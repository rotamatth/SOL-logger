"""Durable progress contracts using temporary, synthetic SQLite databases."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

QUESTIONS = [
    {"topic_id": "3", "question": "Perché il cielo è blu?", "topic_title": "Cielo",
     "experimental": {"condition": "A"}},
    {"topic_id": "1", "question": "Come si forma un arcobaleno?", "topic_title": "Luce"},
    {"topic_id": "2", "question": "Da dove viene la pioggia?", "topic_title": "Acqua"},
]


def make_store(tmp_path, **options):
    from study_progress import AttemptKey, ProgressStore
    return (ProgressStore(tmp_path / "progress.sqlite3", **options),
            AttemptKey("study-2026", "synthetic-1", "grade-4-session-1"))


def test_attempt_survives_reopening_with_exact_snapshot_and_order(tmp_path):
    store, key = make_store(tmp_path)
    questions = deepcopy(QUESTIONS)
    metadata = {"grade": "4", "settings_revision": 7, "condition": {"group": "A"}}
    attempt = store.start_or_resume(key, questions, metadata=metadata)
    attempt_id = attempt["attempt_id"]
    questions[0]["experimental"]["condition"] = "changed"
    metadata["condition"]["group"] = "changed"
    attempt["tasks"][0]["snapshot"]["question"] = "changed by caller"

    reopened, _ = make_store(tmp_path)
    saved = reopened.get_attempt(key, attempt_id)
    assert [t["number"] for t in saved["tasks"]] == [1, 2, 3]
    assert [t["snapshot"] for t in saved["tasks"]] == QUESTIONS
    assert saved["metadata"] == {
        "grade": "4", "settings_revision": 7, "condition": {"group": "A"}}
    assert saved["phase"] == "first-answer"
    assert saved["question_number"] == 1
    assert saved["status"] == "active"
    assert saved["participant_id"] == "synthetic-1"
    assert datetime.fromisoformat(saved["created_at"]).utcoffset() is not None


@pytest.mark.parametrize("replacement", [None, [], list(reversed(QUESTIONS))])
def test_resume_ignores_changed_or_unavailable_configuration(tmp_path, replacement):
    store, key = make_store(tmp_path)
    original = store.start_or_resume(key, QUESTIONS, metadata={"revision": 1})
    resumed = store.start_or_resume(key, replacement, metadata={"revision": 99})
    assert resumed == original


def test_simultaneous_starts_from_independent_workers_resume_one_attempt(tmp_path):
    store, key = make_store(tmp_path)
    workers = [make_store(tmp_path)[0] for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        attempts = list(pool.map(lambda worker: worker.start_or_resume(key, QUESTIONS), workers))
    assert len({a["attempt_id"] for a in attempts}) == 1
    assert store.get_attempt(key, attempts[0]["attempt_id"]) == attempts[0]


def test_study_participant_session_and_test_scopes_are_independent(tmp_path):
    from study_progress import AttemptKey, AttemptNotFound
    store, key = make_store(tmp_path)
    keys = [key, AttemptKey("study-2027", "synthetic-1", "grade-4-session-1"),
            AttemptKey("study-2026", "synthetic-2", "grade-4-session-1"),
            AttemptKey("study-2026", "synthetic-1", "grade-4-session-2"),
            AttemptKey("study-2026", "synthetic-1", "grade-4-session-1", is_test=True),
            AttemptKey("study-2026", "TEST", "grade-4-session-1", is_test=True)]
    attempts = [store.start_or_resume(scope, QUESTIONS) for scope in keys]
    assert len({a["attempt_id"] for a in attempts}) == 6
    assert attempts[0]["is_test"] is False
    assert attempts[-1]["is_test"] is True
    for scope in keys[1:]:
        with pytest.raises(AttemptNotFound):
            store.get_attempt(scope, attempts[0]["attempt_id"])
        with pytest.raises(AttemptNotFound):
            store.save_draft(scope, attempts[0]["attempt_id"], 1, "first-answer", "wrong ID", 0)


@pytest.mark.parametrize("questions", [
    [], QUESTIONS[:2], QUESTIONS + QUESTIONS[:1],
    [QUESTIONS[0], QUESTIONS[0], QUESTIONS[2]],
    [{"topic_id": "3", "question": "  "}, QUESTIONS[1], QUESTIONS[2]],
    [{"topic_id": "", "question": "Valid question"}, QUESTIONS[1], QUESTIONS[2]],
    [{"topic_id": "3"}, QUESTIONS[1], QUESTIONS[2]],
    [None, QUESTIONS[1], QUESTIONS[2]],
])
def test_invalid_question_set_does_not_leave_a_partial_attempt(tmp_path, questions):
    store, key = make_store(tmp_path)
    with pytest.raises(ValueError):
        store.start_or_resume(key, questions)
    valid = store.start_or_resume(key, QUESTIONS)
    assert len(valid["tasks"]) == 3
    assert [t["snapshot"] for t in valid["tasks"]] == QUESTIONS


@pytest.mark.parametrize("values", [
    ("", "synthetic-1", "session-1", False),
    ("study", " ", "session-1", False),
    ("study", "synthetic-1", "", False),
    ("study", 1, "session-1", False),
    ("study", "TEST", "session-1", False),
    ("study", "synthetic-1", "session-1", "false"),
])
def test_invalid_identity_and_unisolated_test_id_are_rejected(values):
    from study_progress import AttemptKey
    with pytest.raises(ValueError):
        AttemptKey(*values)


def test_first_and_final_drafts_restore_separately_without_advancing(tmp_path):
    store, key = make_store(tmp_path)
    attempt = store.start_or_resume(key, QUESTIONS)
    attempt_id = attempt["attempt_id"]
    first = store.save_draft(key, attempt_id, 1, "first-answer", "  La mia idea è…\n", 0)
    final = store.save_draft(key, attempt_id, 1, "final-answer", "Risposta dopo la ricerca", 0)
    reopened, _ = make_store(tmp_path)
    saved = reopened.get_attempt(key, attempt_id)
    assert saved["tasks"][0]["drafts"] == {"first-answer": first, "final-answer": final}
    assert first["text"] == "  La mia idea è…\n"
    assert first["revision"] == final["revision"] == 1
    assert saved["tasks"][1]["drafts"] == saved["tasks"][2]["drafts"] == {}
    assert saved["question_number"] == 1
    assert saved["phase"] == "first-answer"


def test_empty_draft_can_be_saved_without_becoming_a_submission(tmp_path):
    store, key = make_store(tmp_path)
    attempt = store.start_or_resume(key, QUESTIONS)
    saved = store.save_draft(key, attempt["attempt_id"], 1, "first-answer", "", 0)
    updated = store.save_draft(key, attempt["attempt_id"], 1, "first-answer", "   ", 1)
    assert saved["text"] == "" and saved["revision"] == 1
    assert updated["text"] == "   " and updated["revision"] == 2
    assert store.get_attempt(key, attempt["attempt_id"])["phase"] == "first-answer"


def test_stale_draft_revision_is_rejected_without_overwriting_saved_text(tmp_path):
    from study_progress import DraftConflict
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    saved = store.save_draft(key, attempt_id, 1, "first-answer", "Latest", 0)
    with pytest.raises(DraftConflict):
        store.save_draft(key, attempt_id, 1, "first-answer", "Stale tab", 0)
    assert store.get_attempt(key, attempt_id)["tasks"][0]["drafts"]["first-answer"] == saved


def test_concurrent_draft_updates_accept_one_revision_and_reject_the_other(tmp_path):
    from study_progress import DraftConflict
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    workers = [make_store(tmp_path)[0] for _ in range(2)]

    def write(item):
        worker, text = item
        try:
            return worker.save_draft(key, attempt_id, 1, "first-answer", text, 0)
        except DraftConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, zip(workers, ["From tab A", "From tab B"], strict=True)))
    committed = [r for r in results if r is not None]
    assert len(committed) == 1
    assert store.get_attempt(key, attempt_id)["tasks"][0]["drafts"]["first-answer"] == committed[0]


def test_locked_database_preserves_draft_and_allows_retry_after_release(tmp_path):
    store, key = make_store(tmp_path, timeout=0.01)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    original = store.save_draft(key, attempt_id, 1, "first-answer", "Durable", 0)
    lock = sqlite3.connect(store.path)
    try:
        lock.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            store.save_draft(key, attempt_id, 1, "first-answer", "Unsaved", 1)
    finally:
        lock.rollback()
        lock.close()
    assert store.get_attempt(key, attempt_id)["tasks"][0]["drafts"]["first-answer"] == original
    retried = store.save_draft(key, attempt_id, 1, "first-answer", "Recovered", 1)
    assert retried["revision"] == 2


@pytest.mark.parametrize("number, phase, text, revision", [
    (0, "first-answer", "draft", 0), (4, "first-answer", "draft", 0),
    (True, "first-answer", "draft", 0), (1, "unknown-phase", "draft", 0),
    (1, "first-answer", None, 0), (1, "first-answer", "draft", -1),
    (1, "first-answer", "draft", True),
])
def test_invalid_draft_does_not_modify_progress(tmp_path, number, phase, text, revision):
    store, key = make_store(tmp_path)
    attempt = store.start_or_resume(key, QUESTIONS)
    with pytest.raises(ValueError):
        store.save_draft(key, attempt["attempt_id"], number, phase, text, revision)
    assert store.get_attempt(key, attempt["attempt_id"]) == attempt


@pytest.mark.parametrize("source", ["config", "environment", "default-config", "default-environment"])
def test_initializer_uses_configurable_persistent_path_without_creating_routes(tmp_path, monkeypatch, source):
    from flask import Flask
    from study_progress import init_progress
    app = Flask(__name__)
    monkeypatch.delenv("SOL_PROGRESS_DB_PATH", raising=False)
    monkeypatch.setenv("RESEARCH_STATE_DIR", str(tmp_path / "environment-state"))
    if source == "config":
        expected = tmp_path / "explicit" / "progress.sqlite3"
        app.config["SOL_PROGRESS_DB_PATH"] = str(expected)
        monkeypatch.setenv("SOL_PROGRESS_DB_PATH", str(tmp_path / "must-not-be-used.sqlite3"))
    elif source == "environment":
        expected = tmp_path / "environment" / "progress.sqlite3"
        monkeypatch.setenv("SOL_PROGRESS_DB_PATH", str(expected))
    elif source == "default-config":
        app.config["RESEARCH_STATE_DIR"] = str(tmp_path / "configured-state")
        expected = tmp_path / "configured-state" / "study-progress.sqlite3"
    else:
        expected = tmp_path / "environment-state" / "study-progress.sqlite3"
    rules = list(app.url_map.iter_rules())
    store = init_progress(app)
    assert store.path == expected and expected.is_file()
    assert app.extensions["study_progress"] is store
    assert app.config["SOL_PROGRESS_DB_PATH"] == str(expected)
    assert list(app.url_map.iter_rules()) == rules


def test_runtime_uses_rollback_journal_full_sync_foreign_keys_and_bounded_wait(tmp_path):
    store, _ = make_store(tmp_path)
    settings = store.runtime_settings()
    assert settings["journal_mode"] == "delete"
    assert settings["synchronous"] == 2
    assert settings["foreign_keys"] == 1
    assert settings["busy_timeout"] == 5000
    assert settings["schema_version"] == 4
    assert settings["sqlite_version"] == sqlite3.sqlite_version


def test_commit_failure_preserves_draft_and_revision_for_retry(tmp_path):
    store, key = make_store(tmp_path, timeout=0.01)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    original = store.save_draft(key, attempt_id, 1, "first-answer", "Before", 0)
    reader = sqlite3.connect(store.path)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM progress_drafts").fetchall()
        # In DELETE mode, the reader permits UPDATE but prevents COMMIT.
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            store.save_draft(key, attempt_id, 1, "first-answer", "Must roll back", 1)
    finally:
        reader.rollback()
        reader.close()
    assert store.get_attempt(key, attempt_id)["tasks"][0]["drafts"]["first-answer"] == original
    assert store.save_draft(key, attempt_id, 1, "first-answer", "Retry", 1)["revision"] == 2


def test_attempt_and_draft_are_available_to_a_fresh_python_process(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    store.save_draft(key, attempt_id, 1, "first-answer", "Persisted across restart", 0)
    script = """
import sys
from study_progress import AttemptKey, ProgressStore
store = ProgressStore(sys.argv[1])
key = AttemptKey('study-2026', 'synthetic-1', 'grade-4-session-1')
attempt = store.start_or_resume(key, None)
assert attempt['attempt_id'] == sys.argv[2]
assert attempt['tasks'][0]['drafts']['first-answer']['text'] == 'Persisted across restart'
assert attempt['phase'] == 'first-answer'
"""
    result = subprocess.run([sys.executable, "-c", script, str(store.path), attempt_id],
                            cwd=APP_ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_sqlite_backup_restores_snapshots_and_drafts(tmp_path):
    from study_progress import ProgressStore
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS, metadata={"condition": "A"})["attempt_id"]
    store.save_draft(key, attempt_id, 1, "first-answer", "Saved in backup", 0)
    expected = store.get_attempt(key, attempt_id)
    backup_path = tmp_path / "restored.sqlite3"
    with sqlite3.connect(store.path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)
    restored = ProgressStore(backup_path)
    assert restored.get_attempt(key, attempt_id) == expected
