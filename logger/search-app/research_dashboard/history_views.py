"""Data and history: grade overview, participant pages, runs, logs and the trash."""
from io import BytesIO
import re

from flask import abort, jsonify, redirect, request, send_file

from .exports import SourceSnapshotError, capture_log
from .history_data import collect_participants, collection_runs, display_session, has_logs, scoped_people
from .participants import GRADES, valid_school_year
from .recap_pdfs import recap_pdf, run_attempt, saved_attempts
from .session_views import historical_rows
from .state import DEFAULT_STUDY_ID
from .study_config import session_readiness
from .task_stats import question_rows, session_rows, trend_charts

GRADE_VIEWS = (*GRADES, "all", "unassigned", "legacy")


def _overview_school_years(settings, source_runs, selected_year):
    return sorted(({r["school_year"] for r in source_runs if r["school_year"]}
                   | set(settings.get("enrollments", {}))
                   | {s["school_year"] for s in settings["sessions"] if s.get("school_year")}
                   | ({settings["current_school_year"]} if settings["current_school_year"] else set())
                   | ({selected_year} if selected_year else set())), reverse=True)


def _overview_sessions(settings, source_runs, grade, selected_year):
    """Configured sessions of a grade, plus removed ones that still have records."""
    recorded = {r["study_session"]["id"] for r in source_runs if r.get("study_session")}
    recorded_in_year = {r["study_session"]["id"] for r in source_runs if r.get("study_session")
                        and (not selected_year or r["school_year"] == selected_year)}
    return sorted((s for s in settings["sessions"] if s["grade"] == grade
                   and (not s.get("removed") or s["id"] in recorded)
                   and (not selected_year or not s.get("school_year")
                        or s["school_year"] == selected_year or s["id"] in recorded_in_year)),
                  key=lambda s: s["number"], reverse=True)


def _in_session(run, session):
    return bool(run["study_session"] and run["study_session"]["id"] == session["id"])


