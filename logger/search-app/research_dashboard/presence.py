"""Where each tablet is now: the live view's "fuori dalla pagina" and "nessun segnale", nothing else.

Every child page sends a short signal every few seconds: its page and whether it is visible. The signal
goes to a small database file of its own, apart from the logs and the progress database, so a write here
never waits on, or holds up, saving a log or an answer. Failures are ignored: the live view then shows
less, and nothing else changes. One row per run, replaced by each signal; nothing here is study data.
"""
from pathlib import Path
import sqlite3
import time

SILENT_AFTER_SECONDS = 30
PAGE_MAX = 80


class Presence:
    def __init__(self, directory):
        self.path = Path(directory) / "presence.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS presence (
                technical_session_id TEXT PRIMARY KEY, participant_id TEXT NOT NULL,
                page TEXT NOT NULL, visible INTEGER NOT NULL CHECK(visible IN (0, 1)), seen REAL NOT NULL)""")
        self.path.chmod(0o600)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=0.5)

    def beat(self, technical_session_id, participant_id, page, visible, now=None):
        """Record a run's latest signal. Returns False instead of raising: the signal is never worth an error."""
        if not (isinstance(technical_session_id, str) and isinstance(participant_id, str)):
            return False
        page = page if isinstance(page, str) else ""
        try:
            with self._connect() as db:
                db.execute("INSERT OR REPLACE INTO presence VALUES (?, ?, ?, ?, ?)",
                           (technical_session_id, participant_id, page[:PAGE_MAX], int(bool(visible)),
                            time.time() if now is None else now))
            return True
        except sqlite3.Error:
            return False

    def latest(self, technical_session_ids, now=None):
        """{technical_session_id: {"state": visible|hidden|silent, "seconds": n, "page": path}} for the given runs."""
        ids = [item for item in technical_session_ids if isinstance(item, str)]
        if not ids:
            return {}
        now = time.time() if now is None else now
        try:
            with self._connect() as db:
                rows = db.execute(f"SELECT technical_session_id, page, visible, seen FROM presence "
                                  f"WHERE technical_session_id IN ({','.join('?' * len(ids))})", ids).fetchall()
        except sqlite3.Error:
            return {}
        result = {}
        for technical, page, visible, seen in rows:
            seconds = max(0, int(now - seen))
            state = "silent" if seconds >= SILENT_AFTER_SECONDS else "visible" if visible else "hidden"
            result[technical] = {"state": state, "seconds": seconds, "page": page}
        return result
