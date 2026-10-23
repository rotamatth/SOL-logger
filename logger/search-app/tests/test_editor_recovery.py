"""Private form recovery is bounded, transactional and independent of settings."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import sqlite3

import pytest

from research_dashboard import editor_recovery
from research_dashboard.editor_recovery import EditorRecovery, MAX_PAYLOAD_BYTES, TTL_SECONDS
from research_dashboard.state import State


OWNER = "opaque-edit-owner-a"
OTHER_OWNER = "opaque-edit-owner-b"
CREDENTIAL = sha256(b"synthetic-password-a").hexdigest()
OTHER_CREDENTIAL = sha256(b"synthetic-password-b").hexdigest()
KEY = "questions:grade-4-session-1:shared"
FIELDS = {"theme": "Sky", "topic_0": "Clouds", "question_0": "Why does it rain?"}


def test_private_recovery_survives_restart_without_touching_published_settings(tmp_path):
    state = State(tmp_path)
    settings = state.settings()
    original_bytes = state.path.read_bytes()
    recovery = EditorRecovery(tmp_path)
    assert recovery.read(OWNER, CREDENTIAL, KEY) is None
    saved = recovery.save(OWNER, CREDENTIAL, KEY, FIELDS, 0)
    assert saved["sequence"] == 1 and saved["fields"] == FIELDS
    assert saved["updated_at"].endswith("+00:00")
    assert EditorRecovery(tmp_path).read(OWNER, CREDENTIAL, KEY) == saved
    assert recovery.path.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(recovery.path) as db:
        stored_owner = db.execute("SELECT owner FROM editor_drafts").fetchone()[0]
        assert stored_owner == sha256(OWNER.encode()).hexdigest()
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    assert OWNER.encode() not in recovery.path.read_bytes()
    assert state.settings() == settings and state.path.read_bytes() == original_bytes


def test_owner_and_password_fingerprints_are_isolated(tmp_path):
    recovery = EditorRecovery(tmp_path)
    first = recovery.save(OWNER, CREDENTIAL, KEY, FIELDS, 0)
    assert recovery.read(OTHER_OWNER, CREDENTIAL, KEY) is None
    assert recovery.read(OWNER, OTHER_CREDENTIAL, KEY) is None
    assert recovery.clear(OWNER, OTHER_CREDENTIAL, KEY, 0) is None
    assert recovery.read(OWNER, CREDENTIAL, KEY) == first
    replacement = recovery.save(OWNER, OTHER_CREDENTIAL, KEY, {"theme": "New credential"}, 0)
    assert replacement["sequence"] > first["sequence"]
    assert recovery.read(OWNER, CREDENTIAL, KEY) is None
    assert recovery.read(OWNER, OTHER_CREDENTIAL, KEY) == replacement
    with pytest.raises(ValueError, match="recovery_changed"):
        recovery.save(OWNER, CREDENTIAL, KEY, FIELDS, first["sequence"])


def test_compare_and_swap_rejects_a_stale_tab_and_preserves_current_snapshot(tmp_path):
    recovery = EditorRecovery(tmp_path)
    first = recovery.save(OWNER, CREDENTIAL, KEY, FIELDS, 0)
    current = recovery.save(OWNER, CREDENTIAL, KEY, {"theme": "Newer"}, first["sequence"])
    with pytest.raises(ValueError, match="recovery_changed"):
        recovery.save(OWNER, CREDENTIAL, KEY, {"theme": "Stale"}, first["sequence"])
    with pytest.raises(ValueError, match="recovery_changed"):
        recovery.clear(OWNER, CREDENTIAL, KEY, first["sequence"])
    assert recovery.read(OWNER, CREDENTIAL, KEY) == current


def test_two_workers_cannot_both_replace_the_same_sequence(tmp_path):
    first_worker, second_worker = EditorRecovery(tmp_path), EditorRecovery(tmp_path)
    saved = first_worker.save(OWNER, CREDENTIAL, KEY, FIELDS, 0)

    def replace(worker, label):
        try:
            return worker.save(OWNER, CREDENTIAL, KEY, {"theme": label}, saved["sequence"])
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda arguments: replace(*arguments),
                                [(first_worker, "First"), (second_worker, "Second")]))
    winners = [item for item in results if isinstance(item, dict)]
    assert len(winners) == 1 and results.count("recovery_changed") == 1
    assert first_worker.read(OWNER, CREDENTIAL, KEY) == winners[0]


def test_clear_retains_a_sequence_tombstone_and_prevents_aba(tmp_path):
    recovery = EditorRecovery(tmp_path)
    first = recovery.save(OWNER, CREDENTIAL, KEY, FIELDS, 0)
    cleared = recovery.clear(OWNER, CREDENTIAL, KEY, first["sequence"])
    assert cleared["fields"] is None and cleared["sequence"] > first["sequence"]
    assert recovery.read(OWNER, CREDENTIAL, KEY) == cleared
    with pytest.raises(ValueError, match="recovery_changed"):
        recovery.save(OWNER, CREDENTIAL, KEY, FIELDS, 0)
    with pytest.raises(ValueError, match="recovery_changed"):
        recovery.save(OWNER, CREDENTIAL, KEY, FIELDS, first["sequence"])
    reopened = recovery.save(OWNER, CREDENTIAL, KEY, {"theme": "Reopened"}, cleared["sequence"])
    assert reopened["sequence"] > cleared["sequence"]
    with pytest.raises(ValueError, match="recovery_changed"):
        recovery.save(OWNER, CREDENTIAL, KEY, FIELDS, first["sequence"])


def test_owner_limit_never_evicts_active_recovery_and_reuses_oldest_tombstone(tmp_path):
    recovery = EditorRecovery(tmp_path)
    records = {f"session:{number}": recovery.save(OWNER, CREDENTIAL, f"session:{number}", FIELDS, 0)
               for number in range(32)}
    with pytest.raises(ValueError, match="recovery_limit"):
        recovery.save(OWNER, CREDENTIAL, "session:32", FIELDS, 0)
    assert all(recovery.read(OWNER, CREDENTIAL, key) == record for key, record in records.items())
    cleared = recovery.clear(OWNER, CREDENTIAL, "session:0", records["session:0"]["sequence"])
    recovery.save(OWNER, CREDENTIAL, "session:32", FIELDS, 0)
    assert recovery.read(OWNER, CREDENTIAL, "session:0") is None
    assert all(recovery.read(OWNER, CREDENTIAL, key) == record
               for key, record in records.items() if key != "session:0")
    recovery.clear(OWNER, CREDENTIAL, "session:1", records["session:1"]["sequence"])
    recreated = recovery.save(OWNER, CREDENTIAL, "session:0", {"theme": "Recreated"}, 0)
    assert recreated["sequence"] > cleared["sequence"]
    with pytest.raises(ValueError, match="recovery_changed"):
        recovery.save(OWNER, CREDENTIAL, "session:0", FIELDS, records["session:0"]["sequence"])


def test_expiry_is_not_returned_and_writes_cleanup_all_expired_rows(tmp_path, monkeypatch):
    now = 1800000000.0
    monkeypatch.setattr(editor_recovery.time, "time", lambda: now)
    recovery = EditorRecovery(tmp_path)
    first = recovery.save(OWNER, CREDENTIAL, KEY, FIELDS, 0)
    recovery.save(OTHER_OWNER, CREDENTIAL, KEY, FIELDS, 0)
    now += TTL_SECONDS - 1
    assert recovery.read(OWNER, CREDENTIAL, KEY) == first
    now += 1
    assert recovery.read(OWNER, CREDENTIAL, KEY) is None
    with sqlite3.connect(recovery.path) as db:
        assert db.execute("SELECT COUNT(*) FROM editor_drafts").fetchone()[0] == 2
    newer = recovery.save(OWNER, CREDENTIAL, KEY, {"theme": "After expiry"}, 0)
    assert newer["sequence"] > first["sequence"]
    with sqlite3.connect(recovery.path) as db:
        assert db.execute("SELECT COUNT(*) FROM editor_drafts").fetchone()[0] == 1


def test_logout_cleanup_only_removes_the_matching_owner(tmp_path):
    recovery = EditorRecovery(tmp_path)
    recovery.save(OWNER, CREDENTIAL, KEY, FIELDS, 0)
    other = recovery.save(OTHER_OWNER, CREDENTIAL, KEY, FIELDS, 0)
    assert recovery.clear_owner(OWNER) == 1
    assert recovery.read(OWNER, CREDENTIAL, KEY) is None
    assert recovery.read(OTHER_OWNER, CREDENTIAL, KEY) == other


@pytest.mark.parametrize("fields", [
    {"csrf": "token"}, {"PASSWORD": "secret"}, {"review_token": "signed-token"},
    {"field": 1}, {1: "value"}, {"x" * 65: "value"}, {"bad name": "value"},
    {"field": "x" * 300001}, {str(number): "value" for number in range(33)},
    {"first": "x" * 300000, "second": "x" * 300000},
    {"unicode": "é" * (MAX_PAYLOAD_BYTES // 2)}, {"surrogate": "\ud800"},
])
def test_invalid_or_sensitive_payloads_do_not_change_a_saved_snapshot(tmp_path, fields):
    recovery = EditorRecovery(tmp_path)
    before = recovery.save(OWNER, CREDENTIAL, KEY, FIELDS, 0)
    with pytest.raises(ValueError, match="invalid_recovery"):
        recovery.save(OWNER, CREDENTIAL, KEY, fields, before["sequence"])
    assert recovery.read(OWNER, CREDENTIAL, KEY) == before


@pytest.mark.parametrize("key", ["", "x" * 201, "bad key", "<script>", None])
def test_invalid_keys_are_rejected_without_creating_snapshot(tmp_path, key):
    recovery = EditorRecovery(tmp_path)
    with pytest.raises(ValueError, match="invalid_recovery"):
        recovery.read(OWNER, CREDENTIAL, key)
    with sqlite3.connect(recovery.path) as db:
        assert db.execute("SELECT COUNT(*) FROM editor_drafts").fetchone()[0] == 0


@pytest.mark.parametrize("owner,credential", [
    ("", CREDENTIAL), (None, CREDENTIAL), ("x" * 513, CREDENTIAL), ("\ud800", CREDENTIAL),
    (OWNER, ""), (OWNER, None), (OWNER, "x" * 257), (OWNER, "\ud800"),
])
def test_invalid_owner_or_credential_is_rejected(tmp_path, owner, credential):
    recovery = EditorRecovery(tmp_path)
    with pytest.raises(ValueError, match="invalid_recovery"):
        recovery.read(owner, credential, KEY)


@pytest.mark.parametrize("sequence", [-1, True, "0", None, 2**53])
def test_invalid_sequences_are_rejected(tmp_path, sequence):
    recovery = EditorRecovery(tmp_path)
    with pytest.raises(ValueError, match="invalid_recovery"):
        recovery.save(OWNER, CREDENTIAL, KEY, FIELDS, sequence)


def test_sql_failure_rolls_back_snapshot_and_sequence_clock(tmp_path, monkeypatch):
    recovery = EditorRecovery(tmp_path)
    before = recovery.save(OWNER, CREDENTIAL, KEY, FIELDS, 0)
    original_next = recovery._next_sequence

    def fail_after_clock_write(db):
        original_next(db)
        raise sqlite3.OperationalError("synthetic write failure")

    monkeypatch.setattr(recovery, "_next_sequence", fail_after_clock_write)
    with pytest.raises(sqlite3.OperationalError, match="synthetic"):
        recovery.save(OWNER, CREDENTIAL, KEY, {"theme": "Lost"}, before["sequence"])
    assert recovery.read(OWNER, CREDENTIAL, KEY) == before
    with sqlite3.connect(recovery.path) as db:
        assert db.execute("SELECT sequence FROM recovery_clock").fetchone()[0] == before["sequence"]


def test_future_or_unrecognized_schema_is_refused_without_rewriting_data(tmp_path):
    path = tmp_path / "editor-drafts.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE future_data(value TEXT)")
        db.execute("INSERT INTO future_data VALUES ('preserved')")
        db.execute("PRAGMA user_version=2")
    with pytest.raises(RuntimeError, match="different application version"):
        EditorRecovery(tmp_path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT value FROM future_data").fetchone()[0] == "preserved"
        db.execute("PRAGMA user_version=0")
    with pytest.raises(RuntimeError, match="unknown schema"):
        EditorRecovery(tmp_path)
