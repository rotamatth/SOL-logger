"""Behavior tests against synthetic files: never read or modify the real collection."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from hashlib import sha256
from html import unescape
from io import BytesIO
from pathlib import Path
import importlib.util
import json
import os
import re
import sys
import types
import zipfile
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from research_dashboard import init_dashboard
from research_dashboard.collection import record_run
from research_dashboard.index import Index
from research_dashboard.state import DEFAULT_STUDY_ID, State, default_settings, identity, roster, validate_settings

PASSWORD = "synthetic-research-password"


@pytest.fixture
def app(tmp_path):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="synthetic-student-secret",
                      RESEARCH_STATE_DIR=str(tmp_path / "state"),
                      RESEARCH_LOG_DIR=str(tmp_path / "v2"),
                      RESEARCH_LEGACY_LOG_DIR=str(tmp_path / "legacy"),
                      RESEARCH_PASSWORD_HASH=generate_password_hash(PASSWORD, method="pbkdf2:sha256:1000"),
                      RESEARCH_PASSWORD_HASH_FILE="")
    for kind in ("v2", "legacy"):
        (tmp_path / kind).mkdir()
    CORS(app, resources={r"/(?!dashboard(?:/|$)).*": {"origins": "*"}}, supports_credentials=True)
    init_dashboard(app)

    @app.post("/student-reset")
    def student_reset():
        session.clear()
        session["user_id"] = "21"
        return "reset"

    return app


def csrf(response):
    match = re.search(rb'name="csrf" value="([^"]+)"', response.data)
    assert match, response.data[:500]
    return match[1].decode()


def login(client, password=PASSWORD, lang="en"):
    token = csrf(client.get(f"/dashboard/login?lang={lang}"))
    return client.post(f"/dashboard/login?lang={lang}", data={"password": password, "csrf": token})


def configure(app):
    state = app.extensions["research"]["state"]
    settings = state.settings()
    for s in settings["sessions"]:
        s["date"] = f"2026-10-{s['number']:02d}"
    state.save_settings(settings, settings["revision"])
    return state.settings()


def write_run(app, uid="1", suffix="a", collection="v2", answers=3, finish=False, metadata=True, date="2026-10-01"):
    root = Path(app.config["RESEARCH_LOG_DIR" if collection == "v2" else "RESEARCH_LEGACY_LOG_DIR"])
    stem = f"{uid}_{date}_09-00-00_{suffix}"
    sid = f"technical-{uid}-{suffix}"
    order = ["3", "1", "2"]
    events = []
    for n in range(1, 4):
        base = {"uid": uid, "sessionID": sid, "task_number": n, "actual_topic_number": order[n-1],
                "task_order": order, "timestamp": f"{date}T09:0{n}:00.000"}
        task_events = [{**base, "type": "TaskStarted"}]
        if n <= answers:
            task_events.append({**base, "type": "TaskEnded", "answer": f"Answer for {uid} task {n}"})
        if n == 3 and finish:
            task_events.append({**base, "type": "experimentFinished"})
        events.extend(task_events)
        (root / f"{stem}_task{n}_topic{order[n-1]}.log").write_text("".join(json.dumps(e) + "\n" for e in task_events))
    (root / f"{stem}_FULL.log").write_text("".join(json.dumps(e) + "\n" for e in events))
    if metadata:
        sidecar = {"schema_version": 1, "collection": collection, "participant_id": uid,
                   "technical_session_id": sid, "log_id": suffix, "started_at": date + "T09:00:00+02:00",
                   "grade_at_collection": "4" if uid == "1" else "5" if uid == "21" else None,
                   "app_version": "historical-v2.1", "git_commit": "recorded-commit", "task_order": order,
                   "tasks": [{"presented_number": n, "topic_id": order[n-1], "question": f"Recorded question {n}"} for n in range(1, 4)]}
        (root / f"{stem}.run.json").write_text(json.dumps(sidecar))
    return identity(collection + "\0" + stem), root, stem


def archive(response):
    assert response.status_code == 200, response.data[:500]
    assert response.mimetype == "application/zip"
    z = zipfile.ZipFile(BytesIO(response.data))
    return z, json.loads(z.read("manifest.json"))


def test_all_private_routes_fail_closed_without_credentials(app):
    app.config["RESEARCH_PASSWORD_HASH"] = ""
    client = app.test_client()
    for path in ("/dashboard", "/dashboard/login", "/dashboard/settings", "/dashboard/trash", "/dashboard/runs/test",
                 "/dashboard/runs/test/events.json", "/dashboard/exports/grade?grade=4",
                 "/dashboard/exports/grade_session?grade=4&session=grade-4-session-1",
                 "/dashboard/runs/test/logs/test",
                 "/dashboard/runs/test/logs/test/view",
                 "/dashboard/future-diagrams/test"):
        response = client.get(path)
        assert response.status_code == 503
        assert "no-store" in response.headers["Cache-Control"]


def test_all_data_requires_research_auth_even_with_student_session(app):
    key, _, _ = write_run(app)
    client = app.test_client()
    client.post("/student-reset")
    for path in ("/dashboard", "/dashboard/settings", "/dashboard/trash", f"/dashboard/runs/{key}",
                 f"/dashboard/participants/v2/{identity('1')}", "/dashboard/exports/grade?grade=4",
                 "/dashboard/exports/grade_session?grade=4&session=grade-4-session-1",
                 f"/dashboard/runs/{key}/logs/test", f"/dashboard/runs/{key}/logs/test/view"):
        response = client.get(path, headers={"Origin": "https://untrusted.example"})
        assert response.status_code == 302
        assert "/dashboard/login" in response.location
        assert "Access-Control-Allow-Origin" not in response.headers
    assert client.get(f"/dashboard/runs/{key}/events.json").status_code == 401


def test_login_csrf_rotation_logout_and_separate_student_state(app):
    client = app.test_client()
    response = client.get("/dashboard/login")
    first_cookie = client.get_cookie("sol_research", path="/dashboard").value
    assert "HttpOnly" in response.headers["Set-Cookie"]
    assert "SameSite=Lax" in response.headers["Set-Cookie"]
    assert client.post("/dashboard/login", data={"password": PASSWORD}).status_code == 400
    assert client.post("/dashboard/login", data={"password": PASSWORD, "csrf": csrf(response)}).status_code == 302
    assert client.get_cookie("sol_research", path="/dashboard").value != first_cookie
    client.post("/student-reset")
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"studyLogger" not in response.data and b"logger.js" not in response.data
    assert client.post("/dashboard/logout").status_code == 400
    token = csrf(response)
    assert client.post("/dashboard/logout", data={"csrf": token}).status_code == 302
    assert client.get("/dashboard").status_code == 302


@pytest.mark.parametrize("expiry", ["idle", "absolute", "rotation"])
def test_expiry_and_credential_rotation(app, expiry):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    if expiry == "rotation":
        app.config["RESEARCH_PASSWORD_HASH"] = generate_password_hash("replacement", method="pbkdf2:sha256:1000")
    else:
        column, seconds = ("seen", 1801) if expiry == "idle" else ("created", 28801)
        with state.connect() as db:
            db.execute(f"UPDATE auth SET {column} = {column} - ?", (seconds,))
    assert client.get("/dashboard").status_code == 302


def test_failed_attempts_shared_across_clients_and_csrf_required(app):
    for _ in range(5):
        assert login(app.test_client(), "wrong").status_code == 401
    response = login(app.test_client())
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "900"


def test_atomic_throttle_across_state_connections(app):
    directory = app.config["RESEARCH_STATE_DIR"]
    stores = [State(directory), State(directory)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda n: stores[n % 2].reserve_login_attempt("same-ip"), range(20)))
    assert sum(bool(x) for x in outcomes) == 5


def test_secure_cookie_headers_and_bilingual_ui(app):
    app.config["RESEARCH_COOKIE_SECURE"] = True
    client = app.test_client()
    response = client.get("/dashboard/login?lang=it")
    assert b"Accesso ricercatori" in response.data
    assert "Secure" in response.headers["Set-Cookie"]
    response = login(client, lang="it")
    assert response.location == "/dashboard?lang=it"
    response = client.get("/dashboard?lang=it", headers={"Origin": "https://untrusted.example"})
    assert b"Quarta" in response.data
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "Access-Control-Allow-Origin" not in response.headers


def test_ranges_exact_ids_overlap_and_per_grade_dates():
    settings = default_settings()
    assert roster(settings)["20"] == "4" and roster(settings)["21"] == "5"
    assert "01" not in roster(settings)
    settings["ranges"][0]["width"] = 2
    settings["ranges"][0]["prefix"] = "P-"
    assert roster(validate_settings(settings))["P-01"] == "4"
    settings = default_settings()
    settings["ranges"][1]["start"] = 20
    with pytest.raises(ValueError, match="overlapping_ranges"):
        validate_settings(settings)
    settings = default_settings()
    settings["sessions"][0]["date"] = settings["sessions"][3]["date"] = "2026-10-01"
    validate_settings(settings)
    settings["sessions"][1]["date"] = "2026-10-01"
    with pytest.raises(ValueError, match="overlapping_dates"):
        validate_settings(settings)


def test_settings_require_csrf_reject_stale_revision_and_save_calendar(app):
    client = app.test_client()
    login(client)
    response = client.get("/dashboard/settings")
    state = app.extensions["research"]["state"]
    current = state.settings()
    form = {"revision": current["revision"], "csrf": csrf(response)}
    for rule in current["ranges"]:
        form.update({f"{rule['grade']}_{k}": rule[k] for k in ("start", "end", "prefix", "width")})
    form["grade-4-session-1"] = "2026-10-01"
    assert client.post("/dashboard/settings", data={k:v for k,v in form.items() if k != "csrf"}).status_code == 400
    assert client.post("/dashboard/settings", data=form).status_code == 302
    assert state.settings()["sessions"][0]["date"] == "2026-10-01"
    response = client.post("/dashboard/settings", data=form)
    assert response.status_code == 400
    assert b"Another researcher" in response.data


def test_index_uses_full_once_preserves_order_versions_and_answers(app):
    configure(app)
    key, _, _ = write_run(app, finish=False)
    index = app.extensions["research"]["index"]
    index.refresh()
    run = index.run(key, app.extensions["research"]["state"].settings())
    assert run["event_count"] == 6
    assert run["status"] == "completed" and run["finished"] is False
    assert run["study_session"]["id"] == "grade-4-session-1"
    assert run["tasks"]["1"]["topics"] == ["3"]
    assert run["tasks"]["1"]["questions"] == ["Recorded question 1"]
    assert run["app_version"] == "historical-v2.1"
    assert run["git_commit"] == "recorded-commit"
    assert not run["issues"]
    events, count = index.event_page(run, task="1")
    assert count == 2 and len(events) == 2
    assert events[1]["event"]["answer"] == "Answer for 1 task 1"


def test_unknown_legacy_repeats_and_absent_questions(app):
    configure(app)
    first, _, _ = write_run(app, suffix="one", metadata=False)
    second, _, _ = write_run(app, suffix="two", answers=1)
    unknown, _, _ = write_run(app, uid="001", metadata=False)
    legacy, _, _ = write_run(app, collection="legacy", metadata=False, suffix="deadbeef")
    client = app.test_client()
    login(client)
    response = client.get(f"/dashboard/participants/v2/{identity('1')}?view=logs")
    assert response.status_code == 200
    assert first.encode() in response.data and second.encode() in response.data
    response = client.get(f"/dashboard/runs/{first}")
    assert b"Question text was not recorded" in response.data
    assert b"historical-v2.1" not in response.data
    response = client.get("/dashboard?grade=unassigned")
    assert b">001<" in response.data
    index = app.extensions["research"]["index"]
    settings = app.extensions["research"]["state"].settings()
    assert index.run(unknown, settings)["grade"] is None
    assert index.run(legacy, settings)["study_session"] is None
    assert index.run(legacy, settings)["grade"] is None
    assert index.run(legacy, settings)["log_id"] == "2026-10-01_09-00-00_deadbeef"
    assert index.run(legacy, settings)["log_id_source"] == "filename"


def test_missing_empty_malformed_and_partial_records_are_distinct(app):
    key, root, stem = write_run(app)
    path = root / f"{stem}_FULL.log"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    events[1]["answer"] = ""
    del events[3]["answer"]
    events[5]["answer"] = None
    events.append({**events[1], "task_number": 7, "answer": "unexpected task"})
    path.write_text("".join(json.dumps(e) + "\n" for e in events) + 'not json\n{"type":')
    client = app.test_client()
    login(client)
    response = client.get(f"/dashboard/runs/{key}")
    assert response.status_code == 200
    assert b"Explicitly empty answer" in response.data
    assert b"Submission event has no answer field" in response.data
    assert b"malformed_json" in response.data and b"partial_line" in response.data
    index = app.extensions["research"]["index"]
    run = index.run(key, app.extensions["research"]["state"].settings())
    assert run["status"] == "incomplete"
    assert run["tasks"]["1"]["status"] == "completed"
    assert set(run["tasks"]) == {"1", "2", "3"}
    assert "unrecognized_task_number:7" in run["issues"]


def test_metadata_only_run_visible_before_first_task_save(app, monkeypatch):
    monkeypatch.setenv("SOL_APP_VERSION", "v2-test")
    monkeypatch.setenv("SOL_GIT_COMMIT", "test-commit")
    root = Path(app.config["RESEARCH_LOG_DIR"])
    state = app.extensions["research"]["state"]
    topics = {f"{n}_full": f"Question {n}" for n in (1,2,3)}
    record_run(root, state, "1", "new-session", "new-log", ["2","3","1"], topics)
    first = next(root.glob("*.run.json")).read_bytes()
    with pytest.raises(FileExistsError):
        record_run(root, state, "1", "new-session", "new-log", ["1","2","3"], topics)
    assert next(root.glob("*.run.json")).read_bytes() == first
    index = app.extensions["research"]["index"]
    index.refresh()
    run = index.summaries(state.settings())[0]
    assert run["status"] == "incomplete" and run["event_count"] == 0
    assert run["app_version"] == "v2-test" and run["grade"] == "4"
    client = app.test_client()
    login(client)
    response = client.get("/dashboard")
    assert not any(link.path.endswith("/exports/participant") for link in dashboard_links(response))
    row = next(row for row in re.findall(r'<tr>(.*?)</tr>', response.text, re.S)
               if f'/participants/v2/{identity("1")}' in row)
    assert 'Record without log files' in row and "Visualize logs</a>" in row
    assert 'type="checkbox"' not in row
    assert 'type="checkbox"' not in row and "Download logs" not in row


def test_changed_file_refresh_and_cache_parse_policy(app, monkeypatch):
    key, root, stem = write_run(app)
    index = app.extensions["research"]["index"]
    index.refresh()
    settings = app.extensions["research"]["state"].settings()
    run = index.run(key, settings)
    path = root / f"{stem}_FULL.log"
    with path.open("a") as f:
        f.write(json.dumps({"uid":"1", "sessionID":"technical-1-a", "type":"later", "task_number":3}) + "\n")
    rows, _ = index.event_page(run)
    assert all(row["problem"] == "source_changed_refresh" for row in rows)
    original = index._parse
    calls = []
    def tracked(*args):
        calls.append(args[2])
        return original(*args)
    monkeypatch.setattr(index, "_parse", tracked)
    index.refresh()
    assert not calls
    index.refresh(force=True)
    assert calls == [path.name]


def test_pagination_escaped_content_no_arbitrary_files_and_symlinks(app, tmp_path):
    key, root, stem = write_run(app)
    path = root / f"{stem}_FULL.log"
    payload = '<script>alert("secret")</script>'
    event = {"uid":"1", "sessionID":"technical-1-a", "task_number":1, "type":payload, "answer":payload}
    with path.open("a") as f:
        f.write((json.dumps(event) + "\n") * 205)
    outside = tmp_path / "private.log"
    outside.write_text('TOP SECRET SHOULD NOT BE READ')
    (root / "escape_FULL.log").symlink_to(outside)
    client = app.test_client()
    login(client)
    response = client.get(f"/dashboard/runs/{key}")
    assert b'<script>alert' not in response.data and b"&lt;script&gt;" in response.data
    first = client.get(f"/dashboard/runs/{key}/events.json").json
    third = client.get(f"/dashboard/runs/{key}/events.json?page=3").json
    assert len(first["records"]) == 100 and len(third["records"]) == 11
    assert client.get(f"/dashboard/runs/{key}?page=-1").status_code == 400
    assert client.get("/dashboard/runs/..%2F..%2Fprivate.log/events.json").status_code == 404
    response = client.get("/dashboard?grade=unassigned")
    assert b"TOP SECRET" not in response.data
    symlink_key = identity("v2\0escape")
    _, manifest = archive(client.get(f"/dashboard/exports/run?run={symlink_key}"))
    assert manifest["files"][0]["included"] is False


@pytest.mark.parametrize("scope,params,expected_runs", [
    ("task", "run={run}&task=1", 1),
    ("run", "run={run}", 1),
    ("session", "participant={participant}&session=grade-4-session-1", 2),
    ("participant", "participant={participant}", 3),
    ("grade", "grade=4", 3),
    ("grade_session", "grade=4&session=grade-4-session-1", 2),
])
def test_export_scopes_original_bytes_manifest_and_no_other_participants(app, scope, params, expected_runs):
    configure(app)
    first, root, stem = write_run(app)
    write_run(app, suffix="repeat", finish=True)
    write_run(app, suffix="session2", date="2026-10-02")
    write_run(app, uid="21")
    write_run(app, collection="legacy")
    (root / "credentials.json").write_text('{"password":"must-not-export"}')
    (root / "log_registry.jsonl").write_text('UNRELATED REGISTRY DATA')
    original = {p.name: p.read_bytes() for p in root.iterdir()}
    client = app.test_client()
    login(client)
    query = params.format(run=first, participant=identity("1"))
    response = client.get(f"/dashboard/exports/{scope}?{query}")
    z, manifest = archive(response)
    assert len(manifest["runs"]) == expected_runs
    assert all(r["participant_id"] == "1" and r["collection"] == "v2" for r in manifest["runs"])
    assert manifest["duplicate_events"] and manifest["schema_version"] == 1
    for item in manifest["files"]:
        assert item["included"]
        data = z.read(item["archive_name"])
        assert data == original[item["source_name"]]
        assert item["sha256"] == sha256(data).hexdigest()
        if scope == "task":
            assert "_task1_topic3.log" in item["source_name"]
    for entry in manifest["runs"]:
        metadata = json.loads(z.read(entry["metadata_path"]))
        assert metadata["git_commit"] == "recorded-commit"
        assert set(metadata["tasks"]) == ({"1"} if scope == "task" else {"1","2","3"})
    assert all(p.read_bytes() == original[p.name] for p in root.iterdir())
    assert b"must-not-export" not in b"".join(z.read(n) for n in z.namelist())
    assert b"Answer for 21" not in b"".join(z.read(n) for n in z.namelist())


def test_missing_task_export_does_not_include_full_log_and_partial_bytes_preserved(app):
    key, root, stem = write_run(app)
    (root / f"{stem}_task1_topic3.log").unlink()
    path = root / f"{stem}_FULL.log"
    with path.open("ab") as f:
        f.write(b'{"unfinished":')
    original = path.read_bytes()
    client = app.test_client()
    login(client)
    z, manifest = archive(client.get(f"/dashboard/exports/task?run={key}&task=1"))
    assert not manifest["files"]
    assert manifest["problems"][0]["code"] == "original_task_file_missing"
    assert not any(n.endswith(".log") for n in z.namelist())
    z, manifest = archive(client.get(f"/dashboard/exports/run?run={key}"))
    full = next(f for f in manifest["files"] if f["source_name"].endswith("_FULL.log"))
    assert full["partial_final_line"] and z.read(full["archive_name"]) == original


def test_conflicting_participant_ids_never_enter_participant_export(app):
    key, root, stem = write_run(app)
    path = root / f"{stem}_FULL.log"
    with path.open("a") as f:
        f.write(json.dumps({"type":"TaskEnded","uid":"21","answer":"other child","task_number":1}) + "\n")
    client = app.test_client()
    login(client)
    response = client.get(f"/dashboard/exports/participant?participant={identity('1')}")
    assert response.status_code == 404
    response = client.get("/dashboard?grade=unassigned")
    assert key.encode() in response.data


def test_export_excludes_concurrent_appends_and_keeps_metadata_snapshot(app, monkeypatch):
    import research_dashboard.exports as exports
    key, root, stem = write_run(app, answers=2)
    path = root / f"{stem}_FULL.log"
    original = path.read_bytes()
    index = app.extensions["research"]["index"]
    index.refresh()
    settings = app.extensions["research"]["state"].settings()
    selected = index.summaries(settings)
    original_copy = exports._copy_sources
    def append_before_copy(index, plans, manifest, archive):
        with path.open("a") as f:
            f.write(json.dumps({"uid":"1", "type":"TaskEnded", "task_number":3, "answer":"arrived during export"}) + "\n")
        return original_copy(index, plans, manifest, archive)
    monkeypatch.setattr(exports, "_copy_sources", append_before_copy)
    with exports.build_export(index, selected, settings, "run") as output:
        z = zipfile.ZipFile(output)
        manifest = json.loads(z.read("manifest.json"))
        entry = next(f for f in manifest["files"] if f["source_name"].endswith("_FULL.log"))
        assert z.read(entry["archive_name"]) == original
        assert entry["changed_during_export"] and entry["prefix_matches_index"]
        assert manifest["runs"][0]["status"] == "incomplete"
        metadata = json.loads(z.read(manifest["runs"][0]["metadata_path"]))
        assert not metadata["tasks"]["3"]["answers"]


def test_export_reports_truncation_and_does_not_leak_other_tasks(app, monkeypatch):
    import research_dashboard.exports as exports
    key, root, stem = write_run(app)
    path = root / f"{stem}_task1_topic3.log"
    with path.open("a") as f:
        f.write(json.dumps({"uid":"1", "task_number":2, "type":"TaskEnded", "answer":"other task"}) + "\n")
    client = app.test_client()
    login(client)
    z, manifest = archive(client.get(f"/dashboard/exports/task?run={key}&task=1"))
    assert manifest["files"][0]["problem"] == "task_file_contains_other_tasks"
    assert not manifest["files"][0]["included"]
    assert b"other task" not in b"".join(z.read(n) for n in z.namelist())
    original_copy = exports._copy_sources
    def truncate_before_copy(index, plans, manifest, archive):
        (root / f"{stem}_FULL.log").write_bytes(b"")
        return original_copy(index, plans, manifest, archive)
    monkeypatch.setattr(exports, "_copy_sources", truncate_before_copy)
    z, manifest = archive(client.get(f"/dashboard/exports/run?run={key}"))
    full = next(f for f in manifest["files"] if f["source_name"].endswith("_FULL.log"))
    assert full["problem"] == "source_replaced_or_truncated" and not full["included"]


def test_missing_full_log_falls_back_without_doubling_and_index_is_rebuildable(app):
    key, root, stem = write_run(app)
    (root / f"{stem}_FULL.log").unlink()
    index = app.extensions["research"]["index"]
    settings = app.extensions["research"]["state"].settings()
    index.refresh()
    run = index.run(key, settings)
    assert run["event_count"] == 6 and run["status"] == "completed"
    assert "full_log_missing_using_available_files" in run["issues"]
    index.path.unlink()
    rebuilt = Index(app.config["RESEARCH_STATE_DIR"], index.roots)
    rebuilt.refresh()
    assert rebuilt.run(key, settings)["tasks"] == run["tasks"]
    assert app.extensions["research"]["state"].settings() == settings


def test_export_omits_in_place_replacement_instead_of_leaking_new_contents(app, monkeypatch):
    import research_dashboard.exports as exports
    key, root, stem = write_run(app)
    path = root / f"{stem}_FULL.log"
    original_copy = exports._copy_sources
    def replace_before_copy(index, plans, manifest, archive):
        size = path.stat().st_size
        replacement = (b'OTHER PARTICIPANT DATA ' * (size // 20 + 1))[:size]
        path.write_bytes(replacement)
        return original_copy(index, plans, manifest, archive)
    monkeypatch.setattr(exports, "_copy_sources", replace_before_copy)
    client = app.test_client()
    login(client)
    z, manifest = archive(client.get(f"/dashboard/exports/run?run={key}"))
    full = next(f for f in manifest["files"] if f["source_name"].endswith("_FULL.log"))
    assert not full["included"] and full["problem"] == "source_modified_since_index"
    assert b"OTHER PARTICIPANT" not in b"".join(z.read(n) for n in z.namelist())


def test_deeply_nested_and_oversized_bad_lines_do_not_hide_other_runs(app):
    key, root, stem = write_run(app)
    (root / "broken_FULL.log").write_text("[" * 2000 + "]" * 2000 + "\n" + "x" * (1024 * 1024 + 10) + "\n")
    (root / "broken.run.json").write_text("[" * 2000 + "]" * 2000)
    client = app.test_client()
    login(client)
    assert client.get(f"/dashboard/runs/{key}").status_code == 200
    response = client.get(f"/dashboard/runs/{identity('v2' + chr(0) + 'broken')}")
    assert response.status_code == 200
    assert b"line_too_large" in response.data and b"unreadable_or_invalid_file" in response.data


def test_existing_student_flow_writes_logs_and_question_snapshot(tmp_path, monkeypatch):
    # Real Flask routes and logger, with external search calls replaced by a stub.
    monkeypatch.chdir(APP_ROOT)
    monkeypatch.setenv("SOL_LOG_DIR", str(tmp_path / "v2"))
    monkeypatch.setenv("RESEARCH_LEGACY_LOG_DIR", str(tmp_path / "legacy"))
    monkeypatch.setenv("RESEARCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("SOL_GIT_COMMIT", "integration-commit")
    monkeypatch.setitem(sys.modules, "search_backend", types.ModuleType("search_backend"))
    # Flask-Session's filesystem backend otherwise uses the app cwd.
    import flask_session
    original = flask_session.Session
    def session_in_tmp(app):
        app.config["SESSION_FILE_DIR"] = str(tmp_path / "student-sessions")
        return original(app)
    monkeypatch.setattr(flask_session, "Session", session_in_tmp)
    spec = importlib.util.spec_from_file_location("research_student_integration", APP_ROOT / "search_app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.app.config["TESTING"] = True
    module.app.config["RESEARCH_PASSWORD_HASH"] = generate_password_hash(PASSWORD, method="pbkdf2:sha256:1000")
    client = module.app.test_client()
    login(client)
    assert client.post("/start", data={"user_id":"1"}).status_code == 302
    assert client.get("/dashboard").status_code == 200
    assert client.get("/task").status_code == 200
    assert client.get("/search").status_code == 200
    with client.session_transaction() as student:
        sid, topic = student["session_id"], student["task_number"]
    payload = {"session_id":sid,"logs":[{"uid":"1","sessionID":sid,"type":"TaskEnded","answer":"integration answer"}]}
    response = client.post("/log_session", json=payload)
    assert response.status_code == 200
    root = tmp_path / "v2"
    assert (root / response.json["combined_file"]).read_bytes() == (root / response.json["task_file"]).read_bytes()
    metadata = json.loads(next(root.glob("*.run.json")).read_text())
    assert metadata["tasks"][0]["question"] == module.USER_TOPICS["1"][f"{topic}_full"]
    assert metadata["git_commit"] == "integration-commit"
    assert client.get("/welcome?reset=1").status_code == 200
    assert client.get("/dashboard").status_code == 200


@pytest.mark.parametrize("suffix", ["_FULL.log", "_task1_topic3.log"])
def test_individual_log_download_returns_original_bytes_and_name(app, suffix):
    key, root, stem = write_run(app)
    path = root / (stem + suffix)
    # Partial/malformed bytes remain part of the original research file.
    with path.open("ab") as source:
        source.write(b'{"unfinished":')
    original = path.read_bytes()
    source_id = identity("v2\0" + path.name)
    client = app.test_client()
    login(client)
    response = client.get(f"/dashboard/runs/{key}/logs/{source_id}")
    assert response.status_code == 200
    assert response.mimetype == "application/octet-stream"
    assert response.data == original
    assert path.name in response.headers["Content-Disposition"]
    assert response.content_length == len(original)
    assert response.headers["X-Content-SHA256"] == sha256(original).hexdigest()
    assert "no-store" in response.headers["Cache-Control"]
    assert path.read_bytes() == original
    response.close()


def test_individual_log_download_rejects_other_runs_metadata_and_paths(app):
    key, root, stem = write_run(app)
    _, _, other_stem = write_run(app, uid="21")
    client = app.test_client()
    login(client)
    for name in (f"{other_stem}_FULL.log", f"{stem}.run.json", "../../password.hash", "unknown.log"):
        source_id = identity("v2\0" + name)
        assert client.get(f"/dashboard/runs/{key}/logs/{source_id}").status_code == 404
    assert client.get(f"/dashboard/runs/{key}/logs/..%2F..%2Fpassword.hash").status_code == 404


@pytest.mark.parametrize("change", ["append", "replace", "symlink"])
def test_individual_log_download_verifies_snapshot_before_sending(app, tmp_path, monkeypatch, change):
    import research_dashboard as dashboard
    key, root, stem = write_run(app)
    path = root / f"{stem}_FULL.log"
    original = path.read_bytes()
    original_capture = dashboard.capture_log
    outside = tmp_path / "private.log"
    outside.write_bytes(b"PRIVATE DATA")
    def change_before_capture(index, run, source):
        if change == "append":
            with path.open("ab") as target:
                target.write(b"LATER DATA\n")
        elif change == "replace":
            path.write_bytes((b"PRIVATE DATA" * len(original))[:len(original)])
        else:
            path.unlink()
            path.symlink_to(outside)
        return original_capture(index, run, source)
    monkeypatch.setattr(dashboard, "capture_log", change_before_capture)
    client = app.test_client()
    login(client)
    response = client.get(f"/dashboard/runs/{key}/logs/{identity('v2' + chr(0) + path.name)}")
    if change == "append":
        assert response.status_code == 200 and response.data == original
    else:
        assert response.status_code == 409
        assert b"PRIVATE DATA" not in response.data
    response.close()


def test_grade_session_export_respects_grade_and_date_and_preserves_all_runs(app):
    configure(app)
    state = app.extensions["research"]["state"]
    settings = state.settings()
    settings["sessions"][3]["date"] = "2026-10-04"
    state.save_settings(settings, settings["revision"])
    expected = {
        write_run(app)[0],
        write_run(app, suffix="repeat", answers=1)[0],
        write_run(app, uid="2", answers=2)[0],
    }
    write_run(app, suffix="later", date="2026-10-02")
    write_run(app, uid="21", date="2026-10-04")
    write_run(app, uid="001")
    write_run(app, collection="legacy")
    client = app.test_client()
    login(client)
    response = client.get("/dashboard/exports/grade_session?grade=4&session=grade-4-session-1")
    z, manifest = archive(response)
    assert {r["run_id"] for r in manifest["runs"]} == expected
    assert {r["status"] for r in manifest["runs"]} == {"completed", "incomplete"}
    assert manifest["selection"] == {"collection": "v2", "grade": "4", "study_session_id": "grade-4-session-1"}
    assert b"Answer for 21" not in b"".join(z.read(n) for n in z.namelist())
    assert "grade-4-session-1" in response.headers["Content-Disposition"]


def test_selected_and_visible_downloads_follow_the_current_participant_view(app):
    configure(app)
    first = write_run(app)[0]
    second = write_run(app, uid="2")[0]
    later = write_run(app, suffix="later", date="2026-10-02")[0]
    fifth = write_run(app, uid="21")[0]
    client = app.test_client()
    login(client)
    view = client.get("/dashboard?grade=4&session=grade-4-session-1")
    assert 'value="visible"' not in view.text
    assert re.search(r'<button[^>]*value="selected"[^>]*>.*?Download selected.*?</button>', view.text, re.S)
    assert f'value="v2:{identity("1")}"'.encode() in view.data
    form = {"csrf": csrf(view), "collection": "study", "grade": "4",
            "session": "grade-4-session-1", "mode": "selected",
            "participant": [f"v2:{identity('1')}"]}
    _, selected = archive(client.post("/dashboard/exports/selection", data=form))
    assert {run["run_id"] for run in selected["runs"]} == {first}
    assert selected["selection"] == {"collection": "study", "grade": "4", "mode": "selected",
                                     "participant_count": 1, "study_session_id": "grade-4-session-1"}
    form["mode"] = "visible"
    form.pop("participant")
    _, visible = archive(client.post("/dashboard/exports/selection", data=form))
    assert {run["run_id"] for run in visible["runs"]} == {first, second}
    form["grade"] = "5"
    form["session"] = "grade-5-session-1"
    _, fifth_only = archive(client.post("/dashboard/exports/selection", data=form))
    assert {run["run_id"] for run in fifth_only["runs"]} == {fifth}
    form["grade"] = "all"
    form.pop("session")
    _, all_visible = archive(client.post("/dashboard/exports/selection", data=form))
    assert {run["run_id"] for run in all_visible["runs"]} == {first, second, later, fifth}
    assert client.get("/dashboard/exports/all").status_code == 404


def test_selected_export_rejects_forged_or_empty_participants_and_requires_auth_csrf(app):
    configure(app)
    write_run(app)
    write_run(app, uid="21")
    client = app.test_client()
    login(client)
    form = {"csrf": csrf(client.get("/dashboard?grade=4")), "collection": "study",
            "grade": "4", "mode": "selected", "participant": [f"v2:{identity('21')}"]}
    assert client.post("/dashboard/exports/selection", data=form).status_code == 400
    form.pop("participant")
    assert client.post("/dashboard/exports/selection", data=form).status_code == 400
    form["mode"] = "visible"
    form["session"] = "grade-5-session-1"
    assert client.post("/dashboard/exports/selection", data=form).status_code == 404
    form.pop("session")
    form["csrf"] = "invalid"
    assert client.post("/dashboard/exports/selection", data=form).status_code == 400
    assert app.test_client().post("/dashboard/exports/selection", data=form).status_code == 302


def test_selected_download_keeps_same_participant_id_in_different_collections_separate(app):
    configure(app)
    current = write_run(app)[0]
    historical = write_run(app, collection="legacy", date="2025-10-01", metadata=False)[0]
    add_history_rule(app.extensions["research"]["state"])
    client = app.test_client()
    login(client)
    overview = client.get("/dashboard?grade=all")
    form = {"csrf": csrf(overview), "collection": "study", "grade": "all", "mode": "selected"}
    for collection, expected in (("v2", current), ("legacy", historical)):
        form["participant"] = f"{collection}:{identity('1')}"
        _, manifest = archive(client.post("/dashboard/exports/selection", data=form))
        assert {run["run_id"] for run in manifest["runs"]} == {expected}
    form["mode"] = "visible"
    form.pop("participant")
    _, manifest = archive(client.post("/dashboard/exports/selection", data=form))
    assert {run["run_id"] for run in manifest["runs"]} == {current, historical}


def test_run_trash_is_restorable_and_excluded_from_views_and_exports(app):
    configure(app)
    removed, root, _ = write_run(app)
    retained = write_run(app, suffix="repeat")[0]
    originals = {path.name: path.read_bytes() for path in root.iterdir()}
    client = app.test_client()
    login(client)
    overview = client.get("/dashboard?grade=4")
    manage = next(link for link in dashboard_links(overview) if parse_qs(link.query).get("manage") == ["1"])
    manage_page = client.get(manage.geturl())
    assert b"Move run to Trash" in manage_page.data and removed[:12].encode() in manage_page.data
    original_page = client.get(f"/dashboard/runs/{removed}")
    source_link = next(link for link in dashboard_links(original_page)
                       if link.path.startswith(f"/dashboard/runs/{removed}/logs/") and not link.path.endswith("/view"))
    assert app.test_client().post(f"/dashboard/runs/{removed}/trash", data={"csrf": csrf(manage_page)}).status_code == 302
    assert client.post(f"/dashboard/runs/{removed}/trash", data={"csrf": "invalid"}).status_code == 400
    moved = client.post(f"/dashboard/runs/{removed}/trash", data={"csrf": csrf(manage_page)})
    assert moved.status_code == 302 and "/dashboard/trash" in moved.location
    trash = client.get(moved.location)
    assert removed[:12].encode() in trash.data and b"Restore</button>" in trash.data
    assert {item["run_id"] for item in app.extensions["research"]["state"].trashed_runs()} == {removed}
    assert client.get(f"/dashboard/runs/{removed}").status_code == 404
    assert client.get(source_link.geturl()).status_code == 404
    assert client.get(f"/dashboard/exports/run?run={removed}").status_code == 404
    _, grade_export = archive(client.get("/dashboard/exports/grade?grade=4"))
    assert {run["run_id"] for run in grade_export["runs"]} == {retained}
    _, participant_export = archive(client.get(f"/dashboard/exports/participant?participant={identity('1')}"))
    assert {run["run_id"] for run in participant_export["runs"]} == {retained}
    _, session_export = archive(client.get("/dashboard/exports/grade_session?grade=4&session=grade-4-session-1"))
    assert {run["run_id"] for run in session_export["runs"]} == {retained}
    view = client.get("/dashboard?grade=4")
    _, visible = archive(client.post("/dashboard/exports/selection", data={
        "csrf": csrf(view), "collection": "study", "grade": "4", "mode": "visible"}))
    assert {run["run_id"] for run in visible["runs"]} == {retained}
    assert all(path.read_bytes() == originals[path.name] for path in root.iterdir())
    assert client.post(f"/dashboard/trash/{removed}/restore", data={"csrf": "invalid"}).status_code == 400
    restored = client.post(f"/dashboard/trash/{removed}/restore", data={"csrf": csrf(trash)})
    assert restored.status_code == 302
    assert app.extensions["research"]["state"].trashed_runs() == []
    assert client.get(f"/dashboard/runs/{removed}").status_code == 200
    _, grade_export = archive(client.get("/dashboard/exports/grade?grade=4"))
    assert {run["run_id"] for run in grade_export["runs"]} == {removed, retained}
    assert all(path.read_bytes() == originals[path.name] for path in root.iterdir())


def test_grade_download_excludes_other_grades_and_global_export_is_unavailable(app):
    configure(app)
    expected_grade_4 = {
        write_run(app)[0], write_run(app, suffix="repeat", answers=0)[0],
        write_run(app, suffix="later", date="2026-10-02")[0],
    }
    write_run(app, uid="21")
    write_run(app, uid="unmapped")
    conflict, root, stem = write_run(app, suffix="conflict")
    with (root / f"{stem}_FULL.log").open("a") as target:
        target.write(json.dumps({"uid": "21", "type": "querySubmitted"}) + "\n")
    write_run(app, collection="legacy")
    (root / "credentials.json").write_text("PRIVATE CREDENTIALS")
    original = {p.name: p.read_bytes() for p in root.iterdir()}
    client = app.test_client()
    login(client)
    assert client.get("/dashboard/exports/all").status_code == 404
    assert client.get("/dashboard/exports/all?grade=4&session=grade-4-session-1").status_code == 404
    z, manifest = archive(client.get("/dashboard/exports/grade?grade=4"))
    assert {r["run_id"] for r in manifest["runs"]} == expected_grade_4
    assert {r["grade"] for r in manifest["runs"]} == {"4"}
    assert all(r["collection"] == "v2" for r in manifest["runs"])
    assert manifest["selection"] == {"collection": "v2", "grade": "4"}
    assert manifest["includes_incomplete_runs"] and manifest["includes_repeated_runs"]
    assert b"PRIVATE CREDENTIALS" not in b"".join(z.read(n) for n in z.namelist())
    for item in manifest["files"]:
        assert item["included"] and z.read(item["archive_name"]) == original[item["source_name"]]
    assert all(p.read_bytes() == original[p.name] for p in root.iterdir())
    assert conflict not in {r["run_id"] for r in manifest["runs"]}


@pytest.mark.parametrize("path", [
    "/dashboard/exports/all?collection=v2",
    "/dashboard/exports/grade_session?grade=4",
    "/dashboard/exports/grade_session?grade=4&session=grade-5-session-1",
    "/dashboard/exports/grade_session?grade=unknown&session=grade-4-session-1",
    "/dashboard/exports/grade_session?collection=legacy&grade=4&session=grade-4-session-1",
    "/dashboard/exports/grade_session?grade=4&session=grade-4-session-3",
])
def test_new_exports_reject_invalid_or_empty_scopes(app, path):
    configure(app)
    write_run(app)
    client = app.test_client()
    login(client)
    assert client.get(path).status_code == 404


def dashboard_links(response):
    return [urlsplit(unescape(value)) for value in re.findall(r'href="([^"]+)"', response.text)]


def download_selected_participants(client, response, *participants):
    """Submit the rendered checkbox form, including its current collection scope."""
    form = next(form for form in re.findall(r'<form\b.*?</form>', response.text, re.S)
                if '/exports/selection' in form)
    action = unescape(re.search(r'action="([^"]+)"', form).group(1))
    fields = {name: unescape(value) for name, value in re.findall(
        r'<input type="hidden" name="([^"]+)" value="([^"]*)">', form)}
    for participant in participants:
        assert f'value="{participant}"' in response.text
    fields.update(mode="selected", participant=list(participants))
    return client.post(action, data=fields)


def test_overview_places_distinct_downloads_in_their_scope_and_filters_sessions(app):
    configure(app)
    write_run(app)
    write_run(app, suffix="later", date="2026-10-02")
    client = app.test_client()
    login(client)
    response = client.get("/dashboard?grade=4&session=grade-4-session-2&lang=it")
    assert response.status_code == 200
    assert "Partecipanti · Sessione 2" in response.text
    links = dashboard_links(response)
    exports = [link for link in links if "/exports/" in link.path]
    assert {link.path.rsplit("/", 1)[-1] for link in exports} == {"grade", "grade_session"}
    assert all(parse_qs(link.query)["lang"] == ["it"] for link in exports)
    assert not any(link.path.endswith("/participant") for link in exports)
    assert all(parse_qs(link.query)["grade"] == ["4"] for link in exports if link.path.endswith("/grade_session"))
    assert "<button disabled" not in response.text
    assert all(parse_qs(link.query)["session"] == ["grade-4-session-2"] for link in exports if link.path.endswith("/grade_session"))
    views = [link for link in links if parse_qs(link.query).get("view") == ["logs"]
             and "manage" not in parse_qs(link.query)]
    assert len(views) == 1 and parse_qs(views[0].query)["session"] == ["grade-4-session-2"]
    shown = client.get(views[0].geturl())
    shown_keys = {link.path.rsplit("/", 1)[-1] for link in dashboard_links(shown) if "/runs/" in link.path}
    _, manifest = archive(download_selected_participants(client, response, "v2:" + identity("1")))
    assert manifest["selection"]["study_session_id"] == "grade-4-session-2"
    assert shown_keys == {run["run_id"] for run in manifest["runs"]}
    assert all(run["study_session"]["id"] == "grade-4-session-2" for run in manifest["runs"])
    assert client.get("/dashboard?grade=4&session=grade-5-session-1").status_code == 404
    refreshed = client.post("/dashboard/refresh?lang=it", data={"csrf": csrf(response), "grade": "4", "session": "grade-4-session-2"})
    query = parse_qs(urlsplit(refreshed.location).query)
    assert query["session"] == ["grade-4-session-2"] and query["lang"] == ["it"]
    legacy = client.get("/dashboard?collection=legacy")
    assert not any(link.path.endswith("/all") for link in dashboard_links(legacy))


def test_participant_and_task_buttons_download_only_their_advertised_scope(app):
    configure(app)
    key, root, stem = write_run(app)
    client = app.test_client()
    login(client)
    response = client.get(f"/dashboard/participants/v2/{identity('1')}")
    exports = [link for link in dashboard_links(response) if "/exports/" in link.path]
    assert {link.path.rsplit("/", 1)[-1] for link in exports} == {"participant", "session"}
    assert all(parse_qs(link.query)["participant"] == [identity("1")] for link in exports)
    assert b"Download user session" in response.data
    response = client.get(f"/dashboard/runs/{key}?task=1&lang=it")
    downloads = [link for link in dashboard_links(response) if "/logs/" in link.path and not link.path.endswith("/view")]
    assert len(downloads) == 1 and "Scarica log" in response.text
    downloaded = client.get(downloads[0].geturl())
    assert downloaded.data == (root / f"{stem}_task1_topic3.log").read_bytes()
    downloaded.close()
    assert not any("/exports/" in link.path for link in dashboard_links(response))
    (root / f"{stem}_task1_topic3.log").unlink()
    app.extensions["research"]["index"].refresh(force=True)
    response = client.get(f"/dashboard/runs/{key}?task=1")
    assert b"No original log file" in response.data
    assert not any("/logs/" in link.path for link in dashboard_links(response))


def test_empty_dashboard_shows_clear_status_without_unavailable_row_actions(app):
    client = app.test_client()
    login(client)
    for path in ("/dashboard", f"/dashboard/participants/v2/{identity('1')}", "/dashboard/settings"):
        response = client.get(path)
        assert response.status_code == 200
        assert "V2 collection" not in response.text and "Unassigned" not in response.text and "Legacy archive" not in response.text
        assert not any("/exports/" in link.path for link in dashboard_links(response))
    response = client.get("/dashboard")
    assert response.text.count('<span class="badge no_data">No saved data</span>') == 20
    assert response.text.count('class="dashboard-no-actions muted"') == 20
    assert 'type="checkbox"' not in response.text
    assert "Download logs</button>" not in response.text
    bulk_buttons = re.findall(r'<button\b[^>]*form="selected-export"[^>]*>', response.text)
    assert len(bulk_buttons) == 1 and all("disabled" in button for button in bulk_buttons)
    links = dashboard_links(response)
    assert not any(parse_qs(link.query).get("grade") == ["unassigned"] for link in links)
    assert not any(parse_qs(link.query).get("collection") == ["legacy"] for link in links)
    assert 'class="session-card' not in response.text
    assert b"Last saved</th>" not in response.data
    assert b"Runs</th>" not in response.data


def test_compact_grade_download_and_participant_session_selectors(app):
    configure(app)
    key, _, _ = write_run(app)
    client = app.test_client()
    login(client)
    overview = client.get("/dashboard")
    assert '<nav class="dashboard-grades"' in overview.text
    assert 'class="tabs grade-tabs"' not in overview.text
    assert 'class="download-menu"' not in overview.text
    exports = [link for link in dashboard_links(overview) if link.path.endswith("/exports/grade")]
    assert {parse_qs(link.query)["grade"][0] for link in exports} == {"4"}
    assert 'aria-label="Download all 4th grade"' in overview.text
    assert '<details class="dashboard-more-downloads">' not in overview.text
    assert 'class="dashboard-unavailable"' not in overview.text
    assert any(link.path in ("/dashboard", "/dashboard/") and parse_qs(link.query).get("grade") == ["all"]
               for link in dashboard_links(overview))
    empty = client.get(f"/dashboard/participants/v2/{identity('2')}")
    assert empty.text.count("No data") == 1
    assert '<select id="participant-session" name="session">' in empty.text
    assert all(f'value="grade-4-session-{number}"' in empty.text for number in (1, 2, 3))
    participant = client.get(f"/dashboard/participants/v2/{identity('1')}")
    assert participant.text.count('class="session-entry"') == 1
    assert key.encode() not in participant.data
    selected = client.get(f"/dashboard/participants/v2/{identity('1')}?session=grade-4-session-2&view=logs")
    assert selected.text.count('class="session-entry"') == 1
    assert b"No data" in selected.data and key.encode() not in selected.data


def test_calendar_form_keeps_both_grades_and_preserves_id_format_when_saving_dates(app):
    state = app.extensions["research"]["state"]
    settings = state.settings()
    settings["ranges"][0].update(prefix="P-", width=2)
    state.save_settings(settings, settings["revision"])
    client = app.test_client()
    login(client)
    fourth = client.get("/dashboard/settings?grade=4")
    assert 'id="grade-4-session-1"' in fourth.text and 'id="grade-5-session-1"' not in fourth.text
    participant_editor = client.get("/dashboard/settings?section=participants&grade=4&edit_participants=1")
    assert 'name="4_prefix" value="P-"' in participant_editor.text
    assert client.post("/dashboard/settings?grade=4", data={
        "action": "save_session", "session_id": "grade-4-session-1", "name": "", "date": "2026-10-02",
        "revision": state.settings()["revision"], "csrf": csrf(fourth),
    }).status_code == 302
    fifth = client.get("/dashboard/settings?grade=5")
    assert 'id="grade-5-session-1"' in fifth.text and 'id="grade-4-session-1"' not in fifth.text
    assert client.post("/dashboard/settings?grade=5", data={
        "action": "save_session", "session_id": "grade-5-session-1", "name": "", "date": "2026-10-03",
        "revision": state.settings()["revision"], "csrf": csrf(fifth),
    }).status_code == 302
    saved = state.settings()
    assert saved["ranges"][0]["prefix"] == "P-" and saved["ranges"][0]["width"] == 2
    assert saved["sessions"][0]["date"] == "2026-10-02"
    assert saved["sessions"][3]["date"] == "2026-10-03"


def test_settings_actions_change_only_their_named_fields(app):
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    page = client.get("/dashboard/settings?grade=4")
    assert b"Prepare the school year, sessions and student access" in page.data
    assert 'id="grade-4-session-1"' in page.text and 'id="grade-5-session-1"' not in page.text
    assert "Historical grade assignments" not in page.text
    original = state.settings()
    year = client.post("/dashboard/settings?grade=4", data={
        "action": "save_year", "revision": original["revision"], "csrf": csrf(page),
        "current_school_year": "2026/2027", "grade-4-session-1": "2030-01-01", "4_end": "19",
    })
    assert year.status_code == 302 and urlsplit(year.location).fragment == "school-year"
    after_year = state.settings()
    assert after_year["current_school_year"] == "2026/2027"
    assert after_year["sessions"] == original["sessions"] and after_year["ranges"] == original["ranges"]
    page = client.get("/dashboard/settings?grade=4")
    wrong_grade = client.post("/dashboard/settings?grade=4", data={
        "action": "save_dates", "grade": "4", "revision": after_year["revision"], "csrf": csrf(page),
        "grade-4-session-1": "2026-10-01", "grade-5-session-1": "2026-10-01",
    })
    assert wrong_grade.status_code == 400 and state.settings() == after_year
    dates = client.post("/dashboard/settings?grade=4", data={
        "action": "save_dates", "grade": "4", "revision": after_year["revision"], "csrf": csrf(page),
        "grade-4-session-1": "2026-10-01", "current_school_year": "2030/2031", "4_end": "19",
    })
    assert dates.status_code == 302 and urlsplit(dates.location).fragment == "session-history"
    after_dates = state.settings()
    assert after_dates["sessions"][0]["date"] == "2026-10-01"
    assert after_dates["current_school_year"] == "2026/2027" and after_dates["ranges"] == original["ranges"]
    ranges = client.post("/dashboard/settings?grade=4", data={
        "action": "save_ranges", "revision": after_dates["revision"], "csrf": csrf(page),
        "4_end": "19", "grade-4-session-1": "2030-01-01", "current_school_year": "2030/2031",
    })
    assert ranges.status_code == 302 and urlsplit(ranges.location).fragment == "participant-ids"
    after_ranges = state.settings()
    assert after_ranges["ranges"][0]["end"] == 19
    assert after_ranges["sessions"] == after_dates["sessions"]
    assert after_ranges["current_school_year"] == "2026/2027"


def test_individual_session_editor_rejects_other_grades_and_keeps_invalid_input_open(app):
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    page = client.get("/dashboard/settings?grade=4")
    before = state.settings()
    form = {"action": "save_session", "revision": before["revision"], "csrf": csrf(page),
            "session_id": "grade-5-session-1", "name": "Moved", "date": "2026-10-04"}
    assert client.post("/dashboard/settings?grade=4", data=form).status_code == 400
    assert state.settings() == before
    invalid = client.post("/dashboard/settings?grade=4", data={
        **form, "session_id": "grade-4-session-1", "name": "Needs a date", "date": "2026-02-30"})
    assert invalid.status_code == 400 and 'id="grade-4-session-1" open' in invalid.text
    assert 'value="Needs a date"' in invalid.text
    assert state.settings() == before


def test_researcher_can_visualize_or_download_participant_sessions_and_runs(app):
    configure(app)
    expected = {write_run(app)[0], write_run(app, suffix="repeat", answers=1)[0],
                write_run(app, suffix="later", date="2026-10-02")[0]}
    other = write_run(app, uid="21")[0]
    client = app.test_client()
    login(client)
    overview = client.get("/dashboard")
    assert b"Visualize logs</a>" in overview.data and b'aria-label="Download all 4th grade"' in overview.data
    assert not any(link.path.endswith("/exports/all") for link in dashboard_links(overview))
    assert b"export-menu" not in overview.data
    view_links = [link for link in dashboard_links(overview) if parse_qs(link.query).get("view") == ["logs"]
                  and "manage" not in parse_qs(link.query)]
    assert len(view_links) == 1
    participant = client.get(view_links[0].geturl())
    run_links = [link for link in dashboard_links(participant) if "/runs/" in link.path]
    assert {link.path.rsplit("/", 1)[-1] for link in run_links} == expected
    assert other.encode() not in participant.data
    exports = [link for link in dashboard_links(participant) if link.path.endswith("/run")]
    assert len(exports) == 3
    for link in exports:
        _, manifest = archive(client.get(link.geturl()))
        assert {run["run_id"] for run in manifest["runs"]} == set(parse_qs(link.query)["run"])
    row = next(row for row in re.findall(r'<tr>(.*?)</tr>', overview.text, re.S)
               if f'/participants/v2/{identity("1")}' in row)
    assert 'type="checkbox"' in row and "/exports/" not in row
    z, manifest = archive(download_selected_participants(client, overview, "v2:" + identity("1")))
    assert {run["run_id"] for run in manifest["runs"]} == expected
    original_root = Path(app.config["RESEARCH_LOG_DIR"])
    logs = [item for item in manifest["files"] if item["source_name"].endswith(".log")]
    assert len(logs) == 12
    for item in logs:
        assert item["included"]
        assert z.read(item["archive_name"]) == (original_root / item["source_name"]).read_bytes()
    assert client.get(f"/dashboard/participants/v2/{identity('1')}?view=logs&session=grade-5-session-1").status_code == 404


def test_original_log_viewer_uses_the_selected_source_with_pagination_and_escaping(app):
    key, root, stem = write_run(app)
    task_file = root / f"{stem}_task1_topic3.log"
    payload = '<script>alert("source")</script>'
    with task_file.open("a") as target:
        target.write((json.dumps({"uid": "1", "type": payload, "task_number": 1,
                                  "marker": "task-copy-only"}) + "\n") * 205)
        target.write('not JSON\n{"type":')
    client = app.test_client()
    login(client)
    run_page = client.get(f"/dashboard/runs/{key}?task=1")
    source_id = identity("v2\0" + task_file.name)
    path = f"/dashboard/runs/{key}/logs/{source_id}/view"
    assert any(link.path == path for link in dashboard_links(run_page))
    first = client.get(path)
    assert first.status_code == 200
    assert "no-store" in first.headers["Cache-Control"]
    assert first.text.count('class="event-row"') == 100
    assert b"task-copy-only" in first.data and b"&lt;script&gt;" in first.data
    assert b"<script>alert" not in first.data
    assert b"Answer for 1 task 2" not in first.data and b"Answer for 1 task 3" not in first.data
    assert b"task-copy-only" not in run_page.data  # Combined events still use the full log once.
    third = client.get(path + "?page=3&lang=it")
    assert third.text.count('class="event-row"') == 9
    assert "Visualizza log" in third.text and "Scarica log" in third.text
    assert sum(row["problem"] is not None for row in app.extensions["research"]["index"].event_page(
        app.extensions["research"]["index"].run(key, app.extensions["research"]["state"].settings()),
        source_id=source_id, page=3)[0]) == 2
    download = next(link for link in dashboard_links(third) if link.path.endswith("/logs/" + source_id))
    downloaded = client.get(download.geturl())
    assert downloaded.data == task_file.read_bytes()
    downloaded.close()
    for value in ("0", "-1", "invalid", "1000001"):
        assert client.get(path + "?page=" + value).status_code == 400
    _, _, other_stem = write_run(app, uid="21")
    app.extensions["research"]["index"].refresh(force=True)
    other_id = identity("v2\0" + f"{other_stem}_FULL.log")
    metadata_id = identity("v2\0" + f"{stem}.run.json")
    assert client.get(f"/dashboard/runs/{key}/logs/{other_id}/view").status_code == 404
    assert client.get(f"/dashboard/runs/{key}/logs/{metadata_id}/view").status_code == 404
    assert client.get(f"/dashboard/runs/{key}/logs/unknown/view").status_code == 404


def test_original_log_viewer_refuses_changed_or_symlinked_sources(app, tmp_path):
    key, root, stem = write_run(app)
    path = root / f"{stem}_FULL.log"
    source_id = identity("v2\0" + path.name)
    client = app.test_client()
    login(client)
    url = f"/dashboard/runs/{key}/logs/{source_id}/view"
    assert client.get(url).status_code == 200
    with path.open("a") as target:
        target.write(json.dumps({"type": "PRIVATE NEW DATA"}) + "\n")
    stale = client.get(url)
    assert b"PRIVATE NEW DATA" not in stale.data and b"Refresh saved data" in stale.data
    outside = tmp_path / "private.log"
    outside.write_text('PRIVATE OUTSIDE DATA')
    path.unlink()
    path.symlink_to(outside)
    symlinked = client.get(url)
    assert b"PRIVATE OUTSIDE DATA" not in symlinked.data
    assert b"The source file cannot be read" in symlinked.data


def test_grade_downloads_follow_navigation_and_keep_complete_histories(app):
    configure(app)
    expected = {
        "4": {write_run(app)[0], write_run(app, suffix="later", date="2026-10-02")[0]},
        "5": {write_run(app, uid="21")[0], write_run(app, uid="21", suffix="later", date="2026-10-02")[0]},
    }
    write_run(app, collection="legacy")
    client = app.test_client()
    login(client)
    for grade in ("4", "5", "all"):
        query = f"grade={grade}" + (f"&session=grade-{grade}-session-1" if grade != "all" else "")
        response = client.get("/dashboard?" + query)
        expected_grades = {"4", "5"} if grade == "all" else {grade}
        links = [link for link in dashboard_links(response) if link.path.endswith("/exports/grade")]
        assert {parse_qs(link.query)["grade"][0] for link in links} == expected_grades
        assert len(links) == len(expected_grades)
        assert all(f'aria-label="Download all {value}th grade"' in response.text for value in expected_grades)
        for link in links:
            query = parse_qs(link.query)
            assert "session" not in query
            z, manifest = archive(client.get(link.geturl()))
            selected_grade = query["grade"][0]
            assert {run["run_id"] for run in manifest["runs"]} == expected[selected_grade]
            assert {run["grade"] for run in manifest["runs"]} == {selected_grade}
            assert {run["study_session"]["number"] for run in manifest["runs"]} == {1, 2}
            root = Path(app.config["RESEARCH_LOG_DIR"])
            for item in manifest["files"]:
                assert item["included"] and z.read(item["archive_name"]) == (root / item["source_name"]).read_bytes()


def test_creating_and_redating_sessions_preserves_history_and_source_files(app):
    configure(app)
    old_key, root, _ = write_run(app)
    new_key, _, _ = write_run(app, suffix="new-date", date="2026-10-04")
    original = {path.name: path.read_bytes() for path in root.iterdir()}
    state = app.extensions["research"]["state"]
    before = state.settings()
    client = app.test_client()
    login(client, lang="it")
    settings_page = client.get("/dashboard/settings?grade=4&lang=it")
    created = client.post("/dashboard/settings?lang=it", data={
        "action": "add_session", "grade": "4", "date": "2026-10-04",
        "revision": before["revision"], "csrf": csrf(settings_page),
    })
    assert created.status_code == 302
    query = parse_qs(urlsplit(created.location).query)
    assert query == {"grade": ["4"], "session": ["grade-4-session-4"], "lang": ["it"]}
    after = state.settings()
    assert after["sessions"][:6] == before["sessions"]
    assert after["ranges"] == before["ranges"]
    assert len(after["sessions"]) == 7 and after["revision"] == before["revision"] + 1
    overview = client.get(created.location)
    assert "Sessione 4 · 2026-10-04" in re.sub(r'<[^>]+>', '', overview.text)
    session_download = next(link for link in dashboard_links(overview) if link.path.endswith("/exports/grade_session"))
    _, manifest = archive(client.get(session_download.geturl()))
    assert {run["run_id"] for run in manifest["runs"]} == {new_key}
    assert manifest["runs"][0]["study_session"]["number"] == 4
    participant = client.get(f"/dashboard/participants/v2/{identity('1')}?view=logs&session=grade-4-session-4")
    assert new_key.encode() in participant.data and old_key.encode() not in participant.data
    old_view = client.get("/dashboard?session=grade-4-session-1")
    old_download = next(link for link in dashboard_links(old_view) if link.path.endswith("/exports/grade_session"))
    assert {run["run_id"] for run in archive(client.get(old_download.geturl()))[1]["runs"]} == {old_key}
    settings_page = client.get("/dashboard/settings")
    assert 'id="grade-4-session-4"' in settings_page.text
    assert 'id="grade-5-session-4"' not in settings_page.text
    changed = client.post("/dashboard/settings", data={
        "action": "save_session", "session_id": "grade-4-session-4", "name": "", "date": "2026-10-05",
        "revision": after["revision"], "csrf": csrf(settings_page),
    })
    assert changed.status_code == 302
    latest = state.settings()
    assert latest["sessions"][:6] == before["sessions"] and latest["ranges"] == before["ranges"]
    assert latest["sessions"][-1]["id"] == "grade-4-session-4"
    assert latest["sessions"][-1]["date"] == "2026-10-05"
    assert all(path.read_bytes() == original[path.name] for path in root.iterdir())
    with state.connect() as db:
        saved_history = [json.loads(row[0]) for row in db.execute("SELECT body FROM settings ORDER BY revision")]
    assert saved_history[-2]["sessions"][-1]["date"] == "2026-10-04"
    assert saved_history[-1]["sessions"][-1]["date"] == "2026-10-05"


@pytest.mark.parametrize("grade,study_date,error", [
    ("4", "2026-10-01", "Two sessions of the same grade"),
    ("4", "2026-02-30", "Use valid calendar dates"),
    ("4", "", "Use valid calendar dates"),
    ("unknown", "2026-10-04", "Invalid study-session configuration"),
])
def test_new_session_rejects_invalid_or_overlapping_dates_without_changes(app, grade, study_date, error):
    configure(app)
    state = app.extensions["research"]["state"]
    before = state.settings()
    client = app.test_client()
    login(client)
    response = client.post("/dashboard/settings", data={
        "action": "add_session", "grade": grade, "date": study_date,
        "revision": before["revision"], "csrf": csrf(client.get("/dashboard/settings")),
    })
    assert response.status_code == 400 and error in response.text
    assert state.settings() == before


def test_custom_session_name_is_editable_without_changing_session_identity_or_logs(app):
    configure(app)
    run_id, root, _ = write_run(app, date="2026-10-04")
    original = {path.name: path.read_bytes() for path in root.iterdir()}
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    settings_page = client.get("/dashboard/settings?grade=4")
    assert settings_page.text.index('id="school-year"') < settings_page.text.index('id="new-session"')
    assert settings_page.text.index('id="session-history"') < settings_page.text.index('id="new-session"')
    assert 'id="new-name" name="name"' in settings_page.text
    before = state.settings()
    created = client.post("/dashboard/settings?grade=4", data={
        "action": "add_session", "grade": "4", "date": "2026-10-04", "name": " Baseline <Round 1> ",
        "revision": before["revision"], "csrf": csrf(settings_page),
    })
    assert created.status_code == 302
    session = state.settings()["sessions"][-1]
    assert session["id"] == "grade-4-session-4" and session["name"] == "Baseline <Round 1>"
    overview = client.get(created.location)
    assert "Baseline &lt;Round 1&gt;" in overview.text
    assert "Baseline <Round 1>" not in overview.text
    participant = client.get(f"/dashboard/participants/v2/{identity('1')}?session={session['id']}")
    assert "Baseline &lt;Round 1&gt;" in participant.text
    grade_session = next(link for link in dashboard_links(overview) if link.path.endswith("/exports/grade_session"))
    _, manifest = archive(client.get(grade_session.geturl()))
    assert {run["run_id"] for run in manifest["runs"]} == {run_id}
    assert manifest["runs"][0]["study_session"]["name"] == "Baseline <Round 1>"
    settings_page = client.get("/dashboard/settings?grade=4")
    current = state.settings()
    changed = client.post("/dashboard/settings?grade=4", data={
        "action": "save_session", "session_id": "grade-4-session-4", "name": "Follow-up", "date": session["date"],
        "revision": current["revision"], "csrf": csrf(settings_page),
    })
    assert changed.status_code == 302
    renamed = state.settings()["sessions"][-1]
    assert renamed["id"] == session["id"] and renamed["date"] == session["date"]
    assert renamed["name"] == "Follow-up"
    assert "Follow-up" in client.get(created.location).text
    assert all(path.read_bytes() == original[path.name] for path in root.iterdir())


@pytest.mark.parametrize("name", ["x" * 81, "bad\nname"])
def test_session_names_reject_oversized_or_multiline_values(app, name):
    state = app.extensions["research"]["state"]
    before = state.settings()
    client = app.test_client()
    login(client)
    response = client.post("/dashboard/settings", data={
        "action": "add_session", "grade": "4", "date": "2026-10-04", "name": name,
        "revision": before["revision"], "csrf": csrf(client.get("/dashboard/settings")),
    })
    assert response.status_code == 400 and b"Use a session name of at most 80 characters" in response.data
    assert state.settings() == before


def test_new_session_requires_auth_csrf_and_current_revision(app):
    state = app.extensions["research"]["state"]
    before = state.settings()
    form = {"action": "add_session", "grade": "4", "date": "2026-10-04", "revision": before["revision"]}
    anonymous = app.test_client()
    assert anonymous.post("/dashboard/settings", data=form).status_code == 302
    client = app.test_client()
    login(client)
    assert client.post("/dashboard/settings", data=form).status_code == 400
    assert state.settings() == before
    form["csrf"] = csrf(client.get("/dashboard/settings"))
    assert client.post("/dashboard/settings", data=form).status_code == 302
    after = state.settings()
    form["date"] = "2026-10-05"
    stale = client.post("/dashboard/settings", data=form)
    assert stale.status_code == 400 and b"Another researcher" in stale.data
    assert state.settings() == after


def test_hundred_sessions_remain_browsable_exportable_and_capped_per_grade(app):
    state = app.extensions["research"]["state"]
    settings = state.settings()
    for grade in ("4", "5"):
        settings["sessions"].extend({"id": f"grade-{grade}-session-{number}", "grade": grade,
                                     "number": number, "date": (date(2026, 1, 1) + timedelta(days=number - 1)).isoformat()}
                                    for number in range(4, 100))
    state.save_settings(settings, settings["revision"])
    study_date = (date(2026, 1, 1) + timedelta(days=99)).isoformat()
    key, _, _ = write_run(app, date=study_date)
    client = app.test_client()
    login(client)
    csrf_token = csrf(client.get("/dashboard/settings"))
    created = client.post("/dashboard/settings", data={
        "action": "add_session", "grade": "4", "date": study_date,
        "revision": state.settings()["revision"], "csrf": csrf_token,
    })
    assert created.status_code == 302
    overview = client.get(created.location)
    assert "Session 100 · " + study_date in re.sub(r'<[^>]+>', '', overview.text)
    assert 'id="session-filter"' not in overview.text
    history_link = next(link for link in dashboard_links(overview) if link.fragment == "session-history")
    history_page = client.get(history_link.geturl())
    assert history_page.status_code == 200 and 'id="grade-4-session-100"' in history_page.text
    assert len(re.findall(r'<th\b', overview.text.split("<thead>")[1].split("</thead>")[0])) == 4
    downloaded = next(link for link in dashboard_links(overview) if link.path.endswith("/exports/grade_session"))
    _, manifest = archive(client.get(downloaded.geturl()))
    assert {run["run_id"] for run in manifest["runs"]} == {key}
    assert manifest["available_sessions"][0]["id"] == "grade-4-session-100"
    before = state.settings()
    overflow = client.post("/dashboard/settings", data={
        "action": "add_session", "grade": "4", "date": "2027-01-01",
        "revision": before["revision"], "csrf": csrf_token,
    })
    assert overflow.status_code == 400 and b"up to 100 sessions" in overflow.data
    assert state.settings() == before
    available = client.get("/dashboard/settings?grade=4")
    assert re.search(r'<a href="[^"]*section=sessions&amp;grade=4[^"]*"\s+aria-current="page"', available.text)
    assert "This grade has 100 sessions" in available.text
    # A full grade must not block the other grade's next session on the same date.
    assert client.post("/dashboard/settings", data={
        "action": "add_session", "grade": "5", "date": study_date,
        "revision": before["revision"], "csrf": csrf_token,
    }).status_code == 302
    fourth_history = client.get("/dashboard/settings?grade=4")
    fifth_history = client.get("/dashboard/settings?grade=5")
    assert 'id="grade-4-session-100"' in fourth_history.text and 'id="grade-5-session-100"' not in fourth_history.text
    assert 'id="grade-4-session-1"' not in fourth_history.text
    assert 'id="grade-5-session-100"' in fifth_history.text and 'id="grade-4-session-100"' not in fifth_history.text
    assert 'id="grade-5-session-1"' not in fifth_history.text
    assert fourth_history.text.count('class="settings-session-item"') == 10
    fourth_oldest = client.get("/dashboard/settings?grade=4&page=10")
    fifth_oldest = client.get("/dashboard/settings?grade=5&page=10")
    assert 'id="grade-4-session-1"' in fourth_oldest.text
    assert 'id="grade-5-session-1"' in fifth_oldest.text
    assert 'id="grade-4-session-100"' not in fourth_oldest.text
    older_edit = client.post("/dashboard/settings?grade=4&page=10", data={
        "action": "save_session", "session_id": "grade-4-session-1", "name": "First visit",
        "date": before["sessions"][0]["date"], "revision": state.settings()["revision"],
        "csrf": csrf(fourth_oldest),
    })
    assert older_edit.status_code == 302
    assert parse_qs(urlsplit(older_edit.location).query)["page"] == ["10"]
    assert state.settings()["sessions"][0]["name"] == "First visit"
    assert 'id="grade-4-session-1" open' in client.get(older_edit.location).text
    assert len(state.settings()["sessions"]) == 200
    assert "This grade has 100 sessions" in fourth_history.text
    third = state.settings()
    third["sessions"].extend({"id": f"grade-3-session-{number}", "grade": "3", "number": number,
                               "date": (date(2026, 1, 1) + timedelta(days=number - 1)).isoformat()}
                              for number in range(1, 101))
    state.save_settings(third, third["revision"])
    history = client.get("/dashboard/settings")
    assert len(state.settings()["sessions"]) == 300
    assert "This grade has 100 sessions" in history.text


def test_concurrent_session_creation_does_not_overwrite_history(app):
    state = app.extensions["research"]["state"]
    before = state.settings()
    def create(study_date):
        try:
            return state.add_study_session("4", study_date, before["revision"])["id"]
        except ValueError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create, ["2026-10-04", "2026-10-05"]))
    assert sorted(outcomes) == ["grade-4-session-4", "settings_changed"]
    after = state.settings()
    assert after["sessions"][:6] == before["sessions"]
    assert len(after["sessions"]) == 7 and after["revision"] == before["revision"] + 1


def test_all_participants_selector_shows_both_grades_and_complete_histories(app):
    configure(app)
    expected = {
        "1": {write_run(app)[0], write_run(app, suffix="repeat", answers=1)[0],
              write_run(app, suffix="later", answers=2, date="2026-10-02")[0]},
        "21": {write_run(app, uid="21")[0]},
        "001": {write_run(app, uid="001")[0]},
    }
    write_run(app, uid="legacy-only", collection="legacy")
    conflict, root, stem = write_run(app, suffix="conflict")
    with (root / f"{stem}_FULL.log").open("a") as target:
        target.write(json.dumps({"uid": "21", "type": "querySubmitted"}) + "\n")
    client = app.test_client()
    login(client)
    filtered = client.get("/dashboard?grade=4&session=grade-4-session-1")
    assert '<nav class="dashboard-grades"' in filtered.text
    assert any(parse_qs(link.query).get("grade") == ["all"] for link in dashboard_links(filtered))
    response = client.get("/dashboard?grade=all")
    assert response.status_code == 200 and "no-store" in response.headers["Cache-Control"]
    navigation = re.search(r'<nav class="dashboard-grades".*?</nav>', response.text, re.S).group()
    assert re.search(r'<a[^>]*grade=all[^>]*aria-current="page"[^>]*>All participants</a>', navigation)
    assert b"Grade at collection</th>" in response.data and b"Status</th>" in response.data
    ids = re.findall(r'class="participant-link"[^>]*>([^<]+)</a>', response.text)
    assert set(ids) == {str(number) for number in range(1, 41)} | {"001"}
    assert len(ids) == len(set(ids))
    assert b"legacy-only" not in response.data
    assert b"Records with unknown or conflicting participant identity" in response.data
    assert conflict.encode() in response.data
    assert b"Unassigned" not in response.data and b"Legacy archive" not in response.data
    assert 'id="session-filter"' not in response.text
    rows = re.findall(r'<tr>(.*?)</tr>', response.text, re.S)
    for uid, keys in expected.items():
        token = identity(uid)
        row = next(row for row in rows if f'/participants/v2/{token}' in row)
        assert "Visualize logs</a>" in row and 'type="checkbox"' in row
        assert "/exports/" not in row
        if uid == "1":
            assert "4th Grade" in row and "1/3 completed" in row
        elif uid == "21":
            assert "5th Grade" in row and "1/1 completed" in row
        links = dashboard_links(types.SimpleNamespace(text=row))
        view = next(link for link in links if parse_qs(link.query).get("view") == ["logs"])
        viewed = client.get(view.geturl())
        assert {link.path.rsplit("/", 1)[-1] for link in dashboard_links(viewed) if "/runs/" in link.path} == keys
        _, manifest = archive(download_selected_participants(client, response, "v2:" + token))
        assert "study_session_id" not in manifest["selection"]
        assert {run["run_id"] for run in manifest["runs"]} == keys
        assert {run["participant_id"] for run in manifest["runs"]} == {uid}
    assert client.get("/dashboard?grade=all&session=grade-4-session-1").status_code == 404
    assert client.get("/dashboard?grade=all&session=grade-5-session-1").status_code == 404


def test_all_participants_empty_roster_translation_and_refresh(app):
    client = app.test_client()
    assert client.get("/dashboard?grade=all").status_code == 302
    login(client, lang="it")
    response = client.get("/dashboard?grade=all&lang=it")
    assert response.status_code == 200
    assert "Tutti i partecipanti" in response.text and "Classe durante la raccolta</th>" in response.text
    ids = re.findall(r'class="participant-link"[^>]*>([^<]+)</a>', response.text)
    assert ids == [str(number) for number in range(1, 41)]
    assert response.text.count('<span class="badge no_data">Senza dati salvati</span>') == 40
    assert 'type="checkbox"' not in response.text and "Scarica log</button>" not in response.text
    history = next(link for link in dashboard_links(response) if link.fragment == "session-history")
    creation = next(link for link in dashboard_links(response) if link.fragment == "new-session")
    assert client.get(history.geturl()).status_code == 200
    assert parse_qs(creation.query)["new"] == ["1"]
    creation_page = client.get(creation.geturl())
    assert creation_page.status_code == 200 and 'id="new-session" open' in creation_page.text
    refreshed = client.post("/dashboard/refresh?lang=it", data={
        "csrf": csrf(response), "grade": "all", "collection": "v2",
    })
    assert parse_qs(urlsplit(refreshed.location).query) == {"collection": ["v2"], "grade": ["all"], "lang": ["it"]}


def add_history_rule(state, **values):
    settings = state.settings()
    rule = {"id": f"{len(settings['historical_grades']) + 1:024x}", "collection": "legacy",
            "grade": "3", "school_year": "2025/2026", "date_from": "2025-09-01",
            "date_to": "2026-07-31", "start": 1, "end": 20, "prefix": "", "width": 0,
            **values}
    settings["historical_grades"].append(rule)
    state.save_settings(settings, settings["revision"])
    return rule


def test_historical_grade_categories_and_downloads_preserve_both_cohorts(app):
    configure(app)
    current4, _, _ = write_run(app)
    current5, _, _ = write_run(app, uid="21")
    old3, old_root, _ = write_run(app, collection="legacy", date="2025-10-01", metadata=False)
    old4, _, _ = write_run(app, uid="21", collection="legacy", date="2025-10-01", metadata=False)
    unassigned, _, _ = write_run(app, uid="99", collection="legacy", date="2025-10-01", metadata=False)
    originals = {path.name: path.read_bytes() for path in old_root.iterdir()}
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    assert any(parse_qs(link.query).get("grade") == ["3"] for link in dashboard_links(client.get("/dashboard")))
    empty = client.get("/dashboard?grade=3")
    assert b"No participants in this grade" in empty.data
    assert any(link.path == "/dashboard/settings" and parse_qs(link.query).get("section") == ["participants"]
               for link in dashboard_links(empty))
    add_history_rule(state)
    add_history_rule(state, grade="4", start=21, end=40)
    history_before = state.settings()["historical_grades"]
    session = client.post("/dashboard/settings", data={"action": "add_session", "grade": "3", "date": "2025-10-01",
                          "revision": state.settings()["revision"], "csrf": csrf(client.get("/dashboard/settings"))})
    assert session.status_code == 302
    assert parse_qs(urlsplit(session.location).query)["session"] == ["grade-3-session-1"]
    assert state.settings()["historical_grades"] == history_before
    third = client.get("/dashboard?grade=3&school_year=2025/2026&session=grade-3-session-1")
    assert third.status_code == 200
    assert b"Historical records" in third.data and b"2025/2026" in third.data
    ids = re.findall(r'class="participant-link"[^>]*>([^<]+)</a>', third.text)
    assert ids == ["1"]
    links = dashboard_links(third)
    z, manifest = archive(download_selected_participants(client, third, "legacy:" + identity("1")))
    assert {run["collection"] for run in manifest["runs"]} == {"legacy"}
    assert {run["run_id"] for run in manifest["runs"]} == {old3}
    assert manifest["runs"][0]["grade"] == "3" and manifest["runs"][0]["school_year"] == "2025/2026"
    assert manifest["runs"][0]["grade_source"] == "historical_assignment"
    assert manifest["runs"][0]["historical_assignment_id"] == history_before[0]["id"]
    for item in manifest["files"]:
        assert item["included"] and z.read(item["archive_name"]) == originals[item["source_name"]]
    viewer = next(link for link in links if parse_qs(link.query).get("view") == ["logs"])
    viewed = client.get(viewer.geturl())
    assert old3.encode() in viewed.data and current4.encode() not in viewed.data
    fourth_url = next(link for link in links if link.path in ("/dashboard", "/dashboard/")
                      and parse_qs(link.query).get("grade") == ["4"])
    fourth_links = dashboard_links(client.get(fourth_url.geturl()))
    _, grade_manifest = archive(client.get(next(link for link in fourth_links if link.path.endswith("/exports/grade")
                                                and parse_qs(link.query)["grade"] == ["4"]).geturl()))
    assert {run["run_id"] for run in grade_manifest["runs"]} == {current4, old4}
    all_view = client.get("/dashboard?grade=all")
    assert all_view.text.count('class="participant-link"') == 42
    assert b"Historical records" in all_view.data
    assert not any(link.path.endswith("/exports/all") for link in dashboard_links(all_view))
    assert client.get("/dashboard/exports/all?collection=study").status_code == 404
    grade_downloads = {parse_qs(link.query)["grade"][0]: link for link in dashboard_links(all_view)
                       if link.path.endswith("/exports/grade")}
    assert set(grade_downloads) == {"3", "4", "5"}
    for selected_grade, expected in {"3": {old3}, "4": {current4, old4}, "5": {current5}}.items():
        _, grade_manifest = archive(client.get(grade_downloads[selected_grade].geturl()))
        assert {run["run_id"] for run in grade_manifest["runs"]} == expected
        assert unassigned not in expected
    # Identical IDs in different collections remain separate until their continuity is confirmed.
    assert client.get(f"/dashboard/exports/participant?collection=study&participant={identity('1')}").status_code == 404
    _, current_manifest = archive(client.get(f"/dashboard/exports/participant?collection=v2&participant={identity('1')}"))
    assert {run["run_id"] for run in current_manifest["runs"]} == {current4}
    old_year = client.get("/dashboard?grade=all&school_year=2025/2026")
    assert old_year.text.count('class="participant-link"') == 2
    refreshed = client.post("/dashboard/refresh", data={"csrf": csrf(old_year), "grade": "all", "collection": "study", "school_year": "2025/2026"})
    assert parse_qs(urlsplit(refreshed.location).query)["school_year"] == ["2025/2026"]
    assert all(path.read_bytes() == originals[path.name] for path in old_root.iterdir())


def test_recorded_grade_and_year_survive_promotion_and_conflicting_assignment(app):
    key, root, stem = write_run(app, date="2025-10-01")
    sidecar = root / f"{stem}.run.json"
    metadata = json.loads(sidecar.read_text())
    metadata.update(grade_at_collection="3", school_year_at_collection="2025/2026")
    sidecar.write_text(json.dumps(metadata))
    original = sidecar.read_bytes()
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    first = client.get("/dashboard?grade=3")
    assert b"Current grade: 4th Grade" in first.data
    assert any(link.path.endswith("/exports/grade") and parse_qs(link.query)["grade"] == ["3"] for link in dashboard_links(first))
    settings = state.settings()
    settings["ranges"][0].update(start=41, end=60)
    settings["ranges"][1].update(start=1, end=20)
    settings["current_school_year"] = "2027/2028"
    state.save_settings(settings, settings["revision"])
    promoted = client.get("/dashboard?grade=3&school_year=2025/2026")
    assert b"Current grade: 5th Grade" in promoted.data
    add_history_rule(state, collection="v2", grade="4")
    run = app.extensions["research"]["index"].run(key, state.settings())
    assert run["grade"] == "3" and run["current_grade"] == "5"
    assert run["school_year"] == "2025/2026" and run["grade_source"] == "recorded"
    assert "historical_grade_conflict" in run["issues"]
    assert sidecar.read_bytes() == original
    detail = client.get(f"/dashboard/runs/{key}")
    assert b"recorded grade is preserved" in detail.data
    assert b"3rd Grade" in detail.data and b"5th Grade" in detail.data and b"2025/2026" in detail.data
    _, manifest = archive(download_selected_participants(client, promoted, "v2:" + identity("1")))
    assert {run["run_id"] for run in manifest["runs"]} == {key}
    assert manifest["runs"][0]["school_year"] == "2025/2026"
    fifth = client.get("/dashboard?grade=5")
    row = next(row for row in re.findall(r'<tr>(.*?)</tr>', fifth.text, re.S) if f'/participants/v2/{identity("1")}' in row)
    assert 'class="badge no_data"' in row and 'class="dashboard-no-actions muted"' in row
    assert "Download logs" not in row and "completed" not in row


@pytest.mark.parametrize("recorded_year,assigned_year,expected_year,source,issue", [
    ("2025/2026", "2024/2025", "2025/2026", "recorded", "historical_school_year_conflict"),
    ("invalid", "2025/2026", "2025/2026", "historical_assignment", "invalid_recorded_school_year"),
])
def test_historical_school_year_conflicts_and_invalid_metadata_preserve_sources(
        app, recorded_year, assigned_year, expected_year, source, issue):
    key, root, stem = write_run(app, date="2025-10-01")
    sidecar = root / f"{stem}.run.json"
    metadata = json.loads(sidecar.read_text())
    metadata.update(grade_at_collection="3", school_year_at_collection=recorded_year)
    sidecar.write_text(json.dumps(metadata))
    original = sidecar.read_bytes()
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    add_history_rule(state, collection="v2", school_year=assigned_year)
    overview = client.get(f"/dashboard?grade=3&school_year={expected_year}")
    assert overview.status_code == 200 and 'class="participant-link"' in overview.text
    zipped, manifest = archive(download_selected_participants(client, overview, "v2:" + identity("1")))
    assert len(manifest["runs"]) == 1
    run = manifest["runs"][0]
    assert run["run_id"] == key and run["school_year"] == expected_year
    assert run["school_year_source"] == source and issue in run["issues"]
    exported = next(item for item in manifest["files"] if item["source_name"] == sidecar.name)
    assert zipped.read(exported["archive_name"]) == original and sidecar.read_bytes() == original


def test_historical_assignments_use_exact_ids_dates_and_collection(app):
    one, _, _ = write_run(app, collection="legacy", uid="1", date="2025-10-01", metadata=False)
    padded, _, _ = write_run(app, collection="legacy", uid="01", date="2025-10-01", metadata=False)
    outside, _, _ = write_run(app, collection="legacy", uid="01", suffix="outside", date="2026-08-01", metadata=False)
    current, _, _ = write_run(app, uid="01", date="2025-10-01", metadata=False)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    add_history_rule(state, width=2)
    app.extensions["research"]["index"].refresh(force=True)
    classified = {key: app.extensions["research"]["index"].run(key, state.settings()) for key in (one, padded, outside, current)}
    assert classified[padded]["grade"] == "3"
    assert all(classified[key]["grade"] is None for key in (one, outside, current))
    history_page = client.get("/dashboard/settings")
    assert "Historical grade assignments" not in history_page.text
    rule_id = state.settings()["historical_grades"][0]["id"]
    before = state.settings()
    assert client.post("/dashboard/settings", data={"action": "remove_historical_grade", "revision": before["revision"],
                       "rule_id": rule_id, "csrf": csrf(history_page)}).status_code == 400
    assert state.settings()["historical_grades"][0]["id"] == rule_id
    updated = state.settings()
    updated["historical_grades"] = []
    state.save_settings(updated, updated["revision"])
    assert app.extensions["research"]["index"].run(padded, state.settings())["grade"] is None
    with state.connect() as db:
        prior = json.loads(db.execute("SELECT body FROM settings WHERE revision = ?", (before["revision"],)).fetchone()[0])
    assert prior["historical_grades"][0]["id"] == rule_id


@pytest.mark.parametrize("changes", [
    {"school_year": "2025/2025"}, {"source_collection": "unknown"}, {"historical_grade": "6"},
    {"date_from": "2026-09-01", "date_to": "2026-01-01"}, {"history_end": 2000},
])
def test_invalid_historical_assignments_do_not_change_settings(app, changes):
    state = app.extensions["research"]["state"]
    before = state.settings()
    names = {"source_collection": "collection", "historical_grade": "grade",
             "history_end": "end"}
    converted = {names.get(key, key): value for key, value in changes.items()}
    with pytest.raises(ValueError):
        add_history_rule(state, **converted)
    assert state.settings() == before


def test_saved_historical_assignments_still_reject_overlapping_rules(app):
    state = app.extensions["research"]["state"]
    add_history_rule(state)
    before = state.settings()
    with pytest.raises(ValueError, match="overlapping_historical_grades"):
        add_history_rule(state, start=10, end=25)
    assert state.settings() == before


def test_historical_assignment_editing_is_hidden_while_saved_rules_remain_active(app):
    state = app.extensions["research"]["state"]
    saved_rule = add_history_rule(state)
    before = state.settings()
    form = {"action": "add_historical_grade", "revision": before["revision"]}
    client = app.test_client()
    assert client.post("/dashboard/settings", data=form).status_code == 302
    login(client)
    page = client.get("/dashboard/settings")
    assert "Historical grade assignments" not in page.text
    assert 'value="add_historical_grade"' not in page.text
    assert 'value="remove_historical_grade"' not in page.text
    assert client.post("/dashboard/settings", data=form).status_code == 400
    form["csrf"] = csrf(page)
    assert client.post("/dashboard/settings", data=form).status_code == 400
    assert client.post("/dashboard/settings", data={**form, "action": "remove_historical_grade",
                                                    "rule_id": saved_rule["id"]}).status_code == 400
    assert state.settings() == before
    assert client.post("/dashboard/settings", data={"action": "save_year", "revision": before["revision"],
                                                    "csrf": csrf(page), "current_school_year": "2026/2027"}).status_code == 302
    assert state.settings()["historical_grades"] == [saved_rule]


def test_new_run_records_school_year_without_rewriting_previous_metadata(app):
    state = app.extensions["research"]["state"]
    settings = state.settings()
    settings["current_school_year"] = "2026/2027"
    state.save_settings(settings, settings["revision"])
    root = Path(app.config["RESEARCH_LOG_DIR"])
    record_run(root, state, "1", "technical", "year-test", ["1", "2", "3"], {})
    path = next(root.glob("*.run.json"))
    original = path.read_bytes()
    assert json.loads(original)["school_year_at_collection"] == "2026/2027"
    assert json.loads(original)["study_id_at_collection"] == DEFAULT_STUDY_ID
    settings = state.settings()
    settings["current_school_year"] = "2027/2028"
    state.save_settings(settings, settings["revision"])
    index = app.extensions["research"]["index"]
    index.refresh(force=True)
    run = index.summaries(state.settings())[0]
    assert run["school_year"] == "2026/2027" and run["study_id"] == DEFAULT_STUDY_ID
    assert path.read_bytes() == original


def test_future_study_id_does_not_mix_with_current_participants_or_downloads(app):
    current, _, _ = write_run(app)
    future, root, stem = write_run(app, suffix="another-study")
    sidecar = root / f"{stem}.run.json"
    metadata = json.loads(sidecar.read_text())
    metadata["study_id_at_collection"] = "future-school-study"
    sidecar.write_text(json.dumps(metadata))
    client = app.test_client()
    login(client)
    overview = client.get("/dashboard?grade=all")
    participant = next(link for link in dashboard_links(overview)
                       if link.path.endswith(f"/participants/v2/{identity('1')}") and parse_qs(link.query).get("view") == ["logs"])
    shown = client.get(participant.geturl())
    assert current.encode() in shown.data and future.encode() not in shown.data
    download = next(link for link in dashboard_links(overview) if link.path.endswith("/exports/grade")
                    and parse_qs(link.query)["grade"] == ["4"])
    _, manifest = archive(client.get(download.geturl()))
    assert {run["run_id"] for run in manifest["runs"]} == {current}
    assert manifest["study_ids"] == [DEFAULT_STUDY_ID]
    assert manifest["runs"][0]["study_id"] == DEFAULT_STUDY_ID
    assert client.get(f"/dashboard/exports/run?run={future}").status_code == 404
    assert client.get(f"/dashboard/runs/{future}").status_code == 404
    assert client.post(f"/dashboard/runs/{future}/trash", data={"csrf": csrf(overview)}).status_code == 404
    isolated = app.extensions["research"]["index"].run(future, app.extensions["research"]["state"].settings())
    assert isolated["study_id"] == "future-school-study" and isolated["study_session"] is None


def test_existing_settings_load_without_historical_fields_or_migration(app):
    state = app.extensions["research"]["state"]
    old = default_settings()
    del old["historical_grades"]
    del old["current_school_year"]
    for session in old["sessions"]:
        del session["name"]
    with state.connect() as db:
        db.execute("UPDATE settings SET body = ? WHERE revision = 1", (json.dumps(old),))
    loaded = state.settings()
    assert loaded["revision"] == 1 and loaded["sessions"] == old["sessions"]
    assert loaded["ranges"] == old["ranges"]
    assert loaded["historical_grades"] == [] and loaded["current_school_year"] == ""
    client = app.test_client()
    login(client)
    assert client.get("/dashboard/settings").status_code == 200
