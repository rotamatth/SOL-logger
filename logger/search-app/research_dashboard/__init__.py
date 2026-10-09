"""Private researcher routes, independent of participant session state."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import os
import secrets
import sqlite3

from flask import Blueprint, abort, g, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from .exports import SourceSnapshotError, build_export, capture_log
from .i18n import translate
from .index import Index
from .state import DEFAULT_STUDY_ID, GRADES, SETTING_FIELDS, MAX_STUDY_SESSIONS, State, identity, normalize_session_name, roster, validate_settings
from .student_config import configure_students, eligible_students, range_summary, task_catalog, topics_ready

PREFIX = "/dashboard"
COOKIE = "sol_research"


def init_dashboard(app):
    configure_students(app)
    app.config.setdefault("RESEARCH_STATE_DIR", os.getenv("RESEARCH_STATE_DIR", "research_state"))
    app.config.setdefault("RESEARCH_LOG_DIR", os.getenv("SOL_LOG_DIR", "logs_v2"))
    app.config.setdefault("RESEARCH_LEGACY_LOG_DIR", os.getenv("RESEARCH_LEGACY_LOG_DIR", "logs"))
    app.config.setdefault("RESEARCH_PASSWORD_HASH_FILE", os.getenv("RESEARCH_PASSWORD_HASH_FILE", ""))
    app.config.setdefault("RESEARCH_PASSWORD_HASH", os.getenv("RESEARCH_PASSWORD_HASH", ""))
    app.config.setdefault("RESEARCH_COOKIE_SECURE", os.getenv("RESEARCH_COOKIE_SECURE", "0") == "1")
    state = State(app.config["RESEARCH_STATE_DIR"])
    index = Index(app.config["RESEARCH_STATE_DIR"], {
        "v2": app.config["RESEARCH_LOG_DIR"], "legacy": app.config["RESEARCH_LEGACY_LOG_DIR"]})
    app.extensions["research"] = {"state": state, "index": index}
    bp = Blueprint("research", __name__, template_folder="templates", static_folder="static", url_prefix=PREFIX)

    def password_hash():
        filename = app.config["RESEARCH_PASSWORD_HASH_FILE"]
        try:
            if filename:
                with open(filename, encoding="utf-8") as source:
                    value = source.read(4096).strip()
            else:
                value = app.config["RESEARCH_PASSWORD_HASH"]
        except (OSError, UnicodeError):
            return ""
        # Only password hashes are accepted; a mistaken plaintext configuration fails closed.
        if not isinstance(value, str) or value.count("$") != 2 or not value.startswith(("scrypt:", "pbkdf2:")):
            return ""
        return value

    def u(endpoint, **values):
        values.setdefault("lang", g.get("research_lang", "en"))
        return url_for("research." + endpoint, **values)

    def page(name, **values):
        return render_template("research/" + name + ".html", **values)

    def problem(key, code):
        if request.path.endswith("/events.json"):
            return jsonify(error=key), code
        return page("error", message=key), code

    @app.before_request
    def research_gate():
        if not (request.path == PREFIX or request.path.startswith(PREFIX + "/")):
            return None
        g.research_lang = "it" if request.args.get("lang") == "it" else "en"
        g.research_auth = None
        g.research_cookie = request.cookies.get(COOKIE, "")
        request.max_content_length = 64 * 1024
        if request.endpoint == "research.static":
            return None
        g.research_hash = password_hash()
        if not g.research_hash:
            return problem("unconfigured", 503)
        g.research_auth = state.session(g.research_cookie, identity(g.research_hash))
        is_login = request.endpoint == "research.login"
        if not is_login and not (g.research_auth and g.research_auth["authenticated"]):
            if request.path.endswith("/events.json"):
                return problem("login", 401)
            return redirect(u("login"))
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            supplied = request.form.get("csrf", "")
            if not (g.research_auth and secrets.compare_digest(supplied, g.research_auth["csrf"])):
                return problem("csrf_error", 400)
        return None

    @app.after_request
    def research_headers(response):
        if request.path == PREFIX or request.path.startswith(PREFIX + "/"):
            response.headers["Cache-Control"] = "private, no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
            for header in list(response.headers):
                if header[0].lower().startswith("access-control-"):
                    del response.headers[header[0]]
            if g.get("research_new_token"):
                response.set_cookie(COOKIE, g.research_new_token, max_age=28800, path=PREFIX,
                                    httponly=True, samesite="Lax", secure=app.config["RESEARCH_COOKIE_SECURE"])
            elif g.get("research_clear_cookie"):
                response.delete_cookie(COOKIE, path=PREFIX, httponly=True, samesite="Lax",
                                       secure=app.config["RESEARCH_COOKIE_SECURE"])
        return response

    @app.context_processor
    def context():
        if not (request.path == PREFIX or request.path.startswith(PREFIX + "/")):
            return {}
        language = g.get("research_lang", "en")
        def language_url(lang):
            endpoint = request.endpoint if request.endpoint and request.endpoint.startswith("research.") else "research.overview"
            values = {**request.args.to_dict(), **(request.view_args or {}), "lang": lang}
            if endpoint == "research.overview":
                values.pop("q", None)
                values.pop("status", None)
            return url_for(endpoint, **values)
        def when(timestamp):
            if not timestamp:
                return translate("unknown", language)
            return datetime.fromtimestamp(timestamp, ZoneInfo("Europe/Zurich")).strftime("%Y-%m-%d %H:%M:%S %Z")
        return {"t": lambda key: translate(key, language), "u": u, "language": language,
                "language_url": language_url, "auth": g.get("research_auth"), "when": when,
                "grades": GRADES,
                "pretty": lambda value: json.dumps(value, ensure_ascii=False, indent=2)}

    @bp.route("/login", methods=["GET", "POST"])
    def login():
        if g.research_auth and g.research_auth["authenticated"]:
            return redirect(u("overview"))
        if request.method == "GET":
            if not g.research_auth:
                g.research_new_token, g.research_auth = state.new_session(identity(g.research_hash))
            return page("login", error=None)
        attempt = state.reserve_login_attempt(request.remote_addr or "unknown")
        if not attempt:
            response, status = page("login", error="throttled"), 429
            return response, status, {"Retry-After": "900"}
        supplied = request.form.get("password", "")
        try:
            accepted = len(supplied) <= 1024 and check_password_hash(g.research_hash, supplied)
        except (ValueError, TypeError):
            accepted = False
        if not accepted:
            return page("login", error="bad_password"), 401
        state.successful_attempt(attempt)
        state.revoke(g.research_cookie)
        g.research_new_token, g.research_auth = state.new_session(identity(g.research_hash), authenticated=True)
        return redirect(u("overview"))

    @bp.post("/logout")
    def logout():
        state.revoke(g.research_cookie)
        g.research_clear_cookie = True
        return redirect(u("login"))

    def data():
        index.refresh()
        settings = state.settings()
        return settings, index.summaries(settings)

    def collection_runs(summaries, collection):
        if "research_trashed_run_ids" not in g:
            g.research_trashed_run_ids = state.trashed_run_ids()
        return [run for run in summaries if run["id"] not in g.research_trashed_run_ids
                and run["study_id"] in (DEFAULT_STUDY_ID, None) and (
            run["collection"] == collection or collection == "study" and (
            run["collection"] == "v2" or run["grade"] in GRADES))]

    def participants(settings, summaries, collection):
        people = {}
        if collection in ("v2", "study"):
            for uid, grade in roster(settings).items():
                people[("v2", uid)] = {"id": uid, "token": identity(uid), "collection": "v2", "grades": {grade}, "runs": []}
        for run in collection_runs(summaries, collection):
            if run["participant_id"] is None:
                continue
            uid = run["participant_id"]
            p = people.setdefault((run["collection"], uid), {"id": uid, "token": identity(uid),
                                  "collection": run["collection"], "grades": set(), "runs": []})
            if run["grade"]:
                p["grades"].add(run["grade"])
            p["runs"].append(run)
        return sorted(people.values(), key=lambda p: (not p["id"].isdigit(), int(p["id"]) if p["id"].isdigit() else p["id"], p["id"]))

    def scoped_people(settings, summaries, collection, grade, selected_year=None, selected_session=None):
        people = participants(settings, summaries, collection)
        if grade not in ("all", "legacy"):
            people = [p for p in people if grade in p["grades"] or (grade == "unassigned" and (
                not p["grades"] or any(not r["study_session"] for r in p["runs"])))]
        current_roster = roster(settings)
        for p in people:
            p["visible_runs"] = [r for r in p["runs"] if (grade not in GRADES or r["grade"] == grade)
                                 and (not selected_year or r["school_year"] == selected_year)
                                 and (not selected_session or r["study_session"] and r["study_session"]["id"] == selected_session["id"])]
            p["has_downloadable_logs"] = any(r.get("log_file_count", r["event_count"]) for r in p["visible_runs"])
            p["dashboard_status"] = (
                "no_data" if not p["visible_runs"] else
                "completed" if all(run["status"] == "completed" for run in p["visible_runs"]) else "incomplete")
            p["recorded_grades"] = sorted({run["grade"] for run in p["visible_runs"] if run["grade"]})
            p["school_years"] = sorted({run["school_year"] for run in p["visible_runs"] if run["school_year"]}, reverse=True)
            p["current_grade"] = current_roster.get(p["id"]) if p["collection"] == "v2" else None
        return [person for person in people if person["visible_runs"]] if selected_year else people

    @bp.get("/")
    @bp.get("")
    def overview():
        settings, runs = data()
        collection = request.args.get("collection", "study")
        if collection not in (*index.roots, "study"):
            abort(404)
        grade = request.args.get("grade", "4") if collection != "legacy" else request.args.get("grade", "legacy")
        if grade not in (*GRADES, "all", "unassigned", "legacy"):
            abort(404)
        sessions = sorted((s for s in settings["sessions"] if s["grade"] == grade),
                          key=lambda s: s["number"], reverse=True)
        selected_session = None
        if request.args.get("session"):
            selected_session = next((s for s in sessions if s["id"] == request.args["session"]), None)
            if selected_session is None:
                abort(404)
        selected_year = request.args.get("school_year") or None
        school_years = sorted({r["school_year"] for r in collection_runs(runs, collection) if r["school_year"]}, reverse=True)
        if selected_year and selected_year not in school_years:
            abort(404)
        session_cards = [{"session": s, "runs": [r for r in collection_runs(runs, collection)
                         if r["study_session"] and r["study_session"]["id"] == s["id"]
                         and (not selected_year or r["school_year"] == selected_year)]} for s in sessions]
        people = scoped_people(settings, runs, collection, grade, selected_year, selected_session)
        unidentified = [r for r in collection_runs(runs, collection) if r["collection"] == collection
                        and r["participant_id"] is None]
        if collection == "study":
            unidentified = [r for r in collection_runs(runs, collection)
                            if r["collection"] == "v2" and r["participant_id"] is None]
        if selected_year:
            unidentified = [run for run in unidentified if run["school_year"] == selected_year]
        grade_has_logs = {value: any(r["grade"] == value and r.get("log_file_count", r["event_count"])
                                     for r in collection_runs(runs, collection)) for value in GRADES}
        return page("overview", people=people, grade=grade, collection=collection,
                    unidentified=unidentified if grade in ("all", "unassigned", "legacy") else [],
                    scan=index.scan_status(), settings=settings, session_cards=session_cards,
                    selected_session=selected_session, selected_year=selected_year, school_years=school_years,
                    grade_has_logs=grade_has_logs,
                    downloadable_count=sum(person["has_downloadable_logs"] for person in people))

    @bp.get("/participants/<collection>/<token>")
    def participant(collection, token):
        if collection not in index.roots:
            abort(404)
        settings, runs = data()
        person = next((p for p in participants(settings, runs, collection) if p["token"] == token), None)
        if person is None:
            abort(404)
        grade_filter = request.args.get("grade") or None
        year_filter = request.args.get("school_year") or None
        if grade_filter and grade_filter not in GRADES:
            abort(404)
        person["runs"] = [run for run in person["runs"] if (not grade_filter or run["grade"] == grade_filter)
                          and (not year_filter or run["school_year"] == year_filter)]
        if year_filter and not person["runs"]:
            abort(404)
        groups = []
        if collection in ("v2", "legacy"):
            for session in settings["sessions"]:
                if session["grade"] in person["grades"] and (not grade_filter or session["grade"] == grade_filter):
                    groups.append({"session": session, "runs": [r for r in person["runs"] if r["study_session"] and r["study_session"]["id"] == session["id"]]})
        groups.append({"session": None, "runs": [r for r in person["runs"] if not r["study_session"]]})
        for group in groups:
            group["runs"].sort(key=lambda r: (r["date"] or "", r["started_at"] or "", r["id"]))
        groups.sort(key=lambda group: (group["session"] is None,
                                      -group["session"]["number"] if group["session"] else 0))
        selected_session = request.args.get("session")
        if selected_session and not any(group["session"] and group["session"]["id"] == selected_session for group in groups):
            abort(404)
        display_groups = [group for group in groups if
                          (group["session"] and group["session"]["id"] == selected_session)
                          or (not selected_session and group["runs"])]
        grade = grade_filter or (next(iter(person["grades"])) if len(person["grades"]) == 1 else "all")
        return page("participant", person=person, groups=groups, display_groups=display_groups,
                    collection=collection, grade=grade,
                    selected_session=selected_session, selected_year=year_filter, grade_filter=grade_filter,
                    open_logs=request.args.get("view") == "logs", manage=request.args.get("manage") == "1")

    def get_run(key):
        index.refresh()
        run = index.run(key, state.settings())
        if run is None or run["id"] in state.trashed_run_ids() or run["study_id"] not in (DEFAULT_STUDY_ID, None):
            abort(404)
        return run

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
        run = get_run(key)
        task, number, events, total = event_selection(run)
        sources = [f for f in run["files"] if f["kind"] != "metadata" and (
            task is None or (f["kind"] == "task" and f["position"] == task))]
        sources.sort(key=lambda f: (f["kind"] != "full", f["position"] or "", f["name"]))
        return page("run", run=run, task=task, page_number=number, events=events, total=total,
                    sources=sources, tasks=[v for k, v in run["tasks"].items() if task is None or k == task])

    @bp.get("/runs/<key>/logs/<source_id>/view")
    def visualize_log(key, source_id):
        run = get_run(key)
        source = next((f for f in run["files"] if f["id"] == source_id and f["kind"] != "metadata"), None)
        if source is None:
            abort(404)
        task, number, events, total = event_selection(run, source_id=source_id)
        return page("log", run=run, source=source, task=task, page_number=number, events=events, total=total)

    @bp.get("/runs/<key>/logs/<source_id>")
    def download_log(key, source_id):
        index.refresh(force=True)
        run = index.run(key, state.settings())
        if run is None or run["id"] in state.trashed_run_ids() or run["study_id"] not in (DEFAULT_STUDY_ID, None):
            abort(404)
        source = next((f for f in run["files"] if f["id"] == source_id and f["kind"] != "metadata"), None)
        if source is None:
            abort(404)
        try:
            output, details = capture_log(index, run, source)
        except SourceSnapshotError:
            return problem("log_download_unavailable", 409)
        response = send_file(output, mimetype="application/octet-stream", as_attachment=True,
                             download_name=source["name"], conditional=False, etag=False)
        response.content_length = source["size"]
        response.headers["X-Content-SHA256"] = details["sha256"]
        response.call_on_close(output.close)
        return response

    @bp.get("/runs/<key>/events.json")
    def events(key):
        run = get_run(key)
        task, number, records, total = event_selection(run)
        return jsonify(run_id=key, task=task, page=number, page_size=100, total=total, records=records)

    @bp.post("/refresh")
    def refresh():
        index.refresh(force=True)
        return redirect(u("overview", collection=request.form.get("collection", "v2"),
                          grade=request.form.get("grade", "4"), session=request.form.get("session") or None,
                          school_year=request.form.get("school_year") or None))

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
        if selected_year and selected_year not in {r["school_year"] for r in collection_runs(summaries, collection)}:
            abort(404)
        session_id = request.form.get("session") or None
        if session_id and grade == "all":
            abort(404)
        selected_session = next((s for s in settings["sessions"] if s["id"] == session_id and s["grade"] == grade), None)
        if session_id and selected_session is None:
            abort(404)
        visible = scoped_people(settings, summaries, collection, grade, selected_year, selected_session)
        eligible = {f"{p['collection']}:{p['token']}": p for p in visible if p["has_downloadable_logs"]}
        if mode == "selected":
            requested = request.form.getlist("participant")
            if not requested or any(value not in eligible for value in requested):
                return problem("invalid_selection", 400)
            chosen = set(requested)
        else:
            chosen = set(eligible)
        selected = [run for person in visible if f"{person['collection']}:{person['token']}" in chosen
                    for run in person["visible_runs"]]
        if not selected:
            return problem("empty_export", 404)
        selection = {"collection": collection, "grade": grade, "mode": mode,
                     "participant_count": len(chosen)}
        if selected_year:
            selection["school_year"] = selected_year
        if selected_session:
            selection["study_session_id"] = selected_session["id"]
        output = build_export(index, selected, settings, mode, selection=selection)
        label = f"grade-{grade}" + (f"-session-{selected_session['number']}" if selected_session else "")
        response = send_file(output, mimetype="application/zip", as_attachment=True,
                             download_name=f"sol-{collection}-{label}-{mode}-{datetime.now(ZoneInfo('Europe/Zurich')).strftime('%Y%m%d-%H%M%S')}.zip",
                             conditional=False, etag=False)
        response.call_on_close(output.close)
        return response

    @bp.get("/trash")
    def trash_page():
        index.refresh()
        settings = state.settings()
        summaries = {run["id"]: run for run in index.summaries(settings)}
        entries = [{**item, "run": summaries.get(item["run_id"])} for item in state.trashed_runs()]
        return page("trash", entries=entries)

    @bp.post("/runs/<key>/trash")
    def trash_run(key):
        index.refresh(force=True)
        run = index.run(key, state.settings())
        if run is None or run["study_id"] not in (DEFAULT_STUDY_ID, None) or key in state.trashed_run_ids():
            abort(404)
        state.trash_run(key)
        return redirect(u("trash_page", trashed="1"))

    @bp.post("/trash/<key>/restore")
    def restore_run(key):
        if not state.restore_run(key):
            abort(404)
        return redirect(u("trash_page", restored="1"))

    @bp.route("/settings", methods=["GET", "POST"])
    def settings_page():
        current = state.settings()
        error = None
        history_grade = request.args.get("grade", "4")
        if history_grade not in GRADES:
            abort(404)
        active_section = request.args.get("section", "sessions" if "grade" in request.args or request.args.get("new") else "year")
        if active_section not in ("year", "sessions", "participants"):
            abort(404)
        try:
            history_page = int(request.args.get("page", "1"))
            if history_page < 1:
                raise ValueError()
        except ValueError:
            abort(404)
        action = request.form.get("action", "save") if request.method == "POST" else None
        range_scope = request.form.get("range_grade") if request.method == "POST" else None
        if action in ("save_ranges", "preview_ranges", "edit_ranges"):
            active_section = "participants"
            if range_scope in GRADES:
                history_grade = range_scope
        elif action == "save_year":
            active_section = "year"
        elif action in ("add_session", "save_session", "save_dates"):
            active_section = "sessions"
        edit_session_id = request.form.get("session_id") if action == "save_session" else request.args.get("edit") or None
        edit_name = request.form.get("name") if action == "save_session" else None
        edit_date = request.form.get("date") if action == "save_session" else None
        add_date = request.form.get("date", "") if action == "add_session" else ""
        add_name = request.form.get("name", "") if action == "add_session" else ""
        if action == "add_session" and request.form.get("grade") in GRADES:
            history_grade = request.form["grade"]
        range_draft = current
        range_preview = False
        catalog = task_catalog(app)
        if request.method == "POST":
            try:
                revision = int(request.form["revision"])
                if revision != current["revision"]:
                    raise ValueError("settings_changed")
                updated = deepcopy({key: current[key] for key in SETTING_FIELDS})
                if action == "add_session":
                    add_grade = request.form.get("grade", "")
                    if add_grade in GRADES:
                        history_grade = add_grade
                    add_date = request.form.get("date", "")
                    add_name = request.form.get("name", "")
                    study_session = state.add_study_session(add_grade, add_date, revision, add_name)
                    return redirect(u("overview", grade=add_grade, session=study_session["id"]))
                if action not in ("save", "save_year", "save_dates", "save_session", "save_ranges", "preview_ranges", "edit_ranges"):
                    raise ValueError("invalid_settings")
                if action == "save_year" and "current_school_year" not in request.form:
                    raise ValueError("invalid_school_year")
                if action in ("save", "save_year") and "current_school_year" in request.form:
                    updated["current_school_year"] = request.form["current_school_year"].strip()
                if action in ("save", "save_ranges", "preview_ranges", "edit_ranges"):
                    if range_scope is not None and range_scope not in GRADES:
                        raise ValueError("invalid_ranges")
                    if request.form.get("ranges_editor") == "1":
                        if range_scope in (None, "3"):
                            updated["ranges"] = [rule for rule in updated["ranges"]
                                                 if rule["grade"] != "3" or request.form.get("3_enabled") == "1"]
                            if request.form.get("3_enabled") == "1" and not any(rule["grade"] == "3" for rule in updated["ranges"]):
                                updated["ranges"].append({"grade": "3", "start": 41, "end": 60, "prefix": "", "width": 0})
                    for rule in updated["ranges"]:
                        grade = rule["grade"]
                        if range_scope is not None and grade != range_scope:
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
                            selected = request.form[f"{grade}_task_set"]
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
                                if not topics_ready(rule["assignment"]["topics"], app.config["STUDENT_ASSET_DIR"]):
                                    raise ValueError("invalid_task_assignment")
                    validate_settings(updated)
                    range_draft = updated
                    range_preview = action == "preview_ranges"
                if action == "save_dates":
                    submitted_grade = request.form.get("grade", "")
                    if submitted_grade not in GRADES:
                        raise ValueError("invalid_sessions")
                    history_grade = submitted_grade
                    submitted = [s for s in updated["sessions"] if s["id"] in request.form
                                 or f"name_{s['id']}" in request.form]
                    if not submitted or any(s["grade"] != history_grade for s in submitted):
                        raise ValueError("invalid_sessions")
                if action == "save_session":
                    edit_session_id = request.form.get("session_id")
                    edit_name = request.form.get("name")
                    edit_date = request.form.get("date")
                    if edit_name is None or edit_date is None:
                        raise ValueError("invalid_sessions")
                    study_session = next((s for s in updated["sessions"] if s["id"] == edit_session_id
                                          and s["grade"] == history_grade), None)
                    if study_session is None:
                        raise ValueError("invalid_sessions")
                    study_session["name"] = normalize_session_name(edit_name)
                    study_session["date"] = edit_date
                if action in ("save", "save_dates"):
                    for s in updated["sessions"]:
                        if s["id"] in request.form:
                            s["date"] = request.form[s["id"]]
                        if action == "save_dates" and f"name_{s['id']}" in request.form:
                            s["name"] = normalize_session_name(request.form[f"name_{s['id']}"])
                if action not in ("preview_ranges", "edit_ranges"):
                    state.save_settings(updated, revision)
                anchor = {"save_year": "school-year", "save_dates": "session-history",
                          "save_session": edit_session_id, "save_ranges": "participant-ids"}.get(action)
                if action not in ("preview_ranges", "edit_ranges"):
                    return redirect(u("settings_page", saved="1", grade=history_grade,
                                      section=active_section, saved_action=action,
                                      page=history_page if history_page > 1 else None,
                                      edit=edit_session_id if action == "save_session" else None,
                                      _anchor=anchor))
            except (ValueError, KeyError) as exc:
                error = str(exc) if str(exc) in {"invalid_ranges", "overlapping_ranges", "invalid_task_assignment", "invalid_sessions", "invalid_date", "invalid_session_name", "overlapping_dates", "settings_changed", "session_limit", "invalid_school_year", "invalid_historical_grade", "overlapping_historical_grades"} else "invalid_settings"
        ranges_submitted = action in ("save_ranges", "preview_ranges", "edit_ranges")
        range_forms = []
        for grade in ("4", "5", "3"):
            rule = next((r for r in range_draft["ranges"] if r["grade"] == grade), None)
            saved_rule = next((r for r in current["ranges"] if r["grade"] == grade), None)
            fields = deepcopy(rule or saved_rule or {"grade": grade, "start": 41, "end": 60, "prefix": "", "width": 0})
            fields["enabled"] = rule is not None
            fields["task_set"] = "saved" if fields.get("assignment") else "existing"
            fields["assignment_mode"] = fields.get("assignment", {}).get("mode", "missing")
            if ranges_submitted:
                for key in ("start", "end", "prefix", "width", "task_set", "assignment_mode"):
                    fields[key] = request.form.get(f"{grade}_{key}", fields[key])
                if request.form.get("ranges_editor") == "1" and grade == "3" and range_scope in (None, "3"):
                    fields["enabled"] = request.form.get("3_enabled") == "1"
            range_forms.append(fields)
        summaries = [range_summary(app, rule) for rule in range_draft["ranges"]]
        old_roster, proposed_roster = roster(current), roster(range_draft)
        range_changes = {"added": sorted(set(proposed_roster) - set(old_roster)),
                         "removed": sorted(set(old_roster) - set(proposed_roster)),
                         "moved": sorted(uid for uid in set(old_roster) & set(proposed_roster)
                                         if old_roster[uid] != proposed_roster[uid])}
        previous_students = eligible_students(app, current)
        proposed_students = eligible_students(app, range_draft)
        range_changes.update({
            "enabled": sorted(set(proposed_students) - set(previous_students)),
            "disabled": sorted(set(previous_students) - set(proposed_students)),
            "tasks_changed": sorted(uid for uid in set(previous_students) & set(proposed_students)
                                    if previous_students[uid] != proposed_students[uid]),
        })
        calendars = {grade: {s["number"]: s for s in current["sessions"] if s["grade"] == grade}
                     for grade in GRADES}
        next_numbers = {grade: max(values, default=0) + 1 for grade, values in calendars.items()}
        all_history_sessions = sorted((s for s in current["sessions"] if s["grade"] == history_grade),
                                      key=lambda s: s["number"], reverse=True)
        history_page_count = max(1, (len(all_history_sessions) + 9) // 10)
        if history_page > history_page_count:
            abort(404)
        history_sessions = all_history_sessions[(history_page - 1) * 10:history_page * 10]
        selected_range = next(rule for rule in range_forms if rule["grade"] == history_grade)
        selected_summary = next((summary for summary in summaries if summary["grade"] == history_grade), None)
        participants_mode = "review" if range_preview else "edit" if ranges_submitted or request.args.get("edit_participants") == "1" else "view"
        participant_filter = request.args.get("status", "all")
        if participant_filter not in ("all", "missing"):
            abort(404)
        participant_rows = selected_summary["participants"] if selected_summary else []
        if participant_filter == "missing" and participants_mode == "view":
            participant_rows = [person for person in participant_rows if not person["ready"]]
        participant_total = len(participant_rows)
        try:
            roster_page = int(request.args.get("roster_page", "1")) if participants_mode == "view" else 1
            roster_page_count = max(1, (participant_total + 9) // 10)
            if not 1 <= roster_page <= roster_page_count:
                raise ValueError()
        except ValueError:
            abort(404)
        if participants_mode == "view":
            participant_rows = participant_rows[(roster_page - 1) * 10:roster_page * 10]
        selected_task_label = translate("keep_existing_tasks", g.research_lang)
        if selected_range["task_set"] == "saved" and selected_range.get("assignment"):
            selected_task_label = selected_range["assignment"]["topics"]["1_short"]
        else:
            selected_task_label = next((item["label"] for item in catalog if item["id"] == selected_range["task_set"]), selected_task_label)
        return page("settings", settings=current, error=error,
                    form_revision=request.form.get("revision", current["revision"])
                    if error == "settings_changed" else current["revision"],
                    active_section=active_section, participants_mode=participants_mode,
                    selected_range=selected_range, selected_summary=selected_summary,
                    selected_task_label=selected_task_label,
                    participant_rows=participant_rows, participant_filter=participant_filter,
                    participant_total=participant_total, roster_page=roster_page,
                    roster_page_count=roster_page_count,
                    school_year_value=request.form.get("current_school_year", current["current_school_year"])
                    if action == "save_year" and error else current["current_school_year"],
                    range_forms=range_forms, range_summaries=summaries, task_catalog=catalog,
                    range_preview=range_preview, range_changes=range_changes,
                    ranges_error=error if ranges_submitted else None,
                    range_form_revision=request.form.get("revision", current["revision"])
                    if ranges_submitted and error == "settings_changed" else current["revision"],
                    history_grade=history_grade, history_page=history_page,
                    history_page_count=history_page_count, history_total=len(all_history_sessions),
                    history_sessions=history_sessions,
                    next_numbers=next_numbers,
                    session_limit=MAX_STUDY_SESSIONS, add_date=add_date, add_name=add_name,
                    open_new=request.args.get("new") == "1" or action == "add_session" and error is not None,
                    edit_session_id=edit_session_id, edit_name=edit_name, edit_date=edit_date), 400 if error else 200

    @bp.get("/exports/<scope>")
    def export(scope):
        if scope not in ("task", "run", "session", "participant", "grade", "grade_session"):
            abort(404)
        index.refresh(force=True)
        settings = state.settings()
        summaries = index.summaries(settings)
        collection = request.args.get("collection", "v2")
        if collection not in (*index.roots, "study"):
            abort(404)
        if collection == "study" and scope in ("participant", "session"):
            abort(404)
        selected = collection_runs(summaries, collection)
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
            selected = [r for r in selected if r["participant_token"] is not None and r["participant_token"] == token]
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
        elif scope in ("grade", "grade_session"):
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
            selected = [run for run in selected if run["school_year"] == selected_year]
            selection["school_year"] = selected_year
        if not selected:
            return problem("empty_export", 404)
        output = build_export(index, selected, settings, scope, task, selection=selection)
        response = send_file(output, mimetype="application/zip", as_attachment=True,
                             download_name=f"sol-{collection}-{label}-{datetime.now(ZoneInfo('Europe/Zurich')).strftime('%Y%m%d-%H%M%S')}.zip",
                             conditional=False, etag=False)
        response.call_on_close(output.close)
        return response

    @bp.errorhandler(404)
    def not_found(_):
        return problem("not_found", 404)

    @bp.errorhandler(400)
    def bad_request(_):
        return problem("invalid_settings", 400)

    @bp.errorhandler(sqlite3.Error)
    def storage_error(_):
        return problem("storage_error", 503)

    app.register_blueprint(bp)
    return state
