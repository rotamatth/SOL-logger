from pathlib import Path
import json
import runpy
import sqlite3
import zipfile

from flask import Flask
import pytest

from .test_study_enrollment import student_modules, schedule
from research_dashboard.runtime import configure_runtime
from research_dashboard.log_store import LogStore
from research_dashboard.state import State

backup = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tools" / "backup_study.py"))


def test_backup_restore_preserves_receipts_secrets_and_original_bytes(tmp_path):
    source = tmp_path / "logger"
    (source / "research-secrets").mkdir(parents=True)
    (source / "research-secrets" / "key").write_bytes(b"private-test-key")
    store = LogStore(source / "logs-v2")
    store.accept("run", "batch", {}, lambda: ({"run_FULL.log": '{"answer":"rain"}\n'}, {"status": "logged"}))
    archive = tmp_path / "backup.zip"
    backup["create"](source, archive)
    destination = tmp_path / "restored"
    backup["restore"](archive, destination)
    assert (destination / "research-secrets" / "key").read_bytes() == b"private-test-key"
    restored = LogStore(destination / "logs-v2")
    restored.accept("run", "batch", {}, lambda: pytest.fail("A restored receipt must deduplicate retries"))
    assert (destination / "logs-v2" / "run_FULL.log").read_text() == '{"answer":"rain"}\n'
    with pytest.raises(FileExistsError):
        backup["restore"](archive, destination)


def test_backup_rejects_corrupt_authoritative_database_and_unsafe_archive(tmp_path):
    (tmp_path / "research-state").mkdir()
    (tmp_path / "research-state" / "research.sqlite3").write_bytes(b"corrupted")
    with pytest.raises(sqlite3.DatabaseError):
        backup["create"](tmp_path, tmp_path / "broken.zip")
    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("backup-manifest.json", json.dumps({"version": 1,
            "directories": list(backup["DIRECTORIES"]), "files": [
                {"name": "logs-v2/../../escape", "size": 0, "sha256": ""}]}))
        archive.writestr("logs-v2/../../escape", "")
    with pytest.raises(ValueError, match="Unsafe"):
        backup["restore"](unsafe, tmp_path / "destination")
    assert not (tmp_path / "destination").exists()


def test_private_development_secret_is_persistent_and_production_requires_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY")
    monkeypatch.delenv("FLASK_SECRET_KEY_FILE", raising=False)
    monkeypatch.setenv("SOL_ENV", "production")
    with pytest.raises(RuntimeError, match="Configure"):
        configure_runtime(Flask(__name__))
    monkeypatch.setenv("SOL_ENV", "development")
    first, second = Flask("one"), Flask("two")
    configure_runtime(first)
    configure_runtime(second)
    assert first.secret_key == second.secret_key and len(first.secret_key) >= 32
    assert Path(first.config["SESSION_FILE_DIR"]).joinpath("signing-secret").stat().st_mode & 0o777 == 0o600
    monkeypatch.setenv("FLASK_SECRET_KEY", "short")
    with pytest.raises(RuntimeError, match="32"):
        configure_runtime(Flask(__name__))


def test_readiness_checks_writes_and_authoritative_storage(student_modules, monkeypatch):
    module = student_modules()
    client = module.app.test_client()
    assert client.get("/health/ready").status_code == 200
    monkeypatch.setattr(module.LOG_STORE, "recover", lambda: (_ for _ in ()).throw(OSError("disk unavailable")))
    response = client.get("/health/ready")
    assert response.status_code == 503 and response.json == {"status": "unavailable"}


def test_schema_migration_preserves_settings_and_refuses_newer_databases(tmp_path):
    state = State(tmp_path / "state")
    before = state.settings()
    with state.connect() as db:
        # Simulate the previous version's unversioned database with no attempt table.
        db.execute("DROP TABLE study_attempts")
        db.execute("PRAGMA user_version=0")
    migrated = State(tmp_path / "state")
    assert {k: v for k, v in migrated.settings().items() if k not in ("revision", "updated_at")} == {k: v for k, v in before.items() if k not in ("revision", "updated_at")}
    assert migrated.pending_attempts() == []
    with migrated.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        db.execute("PRAGMA user_version=3")
    with pytest.raises(RuntimeError, match="newer application"):
        State(tmp_path / "state")
    with migrated.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
    assert {k: v for k, v in migrated.settings().items() if k not in ("revision", "updated_at")} == {k: v for k, v in before.items() if k not in ("revision", "updated_at")}