def register_history_routes(dash):
    bp, state, index = dash.bp, dash.state, dash.index

    @bp.get("/")
    @bp.get("")
    def overview():
        if not set(request.args) - {"lang"}:
            return redirect(dash.u("sessions_page"))
        settings, runs = dash.data()
        collection = request.args.get("collection", "study")
        if collection not in (*index.roots, "study"):
            abort(404)
        grade = request.args.get("grade", "4") if collection != "legacy" else request.args.get("grade", "legacy")
        if grade not in GRADE_VIEWS:
            abort(404)
        selected_year = request.args.get("school_year") or None
        if selected_year and not valid_school_year(selected_year):
            abort(404)
        source_runs = collection_runs(state, runs, collection)
        sessions = _overview_sessions(settings, source_runs, grade, selected_year)
        selected_session = None
        if request.args.get("session"):
            selected_session = next((s for s in sessions if s["id"] == request.args["session"]), None)
            if selected_session is None:
                abort(404)
        selected_session_configuration = (selected_session if collection in ("v2", "study") and selected_session
                                          and not selected_session.get("removed") else None)
        scoped_runs = [run for run in source_runs if not selected_year or run["school_year"] == selected_year]
        session_cards = []
        for study_session in sessions:
            matching_runs = [run for run in scoped_runs if _in_session(run, study_session)]
            session_cards.append({"session": display_session(study_session, matching_runs), "runs": matching_runs})
        if selected_session:
            selected_session = display_session(selected_session, scoped_runs)
        people = scoped_people(state, settings, runs, collection, grade, selected_year, selected_session)
        unidentified_collection = "v2" if collection == "study" else collection
        unidentified = [r for r in source_runs
                        if r["collection"] == unidentified_collection and r["participant_id"] is None]
        if selected_year:
            unidentified = [run for run in unidentified if run["school_year"] == selected_year]
        grade_has_logs = {value: any(r["grade"] == value and has_logs(r) for r in source_runs) for value in GRADES}
        scoped_grade_has_logs = {value: any(r["grade"] == value and has_logs(r)
                                            and (not selected_session or _in_session(r, selected_session))
                                            for r in scoped_runs) for value in GRADES}
        preparation_session = selected_session_configuration if selected_session_configuration and (
            not selected_year or not selected_session_configuration.get("school_year")
            or selected_session_configuration["school_year"] == selected_year) else None
        study_context = {"grade": grade, "school_year": selected_year,
                         "id": preparation_session["id"] if preparation_session else None,
                         "preparation_year": (preparation_session.get("school_year")
                                              if preparation_session else selected_year)}
        question_stats = None
        if selected_session and collection in ("v2", "study"):
            expected = (session_readiness(settings, selected_session_configuration)["count"]
                        if selected_session_configuration else None)
            question_stats = question_rows([run for run in scoped_runs if _in_session(run, selected_session)], expected)
        historical_experiments = [row for row in historical_rows(settings, selected_year, grade)
                                  if row.get("experiment")] if collection == "study" and not selected_session else []
        return dash.page("overview", people=people, grade=grade, collection=collection, question_stats=question_stats,
                         historical_experiments=historical_experiments,
                         study_context=study_context, research_area="history",
                         history_sessions=[card["session"] for card in session_cards],
                         unidentified=unidentified if grade in ("all", "unassigned", "legacy") else [],
                         scan=index.scan_status(), settings=settings, session_cards=session_cards,
                         selected_session=selected_session, selected_year=selected_year,
                         school_years=_overview_school_years(settings, source_runs, selected_year),
                         selected_session_configuration=selected_session_configuration,
                         grade_has_logs=grade_has_logs, scoped_grade_has_logs=scoped_grade_has_logs,
                         downloadable_count=sum(person["has_downloadable_logs"] for person in people))

    @bp.get("/participants/<collection>/<token>")
    def participant(collection, token):
        if collection not in (*index.roots, "study"):
            abort(404)
        settings, runs = dash.data()
        person = next((p for p in collect_participants(state, settings, runs, collection) if p["token"] == token), None)
        if person is None:
            abort(404)
        grade_filter = request.args.get("grade") or None
        year_filter = request.args.get("school_year") or None
        if grade_filter and grade_filter not in GRADES:
            abort(404)
        person["runs"] = [run for run in person["runs"] if (not grade_filter or run["grade"] == grade_filter)
                          and (not year_filter or run["school_year"] == year_filter)]
        enrolled_in_year = (year_filter and collection in ("v2", "study")
                            and person["id"] in settings["enrollments"].get(year_filter, {}))
        if year_filter and not person["runs"] and not enrolled_in_year:
            abort(404)
        groups = []
        if collection in ("v2", "legacy", "study"):
            for session in settings["sessions"]:
                if session["grade"] in person["grades"] and (not grade_filter or session["grade"] == grade_filter):
                    matching_runs = [run for run in person["runs"] if _in_session(run, session)]
                    if session.get("removed") and not matching_runs:
                        continue
                    if (year_filter and session.get("school_year")
                            and session["school_year"] != year_filter and not matching_runs):
                        continue
                    groups.append({"session": display_session(session, matching_runs), "runs": matching_runs})
        groups.append({"session": None, "runs": [r for r in person["runs"] if not r["study_session"]]})
        for group in groups:
            group["runs"].sort(key=lambda r: (r["date"] or "", r["started_at"] or "", r["id"]))
        groups.sort(key=lambda group: (group["session"] is None,
                                       -group["session"]["number"] if group["session"] else 0))
        selected_session = request.args.get("session")
        selected_session_group = next((group["session"] for group in groups
                                       if group["session"] and group["session"]["id"] == selected_session), None)
        if selected_session and selected_session_group is None:
            abort(404)
        display_groups = [group for group in groups if
                          (group["session"] and group["session"]["id"] == selected_session)
                          or (not selected_session and group["runs"])]
        grade = grade_filter or (selected_session_group["grade"] if selected_session_group else
                                 next(iter(person["grades"])) if len(person["grades"]) == 1 else "all")
        trend = session_rows(person["runs"])
        saved = saved_attempts(run_attempt(run) for run in person["runs"])
        recap_pdf_runs = {run["id"] for run in person["runs"] if run_attempt(run) in saved}
        return dash.page("participant", person=person, groups=groups, display_groups=display_groups,
                         recap_pdf_runs=recap_pdf_runs,
                         trend=trend, trend_view=trend_charts(trend) if len(trend) > 1 else None,
                         collection=collection, grade=grade,
                         selected_session=selected_session, selected_year=year_filter, grade_filter=grade_filter,
                         open_logs=request.args.get("view") == "logs", manage=request.args.get("manage") == "1",
                         research_area="history")

    def visible_run(key, force=False):
        """A run of this study that is not in the trash, or 404."""
        index.refresh(force=force)
        run = index.run(key, state.settings())
        if run is None or run["id"] in state.trashed_run_ids() or run["study_id"] not in (DEFAULT_STUDY_ID, None):
            abort(404)
        return run

    def log_source(run, source_id):
        source = next((f for f in run["files"] if f["id"] == source_id and f["kind"] != "metadata"), None)
        if source is None:
            abort(404)
        return source

    def event_selection(run, source_id=None):
        task = request.args.get("task") or None
        if task is not None and task not in run["tasks"]:
            abort(404)
        try:
            number = int(request.args.get("page", "1"))
            if not 1 <= number <= 1000000:
                raise ValueError()
        except ValueError:
            abort(400)
        events, total = index.event_page(run, task=task, page=number, source_id=source_id)
        return task, number, events, total

    @bp.get("/runs/<key>")
    def run_detail(key):
        run = visible_run(key)
        task, number, events, total = event_selection(run)
        sources = [f for f in run["files"] if f["kind"] != "metadata" and (
            task is None or (f["kind"] == "task" and f["position"] == task))]
        sources.sort(key=lambda f: (f["kind"] != "full", f["position"] or "", f["name"]))
        return dash.page("run", run=run, task=task, page_number=number, events=events, total=total,
                         sources=sources, tasks=[v for k, v in run["tasks"].items() if task is None or k == task],
                         has_recap_pdf=bool(saved_attempts([run_attempt(run)])), research_area="history")

    @bp.get("/runs/<key>/recap.pdf")
    def run_recap_pdf(key):
        """The PDF of the final recap that the server kept when the child saved the activity."""
        run = visible_run(key)
        pdf = recap_pdf(run_attempt(run))
        if pdf is None:
            abort(404)
        name = "-".join(part for part in ("riepilogo", re.sub(r"[^A-Za-z0-9_-]", "", run["participant_id"] or ""),
                                          run["date"] or "") if part)
        response = send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                             download_name=f"{name}.pdf", max_age=0)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @bp.get("/runs/<key>/logs/<source_id>/view")
    def visualize_log(key, source_id):
        run = visible_run(key)
        source = log_source(run, source_id)
        task, number, events, total = event_selection(run, source_id=source_id)
        return dash.page("log", run=run, source=source, task=task, page_number=number, events=events, total=total,
                         research_area="history")

    @bp.get("/runs/<key>/logs/<source_id>")
    def download_log(key, source_id):
        run = visible_run(key, force=True)
        source = log_source(run, source_id)
        try:
            output, details = capture_log(index, run, source)
        except SourceSnapshotError:
            return dash.problem("log_download_unavailable", 409)
        response = send_file(output, mimetype="application/octet-stream", as_attachment=True,
                             download_name=source["name"], conditional=False, etag=False)
        response.content_length = source["size"]
        response.headers["X-Content-SHA256"] = details["sha256"]
        response.call_on_close(output.close)
        return response

    @bp.get("/runs/<key>/events.json")
    def events(key):
        run = visible_run(key)
        task, number, records, total = event_selection(run)
        return jsonify(run_id=key, task=task, page=number, page_size=100, total=total, records=records)

    @bp.post("/refresh")
    def refresh():
        index.refresh(force=True)
        return redirect(dash.u("overview", collection=request.form.get("collection", "v2"),
                               grade=request.form.get("grade", "4"), session=request.form.get("session") or None,
                               school_year=request.form.get("school_year") or None))

    @bp.get("/trash")
    def trash_page():
        index.refresh()
        settings = state.settings()
        summaries = {run["id"]: run for run in index.summaries(settings)}
        entries = [{**item, "run": summaries.get(item["run_id"])} for item in state.trashed_runs()]
        return dash.page("trash", entries=entries, research_area="history")

    @bp.post("/runs/<key>/trash")
    def trash_run(key):
        index.refresh(force=True)
        run = index.run(key, state.settings())
        if run is None or run["study_id"] not in (DEFAULT_STUDY_ID, None) or key in state.trashed_run_ids():
            abort(404)
        state.trash_run(key)
        return redirect(dash.u("trash_page", trashed="1"))

    @bp.post("/trash/<key>/restore")
    def restore_run(key):
        if not state.restore_run(key):
            abort(404)
        return redirect(dash.u("trash_page", restored="1"))
