"""Durable upload receipts and recoverable appends to original-format log files.

The SQLite journal is authoritative for accepted upload bytes. A process lock
serializes file publication across workers. A committed intent records exact file
offsets; retry completes a partial append instead of appending the events twice.
Keep this database with the logs during backups and recovery.
"""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import fcntl
import json
import os
import re
import sqlite3
import time

from .runtime import sync_directory


class UploadConflict(ValueError):
    pass


class LogStore:
    def __init__(self, directory, lock_timeout=2):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / ".uploads.sqlite3"
        self.lock_timeout = lock_timeout

    @contextmanager
    def locked(self):
        with open(self.root / ".uploads.lock", "a+b") as lock:
            deadline = time.monotonic() + self.lock_timeout
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Collection storage is busy; retry this upload")
                    time.sleep(0.02)
            db = sqlite3.connect(self.path, timeout=self.lock_timeout)
            db.row_factory = sqlite3.Row
            try:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("""CREATE TABLE IF NOT EXISTS uploads (
                    run_id TEXT NOT NULL, batch_id TEXT NOT NULL, digest TEXT NOT NULL,
                    writes TEXT NOT NULL, response TEXT NOT NULL, complete INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(run_id, batch_id))""")
                db.commit()
                self.path.chmod(0o600)
                yield db
            finally:
                db.close()

    @staticmethod
    def digest(payload):
        return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":"), allow_nan=False).encode()).hexdigest()

    def _write(self, name, offset, content):
        if name != Path(name).name or not name.endswith(".log"):
            raise ValueError("invalid_log_name")
        raw = content.encode("utf-8")
        fd = os.open(self.root / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "r+b") as target:
            target.seek(0, os.SEEK_END)
            size = target.tell()
            if size < offset:
                raise OSError("Log truncated before pending upload; restore storage before retrying")
            target.seek(offset)
            existing = target.read(len(raw))
            if existing != raw[:len(existing)]:
                raise OSError("Log changed at pending upload offset; refusing to overwrite original data")
            if len(existing) < len(raw):
                target.seek(offset + len(existing))
                target.write(raw[len(existing):])
            target.flush()
            os.fsync(target.fileno())

    def _recover(self, db):
        for pending in db.execute("SELECT * FROM uploads WHERE complete=0 ORDER BY rowid").fetchall():
            for write in json.loads(pending["writes"]):
                self._write(write["name"], write["offset"], write["content"])
            sync_directory(self.root)
            with db:
                db.execute("UPDATE uploads SET complete=1 WHERE run_id=? AND batch_id=?",
                           (pending["run_id"], pending["batch_id"]))

    def recover(self):
        with self.locked() as db:
            db.execute("BEGIN IMMEDIATE")
            self._recover(db)
            db.commit()

    def accept(self, run_id, batch_id, payload, prepare):
        """Return the original receipt for retries, even after task advancement."""
        digest = self.digest(payload)
        batch_id = batch_id or "legacy:" + digest
        if not isinstance(batch_id, str) or not re.fullmatch(r"[A-Za-z0-9:_-]{1,128}", batch_id):
            raise ValueError("invalid_batch_id")
        with self.locked() as db:
            self._recover(db)
            old = db.execute("SELECT * FROM uploads WHERE run_id=? AND batch_id=?",
                             (run_id, batch_id)).fetchone()
            if old:
                if old["digest"] != digest:
                    raise UploadConflict("batch_id_reused")
                return json.loads(old["response"])
            files, response = prepare()
            response = {**response, "batch_id": batch_id}
            writes = []
            for name, content in files.items():
                if name != Path(name).name or not name.endswith(".log"):
                    raise ValueError("invalid_log_name")
                path = self.root / name
                if path.is_symlink():
                    raise OSError("Refusing symlink log destination")
                writes.append({"name": name, "offset": path.stat().st_size if path.exists() else 0,
                               "content": content})
            with db:
                db.execute("INSERT INTO uploads(run_id,batch_id,digest,writes,response) VALUES (?,?,?,?,?)",
                           (run_id, batch_id, digest, json.dumps(writes), json.dumps(response)))
            self._recover(db)
            return response
