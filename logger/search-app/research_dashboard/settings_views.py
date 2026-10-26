"""Study settings: school year, session administration and the original ID ranges.

POST handling is split into one handler per action. Handlers update a
``SettingsForm`` so that a rejected submission re-renders the page with the same
grade, section and typed values the researcher was working on.
"""
from copy import deepcopy

from flask import abort, g, redirect, request

from .i18n import translate
from .participants import GRADES, valid_school_year
from .session_lifecycle import session_removal_problem
from .state import MAX_STUDY_SESSIONS, SETTING_FIELDS, normalize_session_name, roster, validate_settings
from .student_config import range_summary, task_catalog, topics_ready
from .study_config import assignment_for, session_readiness
from .year_controls import school_year_choices

SECTIONS = ("year", "sessions", "participants")
RANGE_ACTIONS = ("save_ranges", "preview_ranges", "edit_ranges")
SESSION_ACTIONS = ("add_session", "save_session", "save_dates", "remove_session", "restore_session")
SAVE_ACTIONS = ("save", "save_year", "save_dates", "save_session", *RANGE_ACTIONS)
NOT_SAVED_ACTIONS = ("preview_ranges", "edit_ranges")
DEFAULT_RANGE = {"start": 41, "end": 60, "prefix": "", "width": 0}
HISTORY_PAGE_SIZE = 10
ROSTER_PAGE_SIZE = 10
VISIBLE_ERRORS = frozenset((
    "invalid_ranges", "overlapping_ranges", "invalid_task_assignment", "invalid_sessions", "invalid_date",
    "invalid_session_name", "overlapping_dates", "settings_changed", "session_limit", "invalid_school_year",
    "school_year_required", "session_year_mismatch", "participant_inactive", "range_editor_retired",
    "invalid_historical_grade", "overlapping_historical_grades", "session_has_records", "session_year_has_records",
    "session_usage_unavailable", "session_removal_confirmation"))


class SettingsForm:
    """Request state shared by the POST handlers and the rendered page."""

    def __init__(self, current):
        self.current = current
        self.error = None
        self.grade = request.args.get("grade", "4")
        if self.grade not in GRADES:
            abort(404)
        default_section = "sessions" if "grade" in request.args or request.args.get("new") else "year"
        self.section = request.args.get("section", default_section)
        if self.section not in SECTIONS:
            abort(404)
        try:
            self.history_page = int(request.args.get("page", "1"))
            if self.history_page < 1:
                raise ValueError()
        except ValueError:
            abort(404)
        posted = request.method == "POST"
        self.action = request.form.get("action", "save") if posted else None
        self.range_scope = request.form.get("range_grade") if posted else None
        if self.action in RANGE_ACTIONS:
            self.section = "participants"
            if self.range_scope in GRADES:
                self.grade = self.range_scope
        elif self.action == "save_year":
            self.section = "year"
        elif self.action in SESSION_ACTIONS:
            self.section = "sessions"
        editing = self.action == "save_session"
        self.edit_session_id = request.form.get("session_id") if editing else request.args.get("edit") or None
        self.edit_name = request.form.get("name") if editing else None
        self.edit_date = request.form.get("date") if editing else None
        adding = self.action == "add_session"
        self.add_date = request.form.get("date", "") if adding else ""
        self.add_name = request.form.get("name", "") if adding else ""
        if adding and request.form.get("grade") in GRADES:
            self.grade = request.form["grade"]
        selected_id = ((request.form.get("session_id") if posted else None)
                       or self.edit_session_id or request.args.get("session"))
        selected = _session_in_grade(current, selected_id, self.grade)
        self.year = request.args.get("year", selected.get("school_year", "") if selected
                                     else current.get("current_school_year", ""))
        if self.year and not valid_school_year(self.year):
            abort(404)
        context_session = _session_in_grade(current, request.args.get("session"), self.grade)
        self.session_id = (context_session["id"] if context_session and not context_session.get("removed")
                           and _in_year(context_session, self.year) else None)
        self.range_draft = current
        self.range_preview = False

    @property
    def ranges_submitted(self):
        return self.action in RANGE_ACTIONS


def _session_in_grade(settings, session_id, grade):
    return next((s for s in settings["sessions"] if s["id"] == session_id and s["grade"] == grade), None)


