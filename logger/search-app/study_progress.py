"""Durable attempts, drafts and first answers, independent of browser sessions.

Participant routes and logging are integrated in a later increment of issue 6.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import sqlite3
import uuid


TIME_ZONE = ZoneInfo("Europe/Zurich")
DRAFT_PHASES = ("first-answer", "final-answer")


class AttemptNotFound(LookupError):
    """The attempt does not exist within the supplied participant/study scope."""


class DraftConflict(ValueError):
    """The draft changed since the caller last read it."""


class SubmissionConflict(ValueError):
    """A submission is immutable or does not match the active question/phase."""


@dataclass(frozen=True)
class AttemptKey:
    """Use a study_id unique to the study/year, not a technical browser ID."""

    study_id: str
    participant_id: str
    study_session_id: str
    is_test: bool = False

    def __post_init__(self):
        if any(not isinstance(value, str) or not value.strip()
               for value in (self.study_id, self.participant_id, self.study_session_id)):
            raise ValueError("Study, participant and study session IDs are required")
        if type(self.is_test) is not bool:
            raise ValueError("is_test must be a boolean")
        if self.participant_id == "TEST" and not self.is_test:
            raise ValueError("The TEST participant requires an isolated test scope")

    @property
    def scope(self):
        return (self.study_id, self.participant_id, self.study_session_id, int(self.is_test))


SCHEMA = (
    """CREATE TABLE IF NOT EXISTS progress_attempts (
        attempt_id TEXT PRIMARY KEY,
        study_id TEXT NOT NULL, participant_id TEXT NOT NULL,
        study_session_id TEXT NOT NULL, is_test INTEGER NOT NULL CHECK(is_test IN (0, 1)),
        status TEXT NOT NULL CHECK(status IN ('active', 'completed', 'retired')),
        question_number INTEGER NOT NULL CHECK(question_number BETWEEN 1 AND 3),
        phase TEXT NOT NULL, metadata TEXT NOT NULL, created_at TEXT NOT NULL
    )""",
    """CREATE UNIQUE INDEX IF NOT EXISTS progress_one_active_attempt
        ON progress_attempts(study_id, participant_id, study_session_id, is_test)
        WHERE status = 'active'""",
    """CREATE TABLE IF NOT EXISTS progress_tasks (
        attempt_id TEXT NOT NULL REFERENCES progress_attempts(attempt_id),
        number INTEGER NOT NULL CHECK(number BETWEEN 1 AND 3), snapshot TEXT NOT NULL,
        PRIMARY KEY(attempt_id, number)
    )""",
    """CREATE TABLE IF NOT EXISTS progress_drafts (
        attempt_id TEXT NOT NULL, question_number INTEGER NOT NULL,
        phase TEXT NOT NULL CHECK(phase IN ('first-answer', 'final-answer')),
        text TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision > 0),
        saved_at TEXT NOT NULL,
        PRIMARY KEY(attempt_id, question_number, phase),
        FOREIGN KEY(attempt_id, question_number) REFERENCES progress_tasks(attempt_id, number)
    )""",
    """CREATE TABLE IF NOT EXISTS progress_first_answers (
        attempt_id TEXT NOT NULL, question_number INTEGER NOT NULL,
        text TEXT, outcome TEXT NOT NULL CHECK(outcome IN ('answered', 'unknown')),
        submitted_at TEXT NOT NULL,
        PRIMARY KEY(attempt_id, question_number),
        FOREIGN KEY(attempt_id, question_number) REFERENCES progress_tasks(attempt_id, number),
        CHECK((outcome = 'unknown' AND text IS NULL)
            OR (outcome = 'answered' AND text IS NOT NULL AND length(trim(text)) > 0))
    )""",
)


def _now():
    return datetime.now(TIME_ZONE).isoformat(timespec="microseconds")


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class ProgressStore:
    """One short-lived connection/transaction per operation, safe across workers.

    sqlite3's timeout retries busy locks for a bounded period. A timeout or
    commit error propagates to the caller; success is returned only after commit.
    """

    def __init__(self, path, timeout=5):
        self.path = Path(path)
        self.timeout = timeout
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = self._connect()
        try:
            # Rollback journals avoid depending on the deployed WAL version.
            if db.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
                raise RuntimeError("Progress storage requires a durable rollback journal")
        finally:
            db.close()
        with self._transaction(write=True) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError("Unsupported progress database schema version")
            for statement in SCHEMA:
                db.execute(statement)
            db.execute("PRAGMA user_version=2")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
        except BaseException:
            db.close()
            raise
        return db

    @contextmanager
    def _transaction(self, *, write=False):
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _find_attempt(db, key, attempt_id):
        row = db.execute("""SELECT * FROM progress_attempts WHERE attempt_id = ?
            AND study_id = ? AND participant_id = ? AND study_session_id = ? AND is_test = ?""",
                         (attempt_id, *key.scope)).fetchone()
        if row is None:
            raise AttemptNotFound("Attempt not found in this participant/study scope")
        return row

    @staticmethod
    def _snapshot(db, row):
        attempt = dict(row)
        attempt["is_test"] = bool(attempt["is_test"])
        attempt["metadata"] = json.loads(attempt["metadata"])
        tasks = [{"number": task["number"], "snapshot": json.loads(task["snapshot"]),
                  "drafts": {}, "first_answer": None}
                 for task in db.execute("""SELECT number, snapshot FROM progress_tasks
                     WHERE attempt_id = ? ORDER BY number""", (row["attempt_id"],))]
        for draft in db.execute("SELECT * FROM progress_drafts WHERE attempt_id = ?", (row["attempt_id"],)):
            tasks[draft["question_number"] - 1]["drafts"][draft["phase"]] = {
                "text": draft["text"], "revision": draft["revision"], "saved_at": draft["saved_at"]}
        for answer in db.execute("SELECT * FROM progress_first_answers WHERE attempt_id = ?",
                                 (row["attempt_id"],)):
            tasks[answer["question_number"] - 1]["first_answer"] = {
                "text": answer["text"], "outcome": answer["outcome"],
                "submitted_at": answer["submitted_at"]}
        attempt["tasks"] = tasks
        return attempt

    def start_or_resume(self, key, questions, metadata=None):
        """Snapshot a new attempt or resume it without re-reading configuration.

        The configuration adapter must establish date/enrollment eligibility
        before calling this method; this storage API is not an access gate.
        Questions are passed in their already-selected display order.
        """
        with self._transaction(write=True) as db:
            row = db.execute("""SELECT * FROM progress_attempts WHERE study_id = ?
                AND participant_id = ? AND study_session_id = ? AND is_test = ?
                AND status != 'retired' ORDER BY rowid DESC LIMIT 1""", key.scope).fetchone()
            if row is not None:
                return self._snapshot(db, row)
            if not isinstance(questions, (list, tuple)) or len(questions) != 3:
                raise ValueError("Exactly three questions are required")
            topic_ids, snapshots = set(), []
            for question in questions:
                if (not isinstance(question, dict)
                        or any(not isinstance(question.get(field), str) or not question[field].strip()
                               for field in ("topic_id", "question"))
                        or question["topic_id"] in topic_ids):
                    raise ValueError("Questions need unique topic IDs and non-blank wording")
                topic_ids.add(question["topic_id"])
                snapshots.append(_json(question))
            if metadata is not None and not isinstance(metadata, dict):
                raise ValueError("Attempt metadata must be a dictionary")
            attempt_id = uuid.uuid4().hex
            db.execute("""INSERT INTO progress_attempts
                (attempt_id, study_id, participant_id, study_session_id, is_test, status,
                 question_number, phase, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, 'active', 1, 'first-answer', ?, ?)""",
                       (attempt_id, *key.scope, _json(metadata or {}), _now()))
            db.executemany("INSERT INTO progress_tasks(attempt_id, number, snapshot) VALUES (?, ?, ?)",
                           [(attempt_id, n, text) for n, text in enumerate(snapshots, 1)])
            return self._snapshot(db, self._find_attempt(db, key, attempt_id))

    def get_attempt(self, key, attempt_id):
        with self._transaction() as db:
            return self._snapshot(db, self._find_attempt(db, key, attempt_id))

    def runtime_settings(self):
        """Report the actual connection settings for deployment verification."""
        pragmas = ("journal_mode", "synchronous", "foreign_keys", "busy_timeout")
        with self._transaction() as db:
            settings = {name: db.execute(f"PRAGMA {name}").fetchone()[0] for name in pragmas}
            settings["schema_version"] = db.execute("PRAGMA user_version").fetchone()[0]
        return {**settings, "sqlite_version": sqlite3.sqlite_version}

    def save_draft(self, key, attempt_id, question_number, phase, text, expected_revision):
        """Save exact draft text; revision 0 means no draft has been saved yet.

        This does not submit an answer or change progress/search eligibility.
        Keep the local draft and offer retry when this method raises an error.
        """
        if (type(question_number) is not int or not 1 <= question_number <= 3
                or phase not in DRAFT_PHASES or not isinstance(text, str)
                or type(expected_revision) is not int or expected_revision < 0):
            raise ValueError("Invalid draft question, phase, text or revision")
        with self._transaction(write=True) as db:
            attempt = self._find_attempt(db, key, attempt_id)
            if attempt["status"] != "active":
                raise ValueError("Cannot write to a completed or retired attempt")
            if phase == "first-answer" and db.execute("""SELECT 1 FROM progress_first_answers
                    WHERE attempt_id = ? AND question_number = ?""", (attempt_id, question_number)).fetchone():
                raise SubmissionConflict("The first answer is already submitted")
            draft_key = (attempt_id, question_number, phase)
            current = db.execute("""SELECT revision FROM progress_drafts
                WHERE attempt_id = ? AND question_number = ? AND phase = ?""", draft_key).fetchone()
            revision = current["revision"] if current else 0
            if revision != expected_revision:
                raise DraftConflict("Draft changed; reload the saved revision before retrying")
            saved = {"text": text, "revision": revision + 1, "saved_at": _now()}
            db.execute("""INSERT INTO progress_drafts
                (attempt_id, question_number, phase, text, revision, saved_at) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(attempt_id, question_number, phase) DO UPDATE SET
                    text = excluded.text, revision = excluded.revision, saved_at = excluded.saved_at""",
                       (*draft_key, saved["text"], saved["revision"], saved["saved_at"]))
        return saved

    def submit_first_answer(self, key, attempt_id, question_number, text=None, *, unknown_confirmed=False):
        """Atomically preserve an original first answer and enter the search phase.

        Unknown answers require an explicit boolean confirmation and no text.
        Identical retries return the original answer; different payloads conflict.
        This storage method does not register routes or emit logging events.
        """
        if (type(question_number) is not int or not 1 <= question_number <= 3
                or type(unknown_confirmed) is not bool):
            raise ValueError("Invalid question number or unknown-answer confirmation")
        if unknown_confirmed:
            if text is not None:
                raise ValueError("A confirmed unknown answer must not include answer text")
            outcome = "unknown"
        else:
            if not isinstance(text, str) or not text.strip():
                raise ValueError("A non-blank first answer or confirmed unknown choice is required")
            outcome = "answered"
        with self._transaction(write=True) as db:
            attempt = self._find_attempt(db, key, attempt_id)
            if attempt["status"] != "active":
                raise SubmissionConflict("Cannot submit to a completed or retired attempt")
            existing = db.execute("""SELECT text, outcome, submitted_at FROM progress_first_answers
                WHERE attempt_id = ? AND question_number = ?""", (attempt_id, question_number)).fetchone()
            if existing is not None:
                if existing["text"] != text or existing["outcome"] != outcome:
                    raise SubmissionConflict("The original first answer cannot be replaced")
                return dict(existing)
            if attempt["question_number"] != question_number or attempt["phase"] != "first-answer":
                raise SubmissionConflict("The submission does not match the current question and phase")
            answer = {"text": text, "outcome": outcome, "submitted_at": _now()}
            db.execute("""INSERT INTO progress_first_answers
                (attempt_id, question_number, text, outcome, submitted_at) VALUES (?, ?, ?, ?, ?)""",
                       (attempt_id, question_number, text, outcome, answer["submitted_at"]))
            db.execute("UPDATE progress_attempts SET phase = 'search' WHERE attempt_id = ?", (attempt_id,))
        return answer


def init_progress(app):
    """Configure storage explicitly; the new participant flow will call this."""
    directory = app.config.get("RESEARCH_STATE_DIR") or os.getenv("RESEARCH_STATE_DIR", "research_state")
    app.config.setdefault("SOL_PROGRESS_DB_PATH", os.getenv("SOL_PROGRESS_DB_PATH") or
                          str(Path(directory) / "study-progress.sqlite3"))
    store = ProgressStore(app.config["SOL_PROGRESS_DB_PATH"])
    app.extensions["study_progress"] = store
    return store
