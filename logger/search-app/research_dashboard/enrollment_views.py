"""Researcher enrollment workflows; all writes go through State transactions."""
from flask import abort, g, redirect, request
from itsdangerous import BadSignature, URLSafeSerializer

from .state import DEFAULT_STUDY_ID, identity
from .preparation_views import preparation_session
from .participants import GRADES, parse_ids, participant_sort_key, valid_school_year

ERRORS = frozenset(("settings_changed", "invalid_enrollment", "invalid_participant_ids",
                   "participant_id_reserved", "participant_not_registered", "participant_inactive", "school_year_required", "invalid_promotion_year",
                   "enrollment_conflict", "empty_promotion", "invalid_identity_link", "identity_link_conflict"))


def register_enrollment_routes(bp, state, index, page, u):
    @bp.route("/settings/enrollment", methods=["GET", "POST"])
    def enrollment_page():
        settings = state.settings()
        view = request.args.get("view", "registry")
        if view not in ("registry", "promotion", "links"):
            abort(404)
        workflow_session = preparation_session(settings, request.args.get("prepare_session"))
        if workflow_session and (view != "registry" or not workflow_session.get("school_year")):
            abort(404)
        form = request.form.to_dict() if request.method == "POST" else {}
        year = request.args.get("year", workflow_session["school_year"] if workflow_session else settings["current_school_year"])
        if year and not valid_school_year(year):
            abort(404)
        grade = request.args.get("grade", workflow_session["grade"] if workflow_session else "all")
        status = request.args.get("status", "all")
        if grade not in (*GRADES, "all") or status not in ("all", "active", "inactive"):
            abort(404)
        if workflow_session and (year != workflow_session["school_year"] or grade != workflow_session["grade"]):
            abort(404)
        query = request.args.get("q", "").strip()[:32]
        signer = URLSafeSerializer(g.research_hash, salt="sol-enrollment-review")
        preview, token, error, operation = None, None, None, form.get("operation")
        def legacy_records():
            index.refresh()
            return [run for run in index.summaries(settings)
                      if run["collection"] == "legacy" and run["participant_id"] and run["date"]
                      and run["study_id"] == DEFAULT_STUDY_ID]

        legacy = legacy_records() if view == "links" else []
        if request.method == "POST":
            try:
                if form.get("action") == "confirm":
                    payload = signer.loads(form["review_token"])
                    if payload.get("workflow_session") != (workflow_session["id"] if workflow_session else None):
                        raise ValueError("invalid_enrollment")
                    operation, arguments, revision = payload["operation"], payload["arguments"], payload["revision"]
                    preview, token = payload["preview"], form["review_token"]
                else:
                    revision = int(form["revision"])
                    if operation in ("add", "enroll"):
                        arguments = dict(ids=parse_ids(form.get("ids", "")), year=form.get("year"), grade=form.get("grade"))
                    elif operation == "update":
                        if form.get("active") not in ("yes", "no"):
                            raise ValueError("invalid_enrollment")
                        arguments = dict(uid=form.get("uid"), year=form.get("year"), grade=form.get("grade"), active=form["active"] == "yes")
                    elif operation == "promote":
                        arguments = dict(source_year=form.get("source_year"), target_year=form.get("target_year"))
                    elif operation == "link":
                        arguments = {key: form.get(key, "").strip() for key in ("source_id", "uid", "date_from", "date_to", "note")}
                    elif operation == "unlink":
                        arguments = dict(link_id=form.get("link_id"))
                    else:
                        raise ValueError("invalid_enrollment")
                if workflow_session and (operation not in ("add", "enroll", "update")
                        or arguments.get("year") != workflow_session["school_year"]
                        or operation != "update" and arguments.get("grade") != workflow_session["grade"]):
                    raise ValueError("invalid_enrollment")
                if operation == "link" and view != "links":
                    legacy = legacy_records()
                if operation == "link" and not any(run["participant_id"] == arguments["source_id"]
                                                  and arguments["date_from"] <= run["date"] <= arguments["date_to"] for run in legacy):
                    raise ValueError("invalid_identity_link")
                if form.get("action") == "confirm":
                    state.change_participants(operation, arguments, revision)
                    if workflow_session:
                        return redirect(u("prepare_page", grade=workflow_session["grade"],
                                          year=workflow_session["school_year"], session=workflow_session["id"],
                                          participants_saved="1", _anchor="prepare-participants"))
                    return redirect(u("enrollment_page", grade=grade, status=status, q=query, view="registry" if operation == "promote" else view,
                                      year=arguments.get("target_year", year), saved="1"))
                preview = state.change_participants(operation, arguments, revision, dry_run=True)
                token = signer.dumps(dict(operation=operation, arguments=arguments, revision=revision, preview=preview,
                                         workflow_session=workflow_session["id"] if workflow_session else None))
            except (ValueError, KeyError, TypeError, BadSignature) as exc:
                error = str(exc) if str(exc) in ERRORS else "invalid_enrollment"
        enrollments = settings["enrollments"].get(year, {})
        people = [{"id": uid, **person, "grade": enrollments.get(uid, {}).get("grade"),
                   "history": [{"year": school_year, "grade": members[uid]["grade"]}
                               for school_year, members in sorted(settings["enrollments"].items()) if uid in members]}
                  for uid, person in settings["participant_registry"].items()
                  if (not query or query == uid)
                  and (grade == "all" or enrollments.get(uid, {}).get("grade") == grade)
                  and (status == "all" or person["active"] == (status == "active"))]
        people.sort(key=lambda p: participant_sort_key(p["id"]))
        try:
            number = int(request.args.get("page", "1"))
            if not 1 <= number <= max(1, (len(people) + 49) // 50):
                raise ValueError()
        except ValueError:
            abort(404)
        editing = form.get("uid") if operation == "update" else request.args.get("edit")
        person = next((p for p in people if p["id"] == editing), None)
        if editing and person is None:
            abort(404)
        audit = state.participant_changes()
        return page("enrollment", settings=settings, workflow_session=workflow_session,
                    study_context=workflow_session or {"grade": grade, "school_year": year},
                    research_area="prepare" if workflow_session else "settings", view=view, year=year, grade=grade, status=status, query=query,
                    people=people[(number-1)*50:number*50], total=len(people), page_number=number,
                    page_count=max(1, (len(people)+49)//50), editing=person, form=form,
                    preview=preview, review_token=token, operation=operation, error=error,
                    participant_token=identity, registry_ids=sorted(settings["participant_registry"], key=participant_sort_key),
                    legacy_ids=sorted({run["participant_id"] for run in legacy}, key=participant_sort_key), audit=audit), 400 if error else 200
