"""Study settings: school year and the original ID ranges.

Sessions are administered from the session list (``session_views``).

POST handling is split into one handler per action. Handlers update a
``SettingsForm`` so that a rejected submission re-renders the page with the same
grade, section and typed values the researcher was working on.
"""
from copy import deepcopy

from flask import abort, g, redirect, request

from .i18n import translate
from .participants import GRADES, valid_school_year
from .state import SETTING_FIELDS, roster, validate_settings
from .student_config import range_summary, task_catalog, topics_ready
from .study_config import assignment_for, session_readiness
from .year_controls import school_year_choices

SECTIONS = ("year", "participants")
RANGE_ACTIONS = ("save_ranges", "preview_ranges", "edit_ranges")
SAVE_ACTIONS = ("save", "save_year", *RANGE_ACTIONS)
NOT_SAVED_ACTIONS = ("preview_ranges", "edit_ranges")
DEFAULT_RANGE = {"start": 41, "end": 60, "prefix": "", "width": 0}
ROSTER_PAGE_SIZE = 10
VISIBLE_ERRORS = frozenset((
    "invalid_ranges", "overlapping_ranges", "invalid_task_assignment", "invalid_sessions", "invalid_date",
    "overlapping_dates", "settings_changed", "invalid_school_year", "school_year_required", "session_year_mismatch",
    "participant_inactive", "range_editor_retired", "invalid_historical_grade", "overlapping_historical_grades",
    "session_year_has_records"))


class SettingsForm:
    """Request state shared by the POST handlers and the rendered page."""

    def __init__(self, current):
        self.current = current
        self.error = None
        self.grade = request.args.get("grade", "4")
        if self.grade not in GRADES:
            abort(404)
        self.section = request.args.get("section", "year")
        if self.section not in SECTIONS:
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
        selected = _session_in_grade(current, request.args.get("session"), self.grade)
        self.year = request.args.get("year", selected.get("school_year", "") if selected
                                     else current.get("current_school_year", ""))
        if self.year and not valid_school_year(self.year):
            abort(404)
        self.session_id = (selected["id"] if selected and not selected.get("removed")
                           and _in_year(selected, self.year) else None)
        self.range_draft = current
        self.range_preview = False

    @property
    def ranges_submitted(self):
        return self.action in RANGE_ACTIONS


def _session_in_grade(settings, session_id, grade):
    return next((s for s in settings["sessions"] if s["id"] == session_id and s["grade"] == grade), None)


def _apply_ranges(form, updated, catalog):
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
            _apply_task_set(rule, request.form[f"{grade}_task_set"], catalog)
    validate_settings(updated)
    form.range_draft = updated
    form.range_preview = form.action == "preview_ranges"


def _apply_task_set(rule, selected, catalog):
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
        if not topics_ready(rule["assignment"]["topics"]):
            raise ValueError("invalid_task_assignment")


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


def register_settings_routes(dash):
    app, bp, state = dash.app, dash.bp, dash.state

    def handle_post(form, catalog):
        """Apply the submitted action; return a redirect, or None to re-render the page."""
        current, action = form.current, form.action
        revision = int(request.form["revision"])
        if revision != current["revision"]:
            raise ValueError("settings_changed")
        updated = deepcopy({key: current[key] for key in SETTING_FIELDS})
        if action not in SAVE_ACTIONS:
            raise ValueError("invalid_settings")
        if action == "save_year" and "current_school_year" not in request.form:
            raise ValueError("invalid_school_year")
        if action == "save_year" and request.form["current_school_year"].strip() == current["current_school_year"]:
            # Saving the current year again changes nothing: say so instead of "saved".
            return redirect(dash.u("settings_page", section=form.section, grade=form.grade, year=form.year,
                                   saved_action="year_unchanged", _anchor="school-year"))
        if action in ("save", "save_year") and "current_school_year" in request.form:
            updated["current_school_year"] = request.form["current_school_year"].strip()
        if action in ("save", *RANGE_ACTIONS):
            _apply_ranges(form, updated, catalog)
        if action in NOT_SAVED_ACTIONS:
            return None
        state.save_settings(updated, revision)
        anchor = {"save_year": "school-year", "save_ranges": "participant-ids"}.get(action)
        return redirect(dash.u("settings_page", saved="1", grade=form.grade, section=form.section,
                               year=form.year, saved_action=action, _anchor=anchor))

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

    @bp.route("/settings", methods=["GET", "POST"])
    def settings_page():
        if request.method == "GET" and request.args.get("section") == "sessions":
            # Sessions moved to the session list; older links and bookmarks still arrive here.
            if request.args.get("new") == "1":
                return redirect(dash.u("create_session_page", grade=request.args.get("grade")))
            return redirect(dash.u("sessions_page", grade=request.args.get("grade"), year=request.args.get("year")))
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

        def revision_for(action):
            # Only the rejected form keeps its old revision, so saving it again cannot
            # overwrite the other change. The page's other forms show current values.
            rejected = error == "settings_changed" and form.action == action
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
            history_grade=form.grade, history_year=form.year, school_years=school_year_choices(current, form.year, request.form.get("school_year")),
            study_context={"grade": form.grade, "school_year": form.year, "id": form.session_id},
            **participant_overview(form, catalog)), 400 if error else 200