def _apply_ranges(form, updated, catalog, asset_dir):
    """Apply the range editor fields (bulk ID ranges and their task sets)."""
    scope = form.range_scope
    if scope is not None and scope not in GRADES:
        raise ValueError("invalid_ranges")
    if request.form.get("ranges_editor") == "1" and scope in (None, "3"):
        third_enabled = request.form.get("3_enabled") == "1"
        updated["ranges"] = [rule for rule in updated["ranges"] if rule["grade"] != "3" or third_enabled]
        if third_enabled and not any(rule["grade"] == "3" for rule in updated["ranges"]):
            updated["ranges"].append({"grade": "3", **DEFAULT_RANGE})
    for rule in updated["ranges"]:
        grade = rule["grade"]
        if scope is not None and grade != scope:
            continue
        for key in ("start", "end", "width"):
            if f"{grade}_{key}" in request.form:
                try:
                    rule[key] = int(request.form[f"{grade}_{key}"])
                except ValueError:
                    raise ValueError("invalid_ranges") from None
        if f"{grade}_prefix" in request.form:
            rule["prefix"] = request.form[f"{grade}_prefix"]
        if f"{grade}_task_set" in request.form:
            _apply_task_set(rule, request.form[f"{grade}_task_set"], catalog, asset_dir)
    validate_settings(updated)
    form.range_draft = updated
    form.range_preview = form.action == "preview_ranges"


def _apply_task_set(rule, selected, catalog, asset_dir):
    grade = rule["grade"]
    if selected == "existing":
        rule.pop("assignment", None)
    elif selected != "saved":
        task_set = next((item for item in catalog if item["id"] == selected), None)
        if task_set is None:
            raise ValueError("invalid_task_assignment")
        rule["assignment"] = {"id": task_set["id"], "topics": deepcopy(task_set["topics"]), "mode": "missing"}
    elif not rule.get("assignment"):
        raise ValueError("invalid_task_assignment")
    if rule.get("assignment"):
        rule["assignment"]["mode"] = request.form.get(f"{grade}_assignment_mode", "missing")
        if not topics_ready(rule["assignment"]["topics"], asset_dir):
            raise ValueError("invalid_task_assignment")


def _apply_save_dates(form, updated):
    submitted_grade = request.form.get("grade", "")
    if submitted_grade not in GRADES:
        raise ValueError("invalid_sessions")
    form.grade = submitted_grade
    submitted = [s for s in updated["sessions"] if s["id"] in request.form or f"name_{s['id']}" in request.form]
    if not submitted or any(s["grade"] != form.grade for s in submitted):
        raise ValueError("invalid_sessions")


def _apply_save_session(form, updated):
    form.edit_session_id = request.form.get("session_id")
    form.edit_name = request.form.get("name")
    form.edit_date = request.form.get("date")
    if form.edit_name is None or form.edit_date is None:
        raise ValueError("invalid_sessions")
    study_session = _session_in_grade(updated, form.edit_session_id, form.grade)
    if study_session is None:
        raise ValueError("invalid_sessions")
    study_session["name"] = normalize_session_name(form.edit_name)
    study_session["date"] = form.edit_date
    study_session["school_year"] = request.form.get("school_year", study_session.get("school_year", ""))


def _apply_dates(form, updated):
    """Session dates (and, for save_dates, names) posted as fields keyed by session ID."""
    for study_session in updated["sessions"]:
        if study_session["id"] in request.form:
            study_session["date"] = request.form[study_session["id"]]
        if form.action == "save_dates" and f"name_{study_session['id']}" in request.form:
            study_session["name"] = normalize_session_name(request.form[f"name_{study_session['id']}"])


def _range_forms(form):
    rows = []
    for grade in ("4", "5", "3"):
        rule = next((r for r in form.range_draft["ranges"] if r["grade"] == grade), None)
        saved_rule = next((r for r in form.current["ranges"] if r["grade"] == grade), None)
        fields = deepcopy(rule or saved_rule or {"grade": grade, **DEFAULT_RANGE})
        fields["enabled"] = rule is not None
        fields["task_set"] = "saved" if fields.get("assignment") else "existing"
        fields["assignment_mode"] = fields.get("assignment", {}).get("mode", "missing")
        if form.ranges_submitted:
            for key in ("start", "end", "prefix", "width", "task_set", "assignment_mode"):
                fields[key] = request.form.get(f"{grade}_{key}", fields[key])
            if request.form.get("ranges_editor") == "1" and grade == "3" and form.range_scope in (None, "3"):
                fields["enabled"] = request.form.get("3_enabled") == "1"
        rows.append(fields)
    return rows


