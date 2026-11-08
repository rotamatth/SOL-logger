"""Sessions: the list researchers land on, creating a session, removing and restoring one.

The list reads authoritative settings only, so a reporting-cache failure cannot block it.
"""
from copy import deepcopy

from flask import abort, redirect, request

from .legacy_topics import experiment_questions
from .participants import GRADES, school_year_for, valid_school_year
from .preparation_views import (DETAIL_ERRORS, is_placeholder, save_session_details, session_group, session_needs,
                                zurich_today)
from .session_lifecycle import session_removal_problem
from .state import SETTING_FIELDS
from .study_config import session_readiness
from .year_controls import school_year_choices

REMOVAL_ERRORS = frozenset(("settings_changed", "invalid_sessions", "invalid_date", "overlapping_dates",
                            "session_year_mismatch", "session_year_has_records", "session_has_records",
                            "session_usage_unavailable", "session_removal_confirmation"))


def _in_view(study_session, year, grade):
    return ((grade == "all" or study_session["grade"] == grade)
            and (not year or study_session.get("school_year", "") in ("", year)))


def historical_rows(settings, year, grade):
    """Past experiments known only from their logs, such as May's. They have no session number."""
    rows = {}
    for rule in settings.get("historical_grades", []):
        if (grade != "all" and rule["grade"] != grade) or (year and rule["school_year"] != year):
            continue
        key = (rule["grade"], rule["school_year"], rule["date_from"], rule["date_to"])
        row = rows.setdefault(key, {"historical": True, "grade": rule["grade"], "school_year": rule["school_year"],
                                    "date": rule["date_from"], "date_to": rule["date_to"], "count": 0, "ids": [],
                                    "session": {"date": rule["date_from"], "grade": rule["grade"], "number": 0}})
        row["count"] += rule["end"] - rule["start"] + 1
        row["ids"] += [rule["prefix"] + str(number).zfill(rule["width"]) for number in range(rule["start"], rule["end"] + 1)]
    for row in rows.values():
        # A one-day experiment: its theme and questions, when all its IDs had the same ones.
        if row["date"] == row["date_to"]:
            row["experiment"] = experiment_questions(row["ids"], row["date"])
    return list(rows.values())


def session_rows(settings, year, grade, today):
    """Sessions in view, grouped for the list. Empty numbered slots are not shown."""
    groups = {"today": [], "published": [], "draft": [], "past": []}
    for study_session in settings["sessions"]:
        # Today's session is never hidden by the year filter: it is the one researchers need on the day.
        in_view = _in_view(study_session, year if study_session.get("date") != today else "", grade)
        if study_session.get("removed") or not in_view or is_placeholder(study_session):
            continue
        readiness = session_readiness(settings, study_session)
        group = session_group(study_session, readiness, today)
        groups[group].append({"session": study_session, "readiness": readiness, "group": group,
                              "needs": session_needs(study_session, readiness)})
    groups["past"].extend(historical_rows(settings, year, grade))

    def position(row):
        return row["session"].get("date") or "9999", row["session"]["grade"], row["session"]["number"]
    for group, rows in groups.items():
        rows.sort(key=position, reverse=group == "past")
    return groups


def register_session_routes(dash):
    bp, state, page, u = dash.bp, dash.state, dash.page, dash.u

    def change_removal(settings, year, grade):
        """Remove or restore one session; records protect it from removal."""
        revision = int(request.form["revision"])
        if revision != settings["revision"]:
            raise ValueError("settings_changed")
        action = request.form.get("action")
        if action not in ("remove_session", "restore_session"):
            raise ValueError("invalid_sessions")
        updated = deepcopy({key: settings[key] for key in SETTING_FIELDS})
        target = next((item for item in updated["sessions"] if item["id"] == request.form.get("session_id")), None)
        restoring = action == "restore_session"
        if (target is None or grade not in ("all", target["grade"])
                or bool(target.get("removed")) != restoring):
            raise ValueError("invalid_sessions")
        if restoring:
            target["removed"] = False
            if "date" in request.form:
                target["date"] = request.form["date"]
                target["school_year"] = school_year_for(target["date"]) or target.get("school_year", "")
        else:
            if request.form.get("confirm_remove") != "1":
                raise ValueError("session_removal_confirmation")
            reason = session_removal_problem(dash.index, settings, target)
            if reason:
                raise ValueError(reason)
            target["removed"] = True
        state.save_settings(updated, revision)
        return redirect(u("sessions_page", grade=None if grade == "all" else grade, year=year, saved_action=action,
                          removed=None if restoring else "1",
                          _anchor=target["id"] if restoring else "removed-sessions"))

    @bp.route("/sessions", methods=["GET", "POST"])
    def sessions_page():
        settings = state.settings()
        today = zurich_today()
        grade = request.args.get("grade", "all")
        # Sessions are filed by their date, so a saved current year that lags behind must not hide them.
        year = request.args.get("year", max(settings["current_school_year"] or "", school_year_for(today)))
        if grade not in (*GRADES, "all") or year and not valid_school_year(year):
            abort(404)
        error = None
        if request.method == "POST":
            try:
                return change_removal(settings, year, grade)
            except (ValueError, KeyError) as exc:
                error = str(exc) if str(exc) in REMOVAL_ERRORS else "invalid_settings"
        submitted_revision = request.form.get("revision", settings["revision"])

        def revision_for(action, session_id):
            # Only the rejected form keeps its old revision, so saving it again cannot
            # overwrite the other change. The page's other forms show current values.
            rejected = (error == "settings_changed" and request.form.get("action") == action
                        and request.form.get("session_id") == session_id)
            return submitted_revision if rejected else settings["revision"]

        removed = sorted((item for item in settings["sessions"] if item.get("removed") and _in_view(item, year, grade)),
                         key=lambda item: item.get("date") or "", reverse=True)
        groups = session_rows(settings, year, grade, today)
        return page("sessions", settings=settings, research_area="sessions", sessions_tab="list", groups=groups,
                    removed_sessions=removed, grade_filter=grade, selected_year=year, today=today,
                    school_years=school_year_choices(settings, year, school_year_for(today)),
                    has_current=bool(groups["today"] or groups["published"] or groups["draft"]),
                    revision_for=revision_for, error=error,
                    study_context={"grade": None if grade == "all" else grade, "school_year": year or None,
                                   "id": None}), 400 if error else 200

    @bp.route("/sessions/new", methods=["GET", "POST"])
    def create_session_page():
        settings = state.settings()
        # No class is preselected unless the list was filtered to one: it is an explicit choice.
        grade = request.form.get("grade", request.args.get("grade", ""))
        if request.method == "GET" and grade and grade not in GRADES:
            abort(404)
        error = None
        if request.method == "POST":
            try:
                revision = int(request.form["revision"])
                if revision != settings["revision"]:
                    raise ValueError("settings_changed")
                target = save_session_details(state, settings, grade, None, request.form.get("name", ""),
                                              request.form.get("date", ""), revision)
                return redirect(u("prepare_page", grade=grade, year=target["school_year"], session=target["id"],
                                  saved="1", _anchor="prepare-participants"))
            except (ValueError, KeyError) as exc:
                error = str(exc) if str(exc) in DETAIL_ERRORS else "invalid_settings"
        return page("sessions_new", settings=settings, research_area="sessions", sessions_tab="create",
                    selected_grade=grade, error=error,
                    form_revision=request.form.get("revision", settings["revision"]) if error == "settings_changed"
                    else settings["revision"],
                    study_context={"grade": grade if grade in GRADES else None, "school_year": None,
                                   "id": None}), 400 if error else 200
