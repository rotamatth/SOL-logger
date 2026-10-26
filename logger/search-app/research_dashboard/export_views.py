"""ZIP downloads of collected logs for a selection, run, participant, session or grade."""
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import abort, request, send_file
from werkzeug.utils import secure_filename

from .exports import build_export
from .history_data import collection_runs, scoped_people
from .participants import GRADES, valid_school_year
from .state import identity

EXPORT_SCOPES = ("task", "run", "session", "participant", "grade", "grade_session")


def _zip_response(output, filename):
    response = send_file(output, mimetype="application/zip", as_attachment=True,
                         download_name=filename, conditional=False, etag=False)
    response.call_on_close(output.close)
    return response


def _timestamp():
    return datetime.now(ZoneInfo("Europe/Zurich")).strftime("%Y%m%d-%H%M%S")


def _participant_token(run, collection):
    if collection == "study":
        return identity(run["study_participant_id"]) if run.get("study_participant_id") else None
    return run["participant_token"]


def register_export_routes(dash):
    bp, state, index = dash.bp, dash.state, dash.index

    @bp.post("/exports/selection")
    def export_selection():
        index.refresh(force=True)
        settings = state.settings()
        summaries = index.summaries(settings)
        collection = request.form.get("collection", "study")
        grade = request.form.get("grade")
        mode = request.form.get("mode")
        if collection not in (*index.roots, "study") or grade not in (*GRADES, "all") or mode not in ("visible", "selected"):
            abort(404)
        selected_year = request.form.get("school_year") or None
        if selected_year and selected_year not in {r["school_year"] for r in collection_runs(state, summaries, collection)}:
            abort(404)
        session_id = request.form.get("session") or None
        if session_id and grade == "all":
            abort(404)
        selected_session = next((s for s in settings["sessions"] if s["id"] == session_id and s["grade"] == grade), None)
        if session_id and selected_session is None:
            abort(404)
        visible = scoped_people(state, settings, summaries, collection, grade, selected_year, selected_session)
        eligible = {f"{p['collection']}:{p['token']}": p for p in visible if p["has_downloadable_logs"]}
        if mode == "selected":
            requested = request.form.getlist("participant")
            if not requested or any(value not in eligible for value in requested):
                return dash.problem("invalid_selection", 400)
            chosen = set(requested)
        else:
            chosen = set(eligible)
        selected = [run for person in visible if f"{person['collection']}:{person['token']}" in chosen
                    for run in person["visible_runs"]]
        if not selected:
            return dash.problem("empty_export", 404)
        selection = {"collection": collection, "grade": grade, "mode": mode, "participant_count": len(chosen)}
        if selected_year:
            selection["school_year"] = selected_year
        if selected_session:
            selection["study_session_id"] = selected_session["id"]
        output = build_export(index, selected, settings, mode, selection=selection)
        label = f"grade-{grade}" + (f"-session-{selected_session['number']}" if selected_session else "")
        return _zip_response(output, f"sol-{collection}-{label}-{mode}-{_timestamp()}.zip")

    @bp.get("/exports/<scope>")
    def export(scope):
        if scope not in EXPORT_SCOPES:
            abort(404)
        index.refresh(force=True)
        settings = state.settings()
        summaries = index.summaries(settings)
        collection = request.args.get("collection", "v2")
        if collection not in (*index.roots, "study"):
            abort(404)
        selected = collection_runs(state, summaries, collection)
        task = None
        selection = {"collection": collection}
        label = scope
        if scope in ("run", "task"):
            selected = [r for r in selected if r["id"] == request.args.get("run")]
            if scope == "task":
                task = request.args.get("task")
                if not selected or task not in index.run(selected[0]["id"], settings)["tasks"]:
                    abort(404)
            selection.update(run_id=request.args.get("run"), task=task)
            label = f"run-{request.args.get('run', '')[:12]}" + (f"-task-{task}" if task else "")
        elif scope in ("participant", "session"):
            token = request.args.get("participant")
            selected = [r for r in selected if token and _participant_token(r, collection) == token]
            selection["participant_token"] = token
            if request.args.get("grade"):
                grade = request.args["grade"]
                if grade not in GRADES:
                    abort(404)
                selected = [run for run in selected if run["grade"] == grade]
                selection["grade"] = grade
            if selected:
                label = "participant-" + (secure_filename(selected[0]["participant_id"]) or "unknown")
            if scope == "session":
                session_id = request.args.get("session")
                selected = [r for r in selected if r["study_session"] and r["study_session"]["id"] == session_id]
                selection["study_session_id"] = session_id
                if selected:
                    label += f"-session-{selected[0]['study_session']['number']}"
        else:
            grade = request.args.get("grade")
            if grade not in GRADES:
                abort(404)
            selected = [r for r in selected if r["grade"] == grade]
            selection["grade"] = grade
            label = f"grade-{grade}"
            if scope == "grade_session":
                session_id = request.args.get("session")
                session = next((s for s in settings["sessions"] if s["id"] == session_id and s["grade"] == grade), None)
                if session is None:
                    abort(404)
                selected = [r for r in selected if r["study_session"] and r["study_session"]["id"] == session_id]
                selection["study_session_id"] = session_id
                label += f"-session-{session['number']}"
            else:
                label += "-all-sessions"
        if request.args.get("school_year"):
            selected_year = request.args["school_year"]
            if not valid_school_year(selected_year):
                abort(404)
            selected = [run for run in selected if run["school_year"] == selected_year]
            selection["school_year"] = selected_year
            label += "-" + selected_year.replace("/", "-")
        if not selected:
            return dash.problem("empty_export", 404)
        output = build_export(index, selected, settings, scope, task, selection=selection)
        return _zip_response(output, f"sol-{collection}-{label}-{_timestamp()}.zip")