def _range_changes(current, draft, participant_session_id):
    """IDs added/removed/moved by a range draft and its effect on who may start."""
    old_roster, proposed_roster = roster(current), roster(draft)
    changes = {"added": sorted(set(proposed_roster) - set(old_roster)),
               "removed": sorted(set(old_roster) - set(proposed_roster)),
               "moved": sorted(uid for uid in set(old_roster) & set(proposed_roster)
                               if old_roster[uid] != proposed_roster[uid])}

    def ready_assignments(configuration):
        return {uid: resolved["question_set"] for uid in roster(configuration)
                if participant_session_id
                and (resolved := assignment_for(configuration, uid, participant_session_id))
                and resolved["ready"]}

    previous, proposed = ready_assignments(current), ready_assignments(draft)
    changes.update({
        "enabled": sorted(set(proposed) - set(previous)),
        "disabled": sorted(set(previous) - set(proposed)),
        "tasks_changed": sorted(uid for uid in set(previous) & set(proposed) if previous[uid] != proposed[uid]),
    })
    return changes


def _page_of(rows, number, size):
    return rows[(number - 1) * size:number * size]


def _page_count(total, size):
    return max(1, (total + size - 1) // size)


def _in_year(study_session, year):
    # Undated initial sessions remain available to complete their setup.
    return not year or study_session.get("school_year", "") in ("", year)


def _session_page(settings, grade, year, session_id):
    active = sorted((item for item in settings["sessions"] if item["grade"] == grade
                     and not item.get("removed") and _in_year(item, year)),
                    key=lambda item: item["number"], reverse=True)
    return next((index // HISTORY_PAGE_SIZE + 1 for index, item in enumerate(active)
                 if item["id"] == session_id), 1)


def session_review_url(dash, settings, study_session, fallback_year=None):
    """Session administration opened at a session's saved state: its year and page, or the restore panel."""
    year = study_session.get("school_year") or fallback_year
    removed = bool(study_session.get("removed"))
    page = _session_page(settings, study_session["grade"], year, study_session["id"])
    return dash.u("settings_page", section="sessions", grade=study_session["grade"], year=year,
                  page=page if page > 1 else None, edit=None if removed else study_session["id"],
                  removed="1" if removed else None,
                  _anchor="removed-sessions" if removed else study_session["id"])


def register_settings_routes(dash):
    app, bp, state = dash.app, dash.bp, dash.state

    def remove_or_restore(form, updated, revision):
        target = _session_in_grade(updated, request.form.get("session_id"), form.grade)
        restoring = form.action == "restore_session"
        if target is None or bool(target.get("removed")) != restoring:
            raise ValueError("invalid_sessions")
        if restoring:
            target["removed"] = False
            if "date" in request.form:
                target["date"] = request.form["date"]
        else:
            if request.form.get("confirm_remove") != "1":
                raise ValueError("session_removal_confirmation")
            reason = session_removal_problem(dash.index, form.current, target)
            if reason:
                raise ValueError(reason)
            target["removed"] = True
        state.save_settings(updated, revision)
        removing = not restoring
        target_year = form.year
        target_page = 1 if removing else _session_page(updated, form.grade, target_year, target["id"])
        return redirect(dash.u("settings_page", section="sessions", grade=form.grade, year=target_year, saved="1",
                               saved_action=form.action, removed="1" if removing else None,
                               page=target_page if target_page > 1 else None,
                               edit=target["id"] if restoring else None,
                               _anchor="removed-sessions" if removing else target["id"]))

    def add_session(form, revision):
        add_grade = request.form.get("grade", "")
        if add_grade in GRADES:
            form.grade = add_grade
        form.add_date = request.form.get("date", "")
        form.add_name = request.form.get("name", "")
        study_session = state.add_study_session(add_grade, form.add_date, revision, form.add_name,
                                                request.form.get("school_year"))
        return redirect(dash.u("overview", grade=add_grade, session=study_session["id"]))

    def handle_post(form, catalog):
        """Apply the submitted action; return a redirect, or None to re-render the page."""
        current, action = form.current, form.action
        revision = int(request.form["revision"])
        if revision != current["revision"]:
            raise ValueError("settings_changed")
        updated = deepcopy({key: current[key] for key in SETTING_FIELDS})
        if action in ("remove_session", "restore_session"):
            return remove_or_restore(form, updated, revision)
        if action == "add_session":
            return add_session(form, revision)
        if action not in SAVE_ACTIONS:
            raise ValueError("invalid_settings")
        if action == "save_year" and "current_school_year" not in request.form:
            raise ValueError("invalid_school_year")
        if action in ("save", "save_year") and "current_school_year" in request.form:
            updated["current_school_year"] = request.form["current_school_year"].strip()
        if action in ("save", *RANGE_ACTIONS):
            _apply_ranges(form, updated, catalog, app.config["STUDENT_ASSET_DIR"])
        if action == "save_dates":
            _apply_save_dates(form, updated)
        if action == "save_session":
            _apply_save_session(form, updated)
        if action in ("save", "save_dates"):
            _apply_dates(form, updated)
        if action in NOT_SAVED_ACTIONS:
            return None
        state.save_settings(updated, revision)
        target_year, target_page = form.year, form.history_page
        if action == "save_session":
            target = _session_in_grade(updated, form.edit_session_id, form.grade)
            if target_year and target.get("school_year"):
                target_year = target["school_year"]
            target_page = _session_page(updated, form.grade, target_year, form.edit_session_id)
        anchor = {"save_year": "school-year", "save_dates": "session-history",
                  "save_session": form.edit_session_id, "save_ranges": "participant-ids"}.get(action)
        return redirect(dash.u("settings_page", saved="1", grade=form.grade, section=form.section,
                               year=target_year, saved_action=action,
                               page=target_page if target_page > 1 else None,
                               edit=form.edit_session_id if action == "save_session" else None,
                               _anchor=anchor))

    def participant_overview(form, catalog):
        """Range summaries, the selected session's readiness and the paginated ID rows."""
        draft = form.range_draft
        participant_sessions = [s for s in draft["sessions"] if s["grade"] == form.grade and not s.get("removed")]
        participant_session_id = (request.args.get("participant_session")
                                  or (participant_sessions[0]["id"] if participant_sessions else None))
        participant_session = next((s for s in participant_sessions if s["id"] == participant_session_id), None)
        if participant_session_id and participant_session is None:
            abort(404)
        summaries = []
        for rule in draft["ranges"]:
            summary = range_summary(app, rule)
            study_session = participant_session if rule["grade"] == form.grade else next(
                (s for s in draft["sessions"] if s["grade"] == rule["grade"] and not s.get("removed")), None)
            if study_session:
                summary.update(session_readiness(draft, study_session))
            else:
                summary.update(ready=0, missing=summary["ids"], participants=[
                    {"id": uid, "ready": False, "problem": "session_date_missing", "questions": [], "titles": []}
                    for uid in summary["ids"]])
            summaries.append(summary)
        range_forms = _range_forms(form)
        selected_range = next(rule for rule in range_forms if rule["grade"] == form.grade)
        selected_summary = next((summary for summary in summaries if summary["grade"] == form.grade), None)
        mode = ("review" if form.range_preview else
                "edit" if form.ranges_submitted or request.args.get("edit_participants") == "1" else "view")
        participant_filter = request.args.get("status", "all")
        if participant_filter not in ("all", "missing"):
            abort(404)
        rows = selected_summary["participants"] if selected_summary else []
        if participant_filter == "missing" and mode == "view":
            rows = [person for person in rows if not person["ready"]]
        total = len(rows)
        try:
            roster_page = int(request.args.get("roster_page", "1")) if mode == "view" else 1
            roster_page_count = _page_count(total, ROSTER_PAGE_SIZE)
            if not 1 <= roster_page <= roster_page_count:
                raise ValueError()
        except ValueError:
            abort(404)
        if mode == "view":
            rows = _page_of(rows, roster_page, ROSTER_PAGE_SIZE)
        task_label = translate("keep_existing_tasks", g.research_lang)
        if selected_range["task_set"] == "saved" and selected_range.get("assignment"):
            task_label = selected_range["assignment"]["topics"]["1_short"]
        else:
            task_label = next((item["label"] for item in catalog if item["id"] == selected_range["task_set"]),
                              task_label)
        return {"participants_mode": mode, "participant_sessions": participant_sessions,
                "participant_session": participant_session, "selected_range": selected_range,
                "selected_summary": selected_summary, "selected_task_label": task_label,
                "participant_rows": rows, "participant_filter": participant_filter,
                "participant_total": total, "roster_page": roster_page, "roster_page_count": roster_page_count,
                "range_forms": range_forms, "range_summaries": summaries,
                "range_changes": _range_changes(form.current, draft, participant_session_id)}

    def session_history(form):
        current = form.current
        in_grade = [s for s in current["sessions"] if s["grade"] == form.grade and _in_year(s, form.year)]
        active = sorted((s for s in in_grade if not s.get("removed")), key=lambda s: s["number"], reverse=True)
        removed = sorted((s for s in in_grade if s.get("removed")), key=lambda s: s["number"], reverse=True)
        page_count = _page_count(len(active), HISTORY_PAGE_SIZE)
        if form.history_page > page_count:
            if not form.error:
                abort(404)
            # A concurrent removal/year change may invalidate a submitted page.
            # Keep rejected input visible without accepting invalid GET URLs.
            form.history_page = page_count
        shown = _page_of(active, form.history_page, HISTORY_PAGE_SIZE)
        submitted = (_session_in_grade(current, form.edit_session_id, form.grade)
                     if form.error and form.action == "save_session" else None)
        rejected_session = (submitted if submitted and submitted["id"] not in {s["id"] for s in shown}
                            else None)
        saved_session_url = None
        if submitted and form.error == "settings_changed":
            saved_session_url = session_review_url(dash, current, submitted, form.year)
        numbers = {grade: [s["number"] for s in current["sessions"] if s["grade"] == grade] for grade in GRADES}
        return {"history_page_count": page_count, "history_total": len(active), "history_sessions": shown,
                "removed_sessions": removed, "rejected_session": rejected_session,
                "saved_session_url": saved_session_url,
                "next_numbers": {grade: max(values, default=0) + 1 for grade, values in numbers.items()},
                "session_readiness": {s["id"]: session_readiness(current, s) for s in shown}}

    @bp.route("/settings", methods=["GET", "POST"])
    def settings_page():
        current = state.settings()
        form = SettingsForm(current)
        catalog = task_catalog(app)
        if request.method == "POST":
            try:
                response = handle_post(form, catalog)
                if response is not None:
                    return response
            except (ValueError, KeyError) as exc:
                form.error = str(exc) if str(exc) in VISIBLE_ERRORS else "invalid_settings"
        error = form.error
        submitted_revision = request.form.get("revision", current["revision"])
        history = session_history(form)

        def revision_for(action, session_id=None):
            # Only the rejected form keeps its old revision, so saving it again cannot
            # overwrite the other change. The page's other forms show current values.
            rejected = (error == "settings_changed" and form.action == action
                        and (session_id is None or request.form.get("session_id") == session_id))
            return submitted_revision if rejected else current["revision"]

        return dash.page(
            "settings", settings=current, error=error, revision_for=revision_for,
            form_revision=submitted_revision if error == "settings_changed" else current["revision"],
            active_section=form.section,
            school_year_value=(request.form.get("current_school_year", current["current_school_year"])
                               if form.action == "save_year" and error else current["current_school_year"]),
            task_catalog=catalog, range_preview=form.range_preview,
            ranges_error=error if form.ranges_submitted else None,
            range_form_revision=(submitted_revision if form.ranges_submitted and error == "settings_changed"
                                 else current["revision"]),
            history_grade=form.grade, history_page=form.history_page,
            history_year=form.year, school_years=school_year_choices(current, form.year, request.form.get("school_year")),
            study_context={"grade": form.grade, "school_year": form.year, "id": form.session_id},
            session_limit=MAX_STUDY_SESSIONS, add_date=form.add_date, add_name=form.add_name,
            open_new=request.args.get("new") == "1" or form.action == "add_session" and error is not None,
            edit_session_id=form.edit_session_id, edit_name=form.edit_name, edit_date=form.edit_date,
            **participant_overview(form, catalog), **history), 400 if error else 200
