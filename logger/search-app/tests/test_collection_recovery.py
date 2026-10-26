"""Failure injection against synthetic storage; never touches a study collection."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import sqlite3

import pytest

from .test_study_enrollment import student_modules, schedule
from research_dashboard.log_store import LogStore, UploadConflict
from research_dashboard.index import Index


def test_upload_retry_and_concurrent_requests_return_one_receipt(tmp_path):
    store = LogStore(tmp_path)
    def save(_):
        return store.accept("run", "batch", {"answer": "rain"},
                            lambda: ({"a_FULL.log": "answer\n", "a_task1.log": "answer\n"}, {"status": "logged"}))
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(save, range(8)))
    assert all(response == responses[0] for response in responses)
    assert (tmp_path / "a_FULL.log").read_text() == "answer\n"
    assert (tmp_path / "a_task1.log").read_text() == "answer\n"
    with pytest.raises(UploadConflict):
        store.accept("run", "batch", {"answer": "changed"}, lambda: ({}, {}))


def test_interrupted_append_completes_exact_bytes_after_new_worker(tmp_path, monkeypatch):
    store = LogStore(tmp_path)
    original = store._write
    def interrupted(name, offset, content):
        if name == "a_task1.log":
            (tmp_path / name).write_bytes(content.encode()[:7])
            raise OSError("simulated disk failure")
        original(name, offset, content)
    monkeypatch.setattr(store, "_write", interrupted)
    body = '{"answer":"pioggia ☔"}\n'
    def prepare():
        return {"a_FULL.log": body, "a_task1.log": body}, {"status": "logged"}
    with pytest.raises(OSError):
        store.accept("run", "batch", {"answer": "pioggia"}, prepare)
    replacement = LogStore(tmp_path)
    assert replacement.accept("run", "batch", {"answer": "pioggia"}, prepare)["status"] == "logged"
    assert (tmp_path / "a_FULL.log").read_text() == body
    assert (tmp_path / "a_task1.log").read_text() == body


def test_pending_upload_never_overwrites_changed_original(tmp_path, monkeypatch):
    store = LogStore(tmp_path)
    monkeypatch.setattr(store, "_write", lambda *args: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(OSError):
        store.accept("run", "batch", {}, lambda: ({"a.log": "original\n"}, {}))
    (tmp_path / "a.log").write_text("changed\n")
    with pytest.raises(OSError):
        LogStore(tmp_path).recover()
    assert (tmp_path / "a.log").read_text() == "changed\n"


def test_busy_publisher_returns_retry_instead_of_blocking_workers(tmp_path):
    store = LogStore(tmp_path, lock_timeout=0.02)
    with store.locked():
        with pytest.raises(TimeoutError, match="busy"):
            store.accept("run", "batch", {}, lambda: ({"a.log": "answer\n"}, {}))
    assert not (tmp_path / "a.log").exists()


def test_corrupt_reporting_index_does_not_stop_student_app(student_modules, tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "index.sqlite3").write_bytes(b"corrupt-cache")
    module = student_modules()
    schedule(module)
    client = module.app.test_client()
    assert client.get("/welcome").status_code == 200
    assert client.post("/start", data={"user_id": "1"}).status_code == 302
    index = module.app.extensions["research"]["index"]
    index.refresh()
    assert len(index.summaries(module.RESEARCH_STATE.settings())) == 1
    assert list(state_dir.glob("index-corrupt-*/index.sqlite3"))[0].read_bytes() == b"corrupt-cache"


def test_unavailable_reporting_index_leaves_student_collection_running(student_modules, tmp_path):
    module = student_modules()
    schedule(module)
    # A directory at the cache filename cannot be rebuilt as a SQLite file.
    (tmp_path / "state" / "index.sqlite3").mkdir()
    client = module.app.test_client()
    assert client.post("/start", data={"user_id": "1"}).status_code == 302
    with client.session_transaction() as active:
        sid = active["session_id"]
    assert client.post("/log_session", json={"session_id": sid, "logs": [{"type": "TaskEnded", "answer": "ok"}]}).status_code == 200


def test_reporting_cache_recovers_corrupt_table_pages_not_just_a_bad_header(tmp_path):
    index = Index(tmp_path, {"v2": tmp_path / "v2", "legacy": tmp_path / "legacy"})
    with index.connect() as db:
        page = db.execute("SELECT rootpage FROM sqlite_master WHERE name='runs'").fetchone()[0]
        page_size = db.execute("PRAGMA page_size").fetchone()[0]
    with index.path.open("r+b") as cache:
        cache.seek((page - 1) * page_size)
        cache.write(b"\xff")  # Invalid B-tree page type; SQLite header remains valid.
    replacement = Index(tmp_path, {"v2": tmp_path / "v2", "legacy": tmp_path / "legacy"})
    with replacement.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    assert len(list(tmp_path.glob("index-corrupt-*/index.sqlite3"))) == 1


def test_durable_attempt_recovers_sidecar_and_blocks_removal(student_modules, tmp_path, monkeypatch):
    from research_dashboard import collection
    module = student_modules()
    schedule(module)
    original = collection.publish_metadata
    monkeypatch.setattr(collection, "publish_metadata", lambda *args: (_ for _ in ()).throw(OSError("disk error")))
    client = module.app.test_client()
    assert client.post("/start", data={"user_id": "1"}).status_code == 302
    with client.session_transaction() as active:
        sid = active["session_id"]
    snapshot = module.RESEARCH_STATE.attempt_metadata(sid)
    assert snapshot["tasks"][0]["question_id"]
    assert not list((tmp_path / "v2").glob("*.run.json"))
    settings = module.RESEARCH_STATE.settings()
    next(s for s in settings["sessions"] if s["id"] == snapshot["study_session_at_collection"])["removed"] = True
    with pytest.raises(ValueError, match="session_has_records"):
        module.RESEARCH_STATE.save_settings(settings, settings["revision"])
    monkeypatch.setattr(collection, "publish_metadata", original)
    collection.publish_pending_runs(tmp_path / "v2", module.RESEARCH_STATE)
    assert json.loads(next((tmp_path / "v2").glob("*.run.json")).read_text()) == snapshot


def test_start_failure_preserves_existing_attempt(student_modules, monkeypatch):
    module = student_modules()
    schedule(module)
    client = module.app.test_client()
    assert client.post("/start", data={"user_id": "1"}).status_code == 302
    with client.session_transaction() as active:
        before = dict(active)
    monkeypatch.setattr(module.RESEARCH_STATE, "admit_attempt", lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError("unavailable")))
    assert client.post("/start", data={"user_id": "2"}).status_code == 503
    with client.session_transaction() as active:
        assert dict(active) == before


def test_server_replacement_and_lost_ack_preserve_attempt_and_no_duplicate_answers(student_modules, tmp_path):
    module = student_modules()
    schedule(module)
    client = module.app.test_client()
    client.post("/start", data={"user_id": "1"})
    client.get("/search")
    with client.session_transaction() as active:
        sid, config = active["session_id"], active["task_config"]
    body = {"session_id": sid, "batch_id": "stable-batch", "logs": [{"type": "TaskEnded", "answer": "rain"}]}
    first = client.post("/log_session", json=body)
    assert first.status_code == 200
    client.post("/end")
    client.get("/next_task")
    replacement = student_modules().app.test_client()
    replacement.set_cookie("session", client.get_cookie("session").value)
    with replacement.session_transaction() as active:
        assert active["session_id"] == sid and active["task_config"] == config
        assert active["task_position"] == 1
    retry = replacement.post("/log_session", json=body)
    assert retry.json == first.json
    answers = [json.loads(line) for line in next((tmp_path / "v2").glob("*_FULL.log")).read_text().splitlines()]
    assert len([entry for entry in answers if entry["type"] == "TaskEnded"]) == 1
    assert not list((tmp_path / "v2").glob("*_task2_*.log"))


def test_foreign_events_are_acknowledged_only_after_all_files_are_durable(student_modules, tmp_path, monkeypatch):
    module = student_modules()
    schedule(module)
    client = module.app.test_client()
    client.post("/start", data={"user_id": "1"})
    with client.session_transaction() as active:
        sid = active["session_id"]
    body = {"session_id": sid, "batch_id": "recovered", "logs": [
        {"type": "TaskEnded", "uid": "old", "sessionID": "old-run", "answer": "old answer"},
        {"type": "TaskEnded", "uid": "1", "answer": "new answer"}]}
    original = module.LOG_STORE._write
    monkeypatch.setattr(module.LOG_STORE, "_write", lambda *args: (_ for _ in ()).throw(OSError("unavailable")))
    assert client.post("/log_session", json=body).status_code == 503
    monkeypatch.setattr(module.LOG_STORE, "_write", original)
    assert client.post("/log_session", json=body).json["recovered_incomplete"] == {"old": 1}
    assert client.post("/log_session", json=body).status_code == 200
    foreign = next((tmp_path / "v2").glob("*_INCOMPLETE.log")).read_text().splitlines()
    assert len(foreign) == 2


def test_attempt_admission_and_session_removal_are_serialized(student_modules, tmp_path):
    from research_dashboard.collection import record_run
    module = student_modules()
    settings = schedule(module)
    selected = module.scheduled_assignment(settings, "1")
    metadata = record_run(tmp_path / "snapshot", module.RESEARCH_STATE, "1", "racing-run", "racing-log",
                          ["1", "2", "3"], selected["topics"], settings=settings,
                          study_session=selected["session"], question_set=selected["question_set"])
    next(item for item in settings["sessions"] if item["id"] == selected["session"]["id"])["removed"] = True
    def operate(kind):
        try:
            if kind == "start":
                module.RESEARCH_STATE.admit_attempt(metadata)
            else:
                module.RESEARCH_STATE.save_settings(settings, settings["revision"])
            return kind
        except ValueError:
            return "blocked"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(operate, ["start", "remove"]))
    assert outcomes.count("blocked") == 1
    final = module.RESEARCH_STATE.settings()
    removed = next(item for item in final["sessions"] if item["id"] == selected["session"]["id"]).get("removed", False)
    assert removed != bool(module.RESEARCH_STATE.attempt_metadata("racing-run"))
