"""Private, bounded recovery snapshots for researcher forms.

This database is independent from published settings and student attempts. The
owner is an opaque edit-cookie token; only its digest is persisted. A credential
fingerprint scopes every read/write so changing the researcher password cannot
expose a prior credential's drafts.

Clears retain sequence tombstones. Revisions come from a monotonically increasing
database clock, so an evicted/expired tombstone cannot cause an ABA stale write if
the same key is later recreated. Treat sequences as opaque compare-and-swap
tokens: saves to other keys can make them skip numbers.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import sqlite3
import time


SCHEMA_VERSION = 1
TTL_SECONDS = 8 * 60 * 60
MAX_SNAPSHOTS = 32
MAX_PAYLOAD_BYTES = 512 * 1024
MAX_SEQUENCE = 2**53 - 1  # Exact in browser JSON numbers as well as SQLite.
KEY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,199}")
FIELD_PATTERN = re.compile(r"[A-Za-z0-9_:-]{1,64}")
FORBIDDEN_FIELDS = frozenset(("csrf", "password", "review_token"))


def _owner(owner):
    if (not isinstance(owner, str) or not 1 <= len(owner) <= 512
            or any(ord(character) < 32 or ord(character) == 127 for character in owner)):
        raise ValueError("invalid_recovery")
    try:
        return sha256(owner.encode("utf-8")).hexdigest()
    except UnicodeError:
        raise ValueError("invalid_recovery") from None


def _scope(owner, credential, key):
    owner_hash = _owner(owner)
    if (not isinstance(credential, str) or not 1 <= len(credential) <= 256
            or any(ord(character) < 32 or ord(character) == 127 for character in credential)
            or not isinstance(key, str) or not KEY_PATTERN.fullmatch(key)):
        raise ValueError("invalid_recovery")
    try:
        credential.encode("utf-8")
    except UnicodeError:
        raise ValueError("invalid_recovery") from None
    return owner_hash, credential, key


def _sequence(sequence):
    if type(sequence) is not int or not 0 <= sequence <= MAX_SEQUENCE:
        raise ValueError("invalid_recovery")


def _fields(fields):
    if (not isinstance(fields, dict) or len(fields) > 32
            or any(not isinstance(name, str) or not FIELD_PATTERN.fullmatch(name)
                   or name.casefold() in FORBIDDEN_FIELDS
                   or not isinstance(value, str) or len(value) > 300000
                   for name, value in fields.items())):
        raise ValueError("invalid_recovery")
    try:
        body = json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
        size = len(body.encode("utf-8"))
    except (ValueError, UnicodeError):
        raise ValueError("invalid_recovery") from None
    if size > MAX_PAYLOAD_BYTES:
        raise ValueError("invalid_recovery")
    return body


def _record(row):
    if row is None:
        return None
    return {"sequence": row["sequence"],
            "fields": json.loads(row["fields"]) if row["fields"] is not None else None,
            "updated_at": datetime.fromtimestamp(row["updated_at"], timezone.utc).isoformat(timespec="seconds")}


class EditorRecovery:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "editor-drafts.sqlite3"
        if self.path.is_symlink():
            raise RuntimeError("Editor recovery database must be a private regular file")
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if not self.path.is_file():
                raise RuntimeError("Editor recovery database must be a private regular file") from None
        else:
            os.close(descriptor)
        self.path.chmod(0o600)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise RuntimeError("Editor recovery database requires a different application version")
            if version == 0:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone():
                    raise RuntimeError("Editor recovery database has an unknown schema")
                db.execute("""CREATE TABLE editor_drafts (
                    owner TEXT NOT NULL, credential TEXT NOT NULL, key TEXT NOT NULL,
                    sequence INTEGER NOT NULL, fields TEXT, updated_at REAL NOT NULL,
                    PRIMARY KEY(owner,key))""")
                db.execute("CREATE INDEX editor_drafts_expiry ON editor_drafts(updated_at)")
                db.execute("CREATE TABLE recovery_clock (singleton INTEGER PRIMARY KEY CHECK(singleton=1), sequence INTEGER NOT NULL)")
                db.execute("INSERT INTO recovery_clock VALUES (1,0)")
                db.execute("PRAGMA user_version=1")
            else:
                try:
                    db.execute("SELECT owner,credential,key,sequence,fields,updated_at FROM editor_drafts LIMIT 0")
                    clock = db.execute("SELECT sequence FROM recovery_clock WHERE singleton=1").fetchone()
                    if clock is None or type(clock[0]) is not int or not 0 <= clock[0] <= MAX_SEQUENCE:
                        raise RuntimeError("Editor recovery database has an invalid clock")
                except sqlite3.DatabaseError as exc:
                    raise RuntimeError("Editor recovery database has an invalid schema") from exc
        self.path.chmod(0o600)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _cleanup(db, now):
        db.execute("DELETE FROM editor_drafts WHERE updated_at <= ?", (now - TTL_SECONDS,))

    @staticmethod
    def _next_sequence(db):
        sequence = db.execute("SELECT sequence FROM recovery_clock WHERE singleton=1").fetchone()[0]
        if sequence >= MAX_SEQUENCE:
            raise RuntimeError("Editor recovery sequence exhausted")
        sequence += 1
        db.execute("UPDATE recovery_clock SET sequence=? WHERE singleton=1", (sequence,))
        return sequence

    @staticmethod
    def _row(db, owner_hash, credential, key):
        return db.execute("SELECT * FROM editor_drafts WHERE owner=? AND credential=? AND key=?",
                          (owner_hash, credential, key)).fetchone()

    def read(self, owner, credential, key):
        """Return a private snapshot/tombstone, or None when absent or expired."""
        scope = _scope(owner, credential, key)
        with self._connect() as db:
            row = self._row(db, *scope)
        return _record(row) if row and time.time() - row["updated_at"] < TTL_SECONDS else None

    def has_copies(self, owner, credential):
        """Whether logout would remove an unexpired copy; disclose no keys or text."""
        owner_hash, credential, _ = _scope(owner, credential, "logout")
        with self._connect() as db:
            return db.execute("""SELECT 1 FROM editor_drafts WHERE owner=? AND credential=?
                                 AND fields IS NOT NULL AND updated_at>? LIMIT 1""",
                              (owner_hash, credential, time.time() - TTL_SECONDS)).fetchone() is not None

    def save(self, owner, credential, key, fields, expected_sequence):
        """CAS-save text fields; a missing key has expected sequence zero."""
        owner_hash, credential, key = _scope(owner, credential, key)
        _sequence(expected_sequence)
        body, now = _fields(fields), time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._cleanup(db, now)
            row = self._row(db, owner_hash, credential, key)
            if (row["sequence"] if row else 0) != expected_sequence:
                raise ValueError("recovery_changed")
            existing_key = db.execute("SELECT 1 FROM editor_drafts WHERE owner=? AND key=?", (owner_hash, key)).fetchone()
            if not existing_key:
                count = db.execute("SELECT COUNT(*) FROM editor_drafts WHERE owner=?", (owner_hash,)).fetchone()[0]
                while count >= MAX_SNAPSHOTS:
                    oldest = db.execute("""SELECT key FROM editor_drafts WHERE owner=? AND fields IS NULL
                                           ORDER BY updated_at,key LIMIT 1""", (owner_hash,)).fetchone()
                    if oldest is None:
                        raise ValueError("recovery_limit")
                    db.execute("DELETE FROM editor_drafts WHERE owner=? AND key=?", (owner_hash, oldest["key"]))
                    count -= 1
            sequence = self._next_sequence(db)
            db.execute("""INSERT INTO editor_drafts(owner,credential,key,sequence,fields,updated_at)
                          VALUES (?,?,?,?,?,?) ON CONFLICT(owner,key) DO UPDATE SET
                          credential=excluded.credential,sequence=excluded.sequence,
                          fields=excluded.fields,updated_at=excluded.updated_at""",
                       (owner_hash, credential, key, sequence, body, now))
            saved = self._row(db, owner_hash, credential, key)
        return _record(saved)

    def clear(self, owner, credential, key, expected_sequence=None):
        """CAS-clear to a tombstone; return it, or None for a missing key.

        Supplying no expected sequence intentionally clears the current recovery
        snapshot (for a successful explicit settings save). Browser requests
        should always supply their known sequence to reject stale tab actions.
        """
        owner_hash, credential, key = _scope(owner, credential, key)
        if expected_sequence is not None:
            _sequence(expected_sequence)
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._cleanup(db, now)
            row = self._row(db, owner_hash, credential, key)
            if expected_sequence is not None and (row["sequence"] if row else 0) != expected_sequence:
                raise ValueError("recovery_changed")
            if row is None:
                return None
            sequence = self._next_sequence(db)
            db.execute("UPDATE editor_drafts SET sequence=?,fields=NULL,updated_at=? WHERE owner=? AND credential=? AND key=?",
                       (sequence, now, owner_hash, credential, key))
            cleared = self._row(db, owner_hash, credential, key)
        return _record(cleared)

    def clear_owner(self, owner):
        """Delete this opaque owner's snapshots on logout; never reset the clock."""
        owner_hash = _owner(owner)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._cleanup(db, time.time())
            removed = db.execute("DELETE FROM editor_drafts WHERE owner=?", (owner_hash,)).rowcount
        return removed
