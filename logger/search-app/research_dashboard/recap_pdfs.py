"""The recap PDFs the server keeps when a child saves the activity, read for the researchers.

The children's app writes them into its progress database at "Salva l'attività". The dashboard only reads
that database, read-only, and finds a run's PDF by the attempt ID its answer events carry.
"""
import sqlite3
from urllib.parse import quote

from flask import current_app


def _connect():
    path = current_app.config.get("SOL_PROGRESS_DB_PATH")
    if not path:
        return None
    try:
        return sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None


def run_attempt(run):
    """The attempt of a run, when its logs name exactly one."""
    attempts = run.get("attempt_ids") or []
    return attempts[0] if len(attempts) == 1 else None


def saved_attempts(attempt_ids):
    """Which of these attempts have a recap PDF on the server."""
    wanted = sorted({attempt for attempt in attempt_ids if attempt})
    db = _connect() if wanted else None
    if db is None:
        return set()
    try:
        marks = ",".join("?" * len(wanted))
        return {row[0] for row in db.execute(
            f"SELECT attempt_id FROM progress_recap_exports WHERE attempt_id IN ({marks})", wanted)}
    except sqlite3.Error:
        return set()
    finally:
        db.close()


def recap_pdf(attempt_id):
    """The PDF saved for this attempt, or None."""
    db = _connect() if attempt_id else None
    if db is None:
        return None
    try:
        row = db.execute("SELECT pdf FROM progress_recap_exports WHERE attempt_id = ?", (attempt_id,)).fetchone()
        return bytes(row[0]) if row else None
    except sqlite3.Error:
        return None
    finally:
        db.close()
