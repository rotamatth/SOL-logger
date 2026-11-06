"""Durable attempts, drafts and original answers, independent of browser sessions.

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
    """CREATE TABLE IF NOT EXISTS progress_final_answers (
        attempt_id TEXT NOT NULL, question_number INTEGER NOT NULL,
        text TEXT NOT NULL CHECK(length(trim(text)) > 0), submitted_at TEXT NOT NULL,
        PRIMARY KEY(attempt_id, question_number),
        FOREIGN KEY(attempt_id, question_number) REFERENCES progress_tasks(attempt_id, number)
    )""",
    """CREATE TABLE IF NOT EXISTS progress_reviews (
        attempt_id TEXT NOT NULL, question_number INTEGER NOT NULL, browser_scope TEXT NOT NULL,
        continued INTEGER NOT NULL DEFAULT 0 CHECK(continued IN (0, 1)),
        PRIMARY KEY(attempt_id, question_number),
        FOREIGN KEY(attempt_id, question_number) REFERENCES progress_final_answers(attempt_id, question_number)
    )""",
    """CREATE TABLE IF NOT EXISTS progress_events (
        event_id TEXT PRIMARY KEY, event_key TEXT NOT NULL UNIQUE,
        attempt_id TEXT NOT NULL, question_number INTEGER NOT NULL,
        type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, published_at TEXT,
        FOREIGN KEY(attempt_id, question_number) REFERENCES progress_tasks(attempt_id, number)
    )""",
    """CREATE TABLE IF NOT EXISTS progress_recap_drafts (
        attempt_id TEXT NOT NULL, question_number INTEGER NOT NULL,
        answer_phase TEXT NOT NULL CHECK(answer_phase IN ('first-answer', 'final-answer')),
        editing_attempt_id TEXT NOT NULL REFERENCES progress_attempts(attempt_id),
        text TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision > 0),
        saved_at TEXT NOT NULL, editing_context TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
        base_answer_revision INTEGER,
        PRIMARY KEY(attempt_id, question_number, answer_phase, editing_attempt_id),
        FOREIGN KEY(attempt_id, question_number) REFERENCES progress_tasks(attempt_id, number)
    )""",
    """CREATE TABLE IF NOT EXISTS progress_answer_revisions (
        attempt_id TEXT NOT NULL, question_number INTEGER NOT NULL,
        answer_phase TEXT NOT NULL CHECK(answer_phase IN ('first-answer', 'final-answer')),
        revision INTEGER NOT NULL CHECK(revision > 0), before_text TEXT, after_text TEXT NOT NULL,
        edited_at TEXT NOT NULL, editing_context TEXT NOT NULL, request_id TEXT NOT NULL,
        PRIMARY KEY(attempt_id, question_number, answer_phase, revision),
        UNIQUE(attempt_id, request_id),
        FOREIGN KEY(attempt_id, question_number) REFERENCES progress_tasks(attempt_id, number)
    )""",
    """CREATE TABLE IF NOT EXISTS progress_repeat_requests (
        study_id TEXT NOT NULL, participant_id TEXT NOT NULL, study_session_id TEXT NOT NULL,
        is_test INTEGER NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL,
        attempt_id TEXT NOT NULL REFERENCES progress_attempts(attempt_id),
        PRIMARY KEY(study_id, participant_id, study_session_id, is_test, request_id)
    )""",
    """CREATE TABLE IF NOT EXISTS progress_recap_exports (
        attempt_id TEXT PRIMARY KEY REFERENCES progress_attempts(attempt_id),
        finished_at TEXT NOT NULL, pdf BLOB NOT NULL
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
            if version not in (0, 1, 2, 3, 4, 5, 6, 7):
                raise ValueError("Unsupported progress database schema version")
            for statement in SCHEMA:
                db.execute(statement)
            # Nullable for historical measurements that were never collected.
            for table in ("progress_first_answers", "progress_drafts"):
                columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
                if "confidence" not in columns:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN confidence INTEGER "
                               "CHECK(confidence IS NULL OR confidence BETWEEN 1 AND 3)")
            recap_columns = {row["name"] for row in db.execute("PRAGMA table_info(progress_recap_drafts)")}
            if "base_answer_revision" not in recap_columns:
                db.execute("ALTER TABLE progress_recap_drafts ADD COLUMN base_answer_revision INTEGER")
            if version < 4:
                self._backfill_events(db)
            db.execute("PRAGMA user_version=7")

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
                  "drafts": {}, "first_answer": None, "final_answer": None}
                 for task in db.execute("""SELECT number, snapshot FROM progress_tasks
                     WHERE attempt_id = ? ORDER BY number""", (row["attempt_id"],))]
        for draft in db.execute("SELECT * FROM progress_drafts WHERE attempt_id = ?", (row["attempt_id"],)):
            tasks[draft["question_number"] - 1]["drafts"][draft["phase"]] = {
                "text": draft["text"], "revision": draft["revision"], "saved_at": draft["saved_at"]}
            if draft["phase"] == "first-answer":
                tasks[draft["question_number"] - 1]["drafts"][draft["phase"]]["confidence"] = draft["confidence"]
        for answer in db.execute("SELECT * FROM progress_first_answers WHERE attempt_id = ?",
                                 (row["attempt_id"],)):
            tasks[answer["question_number"] - 1]["first_answer"] = {
                "text": answer["text"], "outcome": answer["outcome"], "confidence": answer["confidence"],
                "submitted_at": answer["submitted_at"]}
        for answer in db.execute("SELECT * FROM progress_final_answers WHERE attempt_id = ?",
                                 (row["attempt_id"],)):
            tasks[answer["question_number"] - 1]["final_answer"] = {
                "text": answer["text"], "submitted_at": answer["submitted_at"]}
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

    def latest_attempt(self, key):
        """Include retired attempts so admission cannot silently authorize a retake."""
        with self._transaction() as db:
            row = db.execute("""SELECT * FROM progress_attempts WHERE study_id = ?
                AND participant_id = ? AND study_session_id = ? AND is_test = ?
                ORDER BY rowid DESC LIMIT 1""", key.scope).fetchone()
            return self._snapshot(db, row) if row is not None else None

    def repeat_attempt(self, key, source_attempt_id, *, authorized_by, request_id, technical_session_id, log_id):
        """Storage boundary for #15; caller must first authorize/admit the new run.

        Clone the source's immutable questions and metadata, with fresh technical
        identity. Retire the source/current attempt atomically; never erase history.
        A stable authorization request ID makes lost acknowledgements safe.
        """
        values = (authorized_by, request_id, technical_session_id, log_id)
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("An authorization, request ID and new technical run identity are required")
        payload = _json([source_attempt_id, *values])
        with self._transaction(write=True) as db:
            source = self._find_attempt(db, key, source_attempt_id)
            previous = db.execute("""SELECT * FROM progress_repeat_requests WHERE study_id = ?
                AND participant_id = ? AND study_session_id = ? AND is_test = ? AND request_id = ?""",
                                  (*key.scope, request_id)).fetchone()
            if previous:
                if previous["payload"] != payload:
                    raise SubmissionConflict("The repeat request cannot be changed")
                return self._snapshot(db, self._find_attempt(db, key, previous["attempt_id"]))
            metadata = json.loads(source["metadata"])
            if db.execute("""SELECT 1 FROM progress_attempts
                    WHERE json_extract(metadata, '$.technical_session_id') = ?
                       OR json_extract(metadata, '$.log_id') = ?""", (technical_session_id, log_id)).fetchone():
                raise SubmissionConflict("A repeat requires a new technical run and log ID")
            metadata.update(technical_session_id=technical_session_id, log_id=log_id,
                            source_attempt_id=source_attempt_id, repeat_authorized_by=authorized_by,
                            repeat_request_id=request_id)
            db.execute("""UPDATE progress_attempts SET status = 'retired' WHERE study_id = ?
                AND participant_id = ? AND study_session_id = ? AND is_test = ?
                AND (status = 'active' OR attempt_id = ?)""", (*key.scope, source_attempt_id))
            attempt_id = uuid.uuid4().hex
            db.execute("""INSERT INTO progress_attempts
                (attempt_id, study_id, participant_id, study_session_id, is_test, status,
                 question_number, phase, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, 'active', 1, 'first-answer', ?, ?)""",
                       (attempt_id, *key.scope, _json(metadata), _now()))
            db.execute("""INSERT INTO progress_tasks(attempt_id, number, snapshot)
                SELECT ?, number, snapshot FROM progress_tasks WHERE attempt_id = ?""",
                       (attempt_id, source_attempt_id))
            db.execute("INSERT INTO progress_repeat_requests VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (*key.scope, request_id, payload, attempt_id))
            return self._snapshot(db, self._find_attempt(db, key, attempt_id))

    def _recap_context(self, db, key, attempt_id, editing_context, *, write=True):
        target = self._find_attempt(db, key, attempt_id)
        if target["status"] != "completed" and (write or target["status"] != "retired"):
            raise SubmissionConflict("Recap writes require a completed, non-retired target attempt")
        fields = ("study_session_id", "attempt_id", "technical_session_id")
        if (not isinstance(editing_context, dict)
                or any(not isinstance(editing_context.get(field), str) or not editing_context[field].strip()
                       for field in fields)):
            raise ValueError("Explicit editing session, attempt and technical run context is required")
        editor_key = AttemptKey(key.study_id, key.participant_id, editing_context["study_session_id"], key.is_test)
        editor = self._find_attempt(db, editor_key, editing_context["attempt_id"])
        if editor["status"] == "retired":
            raise SubmissionConflict("The editing attempt is retired")
        if write and self._recap_is_finished(db, editor["attempt_id"]):
            raise SubmissionConflict("The editing session is finished")
        if json.loads(editor["metadata"]).get("technical_session_id") != editing_context["technical_session_id"]:
            raise ValueError("The editing technical run does not match the attempt")
        return _json(editing_context)

    @staticmethod
    def _recap_is_finished(db, attempt_id):
        return db.execute("SELECT 1 FROM progress_recap_exports WHERE attempt_id=?", (attempt_id,)).fetchone() is not None

    def recap_finished(self, attempt_id):
        with self._transaction() as db:
            return self._recap_is_finished(db, attempt_id)

    def recap_pdf(self, attempt_id):
        with self._transaction() as db:
            row = db.execute("SELECT pdf FROM progress_recap_exports WHERE attempt_id=?", (attempt_id,)).fetchone()
            return row["pdf"] if row else None

    @staticmethod
    def _check_recap_values(question_number, answer_phase, text, expected_revision):
        if (type(question_number) is not int or not 1 <= question_number <= 3
                or answer_phase not in DRAFT_PHASES or not isinstance(text, str)
                or type(expected_revision) is not int or expected_revision < 0):
            raise ValueError("Invalid recap target, text or revision")

    def save_recap_draft(self, key, attempt_id, question_number, answer_phase, text, expected_revision,
                         *, editing_context, base_answer_revision=None):
        """Save a recap-edit draft separately from originals and confirmed revisions."""
        self._check_recap_values(question_number, answer_phase, text, expected_revision)
        with self._transaction(write=True) as db:
            context = self._recap_context(db, key, attempt_id, editing_context)
            scope = (attempt_id, question_number, answer_phase, editing_context["attempt_id"])
            if base_answer_revision is not None and (
                    type(base_answer_revision) is not int
                    or base_answer_revision != self._answer_revision(db, *scope[:3])):
                raise DraftConflict("The final answer was revised before this draft could be saved")
            current = db.execute("""SELECT revision, text, active, saved_at, base_answer_revision
                FROM progress_recap_drafts WHERE attempt_id = ?
                AND question_number = ? AND answer_phase = ? AND editing_attempt_id = ?""", scope).fetchone()
            if (current and current["active"] and current["revision"] == expected_revision + 1
                    and current["text"] == text and current["base_answer_revision"] == base_answer_revision):
                return {"text": text, "revision": current["revision"], "saved_at": current["saved_at"],
                        "editing_context": editing_context}
            if (current["revision"] if current else 0) != expected_revision:
                raise DraftConflict("The recap draft changed")
            saved = {"text": text, "revision": expected_revision + 1, "saved_at": _now(),
                     "editing_context": editing_context}
            db.execute("""INSERT INTO progress_recap_drafts VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(attempt_id, question_number, answer_phase, editing_attempt_id) DO UPDATE SET
                text=excluded.text, revision=excluded.revision, saved_at=excluded.saved_at,
                editing_context=excluded.editing_context, active=1, base_answer_revision=excluded.base_answer_revision""",
                       (*scope, text, saved["revision"], saved["saved_at"], context, base_answer_revision))
        return saved

    @staticmethod
    def _answer_revision(db, attempt_id, number, phase):
        return db.execute("""SELECT COALESCE(MAX(revision), 0) FROM progress_answer_revisions
            WHERE attempt_id=? AND question_number=? AND answer_phase=?""", (attempt_id, number, phase)).fetchone()[0]

    @staticmethod
    def _revision(row):
        return {**dict(row), "editing_context": json.loads(row["editing_context"])}

    def append_answer_revision(self, key, attempt_id, question_number, answer_phase, text, expected_revision,
                               *, request_id, editing_context):
        """Append a recap revision using the prior revision as its immutable before-text."""
        self._check_recap_values(question_number, answer_phase, text, expected_revision)
        if not text.strip() or not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("A nonblank revision and stable request ID are required")
        with self._transaction(write=True) as db:
            context = self._recap_context(db, key, attempt_id, editing_context)
            return self._append_revision(db, attempt_id, question_number, answer_phase, text, expected_revision,
                                         request_id, editing_context, context)

    def _append_revision(self, db, attempt_id, question_number, answer_phase, text, expected_revision,
                         request_id, editing_context, context):
        existing = db.execute("SELECT * FROM progress_answer_revisions WHERE attempt_id=? AND request_id=?",
                              (attempt_id, request_id)).fetchone()
        if existing:
            if (existing["question_number"] != question_number or existing["answer_phase"] != answer_phase
                    or existing["after_text"] != text or existing["revision"] != expected_revision + 1
                    or json.loads(existing["editing_context"]) != editing_context):
                raise SubmissionConflict("A confirmed revision request cannot be changed")
            return self._revision(existing)
        scope = (attempt_id, question_number, answer_phase)
        latest = db.execute("""SELECT * FROM progress_answer_revisions WHERE attempt_id=?
            AND question_number=? AND answer_phase=? ORDER BY revision DESC LIMIT 1""", scope).fetchone()
        if (latest["revision"] if latest else 0) != expected_revision:
            raise DraftConflict("The answer was revised by another editor")
        table = "progress_first_answers" if answer_phase == "first-answer" else "progress_final_answers"
        original = db.execute(f"SELECT text FROM {table} WHERE attempt_id=? AND question_number=?",
                              (attempt_id, question_number)).fetchone()
        before = latest["after_text"] if latest else original["text"]
        db.execute("INSERT INTO progress_answer_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (*scope, expected_revision + 1, before, text, _now(), context, request_id))
        # Keep a monotonic draft revision even after confirmation, including
        # when the edit was confirmed before its first autosave arrived.
        db.execute("""INSERT INTO progress_recap_drafts VALUES (?, ?, ?, ?, '', 1, ?, ?, 0, NULL)
            ON CONFLICT(attempt_id, question_number, answer_phase, editing_attempt_id) DO UPDATE SET
            text='', revision=progress_recap_drafts.revision+1, saved_at=excluded.saved_at,
            editing_context=excluded.editing_context, active=0, base_answer_revision=NULL
            WHERE progress_recap_drafts.active=0 OR progress_recap_drafts.text=?""",
                   (*scope, editing_context["attempt_id"], _now(), context, text))
        saved = db.execute("SELECT * FROM progress_answer_revisions WHERE attempt_id=? AND request_id=?",
                           (attempt_id, request_id)).fetchone()
        return self._revision(saved)

    def recap_state(self, key, attempt_id, *, editing_context):
        """Read originals, revision history and the current editing session's drafts."""
        with self._transaction() as db:
            self._recap_context(db, key, attempt_id, editing_context, write=False)
            return self._recap_state(db, self._find_attempt(db, key, attempt_id), editing_context["attempt_id"])

    def _recap_state(self, db, row, editing_attempt_id):
        attempt_id = row["attempt_id"]
        state = self._snapshot(db, row)
        for task in state["tasks"]:
            task.update(revisions=[], recap_drafts={}, recap_draft_revisions={})
        for row in db.execute("SELECT * FROM progress_answer_revisions WHERE attempt_id=? ORDER BY rowid",
                              (attempt_id,)):
            state["tasks"][row["question_number"] - 1]["revisions"].append(self._revision(row))
        for row in db.execute("SELECT * FROM progress_recap_drafts WHERE attempt_id=? AND editing_attempt_id=?",
                              (attempt_id, editing_attempt_id)):
            task = state["tasks"][row["question_number"] - 1]
            task["recap_draft_revisions"][row["answer_phase"]] = row["revision"]
            if not row["active"]:
                continue
            task["recap_drafts"][row["answer_phase"]] = {
                "text": row["text"], "revision": row["revision"], "saved_at": row["saved_at"],
                "editing_context": json.loads(row["editing_context"])}
            if row["base_answer_revision"] is not None:
                task["recap_drafts"][row["answer_phase"]]["base_answer_revision"] = row["base_answer_revision"]
        return state

    @staticmethod
    def _recap_targets(db, editor):
        session = json.loads(editor["metadata"])["study_session_snapshot"]
        targets = {session["number"]: editor}
        for row in db.execute("""SELECT * FROM progress_attempts WHERE study_id=? AND participant_id=?
                AND is_test=? AND status='completed' ORDER BY rowid DESC""",
                              (editor["study_id"], editor["participant_id"], editor["is_test"])):
            past = json.loads(row["metadata"]).get("study_session_snapshot") or {}
            number = past.get("number")
            if (type(number) is int and 1 <= number < session["number"]
                    and past.get("school_year") == session.get("school_year")
                    and past.get("date", "") < session["date"]):
                targets.setdefault(number, row)
        return targets

    def recap_columns(self, key, attempt_id):
        with self._transaction() as db:
            editor = self._find_attempt(db, key, attempt_id)
            if editor["status"] != "completed":
                raise SubmissionConflict("Complete all three questions before opening the recap")
            return {number: self._recap_state(db, row, attempt_id)
                    for number, row in self._recap_targets(db, editor).items()}

    def commit_recap(self, key, attempt_id, expected_drafts, render_pdf=None):
        """Commit every pending final-answer edit and, at finish, the immutable PDF and outbox."""
        snapshot = self.recap_columns(key, attempt_id) if render_pdf is not None else None
        if snapshot is not None and self.recap_finished(attempt_id):
            return  # A lost acknowledgement can retry the existing receipt.
        # Layout may take time for long answers. Hold no SQLite writer while rendering.
        pdf = render_pdf(snapshot) if render_pdf is not None else None
        with self._transaction(write=True) as db:
            editor = self._find_attempt(db, key, attempt_id)
            if editor["status"] != "completed":
                raise SubmissionConflict("Complete all three questions before saving the recap")
            if self._recap_is_finished(db, attempt_id):
                if render_pdf is not None:
                    return  # The PDF and events are already durable. Retry publication only.
                raise SubmissionConflict("The session is already finished")
            metadata = json.loads(editor["metadata"])
            context = {"study_session_id": editor["study_session_id"], "attempt_id": attempt_id,
                       "technical_session_id": metadata["technical_session_id"]}
            if render_pdf is not None:
                self._queue_recap_event(db, editor, "sessionCompleted", {})
            targets = self._recap_targets(db, editor)
            if snapshot is not None and snapshot != {n: self._recap_state(db, row, attempt_id)
                                                      for n, row in targets.items()}:
                raise DraftConflict("The recap changed while its PDF was being prepared")
            rows = db.execute("""SELECT * FROM progress_recap_drafts
                WHERE editing_attempt_id=? AND answer_phase='final-answer'""", (attempt_id,)).fetchall()
            targets_by_id = {row["attempt_id"]: row for row in targets.values()}
            pending = [row for row in rows if row["active"]]
            if pending or render_pdf is not None:
                self._check_recap_draft_revisions(targets_by_id, rows, expected_drafts)
            for draft in pending:
                target = targets_by_id.get(draft["attempt_id"])
                if target is None:
                    raise DraftConflict("A draft's target is no longer available")
                self._commit_recap_draft(db, editor, target, draft, context)
            if pdf is not None:
                db.execute("INSERT INTO progress_recap_exports VALUES (?, ?, ?)", (attempt_id, _now(), pdf))
                self._queue_recap_event(db, editor, "studySessionFinished", {})
                if metadata["study_session_snapshot"]["number"] == 3:
                    self._queue_recap_event(db, editor, "experimentFinished", {})

    @staticmethod
    def _check_recap_draft_revisions(targets, rows, expected):
        revisions = {f"{row['attempt_id']}:{row['question_number']}": row["revision"] for row in rows}
        current = {f"{target}:{number}": revisions.get(f"{target}:{number}", 0)
                   for target in targets for number in (1, 2, 3)}
        if current != expected:
            raise DraftConflict("The recap drafts changed before confirmation")

    def _commit_recap_draft(self, db, editor, target, draft, context):
        number, text, attempt_id = draft["question_number"], draft["text"], target["attempt_id"]
        if not text.strip():
            raise ValueError("A final answer cannot be empty")
        latest = db.execute("""SELECT revision, after_text FROM progress_answer_revisions
            WHERE attempt_id=? AND question_number=? AND answer_phase='final-answer'
            ORDER BY revision DESC LIMIT 1""", (attempt_id, number)).fetchone()
        revision = latest["revision"] if latest else 0
        if draft["base_answer_revision"] is not None and draft["base_answer_revision"] != revision:
            raise DraftConflict("The final answer was revised before this draft could be confirmed")
        before = latest["after_text"] if latest else db.execute("""SELECT text FROM progress_final_answers
            WHERE attempt_id=? AND question_number=?""", (attempt_id, number)).fetchone()["text"]
        if text == before:
            db.execute("""UPDATE progress_recap_drafts SET active=0, revision=revision+1
                WHERE attempt_id=? AND question_number=? AND answer_phase='final-answer' AND editing_attempt_id=?""",
                       (attempt_id, number, editor["attempt_id"]))
            return
        request_id = f"recap:{editor['attempt_id']}:{number}:{draft['revision']}"
        saved = self._append_revision(db, attempt_id, number, "final-answer", text,
                                      revision, request_id, context, _json(context))
        self._queue_recap_event(db, editor, "RecapAnswerEdited", {
            "target_study_session_id": target["study_session_id"], "target_attempt_id": attempt_id,
            "target_task_number": number, "answerPhase": "post-search",
            "before_text": saved["before_text"], "after_text": saved["after_text"],
            "edited_at": saved["edited_at"],
        }, f":{attempt_id}:{request_id}")

    @staticmethod
    def _queue_answer_event(db, attempt, number, answer, event_type):
        event_id = uuid.uuid4().hex
        topics = [json.loads(row["snapshot"])["topic_id"] for row in db.execute(
            "SELECT snapshot FROM progress_tasks WHERE attempt_id = ? ORDER BY number", (attempt["attempt_id"],))]
        payload = {"event_id": event_id, "type": event_type, "timestamp": answer["submitted_at"],
                   "uid": attempt["participant_id"], "study_id": attempt["study_id"],
                   "study_session_id": attempt["study_session_id"], "attempt_id": attempt["attempt_id"],
                   "is_test": bool(attempt["is_test"]), "task_number": number,
                   "actual_topic_number": topics[number - 1], "task_order": topics,
                   "answer": answer["text"],
                   "answerPhase": "post-search" if event_type == "TaskEnded" else "pre-search"}
        if event_type == "OwnKnowledgeAnswerSubmitted":
            payload["outcome"] = answer["outcome"]
            payload["confidence"] = answer["confidence"]
        db.execute("""INSERT INTO progress_events
            (event_id, event_key, attempt_id, question_number, type, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(event_key) DO NOTHING""",
                   (event_id, f"{attempt['attempt_id']}:{number}:{event_type}", attempt["attempt_id"],
                    number, event_type, _json(payload), answer["submitted_at"]))

    def _backfill_events(self, db):
        answers = db.execute("""SELECT attempt_id, question_number, text, outcome, submitted_at, confidence,
                'OwnKnowledgeAnswerSubmitted' AS type, 0 AS position FROM progress_first_answers
            UNION ALL SELECT attempt_id, question_number, text, NULL, submitted_at, NULL,
                'TaskEnded', 1 FROM progress_final_answers
            ORDER BY attempt_id, question_number, position""").fetchall()
        for answer in answers:
            attempt = db.execute("SELECT * FROM progress_attempts WHERE attempt_id = ?",
                                 (answer["attempt_id"],)).fetchone()
            self._queue_answer_event(db, attempt, answer["question_number"], answer, answer["type"])

    def pending_events(self, key, attempt_id):
        """Read durable intents; reading never acknowledges log publication.

        Payloads contain logical study context. The later publisher must bind
        technical-run metadata and preserve the log store's receipt semantics.
        """
        with self._transaction() as db:
            self._find_attempt(db, key, attempt_id)
            return [{"event_id": row["event_id"], "type": row["type"],
                     "created_at": row["created_at"], "payload": json.loads(row["payload"])}
                    for row in db.execute("""SELECT * FROM progress_events
                        WHERE attempt_id = ? AND published_at IS NULL ORDER BY rowid""", (attempt_id,))]

    def task_started(self, attempt_id, question_number):
        with self._transaction() as db:
            return db.execute("SELECT 1 FROM progress_events WHERE event_key = ?",
                              (f"{attempt_id}:{question_number}:TaskStarted",)).fetchone() is not None

    def mark_task_started(self, key, attempt_id, question_number):
        """Queue TaskStarted once when the current first-answer page is shown."""
        if type(question_number) is not int or not 1 <= question_number <= 3:
            raise ValueError("Invalid question")
        with self._transaction(write=True) as db:
            attempt = self._find_attempt(db, key, attempt_id)
            if attempt["status"] != "active" or attempt["question_number"] != question_number:
                raise SubmissionConflict("This question is no longer active")
            topics = [json.loads(row["snapshot"])["topic_id"] for row in db.execute(
                "SELECT snapshot FROM progress_tasks WHERE attempt_id=? ORDER BY number", (attempt_id,))]
            timestamp = _now()
            payload = {"event_id": uuid.uuid4().hex, "type": "TaskStarted", "timestamp": timestamp,
                       "uid": key.participant_id, "study_id": key.study_id,
                       "study_session_id": key.study_session_id, "attempt_id": attempt_id,
                       "is_test": key.is_test, "task_number": question_number,
                       "actual_topic_number": topics[question_number - 1], "task_order": topics}
            db.execute("""INSERT INTO progress_events
                (event_id,event_key,attempt_id,question_number,type,payload,created_at)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(event_key) DO NOTHING""",
                       (payload["event_id"], f"{attempt_id}:{question_number}:TaskStarted", attempt_id,
                        question_number, "TaskStarted", _json(payload), timestamp))

    def acknowledge_event(self, key, attempt_id, event_id):
        """An internal publisher calls this only after durable log acknowledgement."""
        with self._transaction(write=True) as db:
            self._find_attempt(db, key, attempt_id)
            event = db.execute("""SELECT published_at FROM progress_events
                WHERE attempt_id = ? AND event_id = ?""", (attempt_id, event_id)).fetchone()
            if event is None:
                raise ValueError("Event not found in this attempt")
            published_at = event["published_at"]
            if published_at is None:
                published_at = _now()
                db.execute("UPDATE progress_events SET published_at = ? WHERE event_id = ?",
                           (published_at, event_id))
        return published_at

    def unpublished_attempts(self):
        """Internal recovery reads only attempts whose durable outbox needs delivery."""
        with self._transaction() as db:
            return [self._snapshot(db, row) for row in db.execute("""SELECT * FROM progress_attempts a
                WHERE EXISTS (SELECT 1 FROM progress_events e
                              WHERE e.attempt_id=a.attempt_id AND e.published_at IS NULL)""").fetchall()]

    def runtime_settings(self):
        """Report the actual connection settings for deployment verification."""
        pragmas = ("journal_mode", "synchronous", "foreign_keys", "busy_timeout")
        with self._transaction() as db:
            settings = {name: db.execute(f"PRAGMA {name}").fetchone()[0] for name in pragmas}
            settings["schema_version"] = db.execute("PRAGMA user_version").fetchone()[0]
        return {**settings, "sqlite_version": sqlite3.sqlite_version}

    def save_draft(self, key, attempt_id, question_number, phase, text, expected_revision, *, confidence=None):
        """Save exact draft text; revision 0 means no draft has been saved yet.

        This does not submit an answer or change progress/search eligibility.
        Keep the local draft and offer retry when this method raises an error.
        """
        if (type(question_number) is not int or not 1 <= question_number <= 3
                or phase not in DRAFT_PHASES or not isinstance(text, str)
                or type(expected_revision) is not int or expected_revision < 0):
            raise ValueError("Invalid draft question, phase, text or revision")
        if confidence is not None and (type(confidence) is not int or confidence not in (1, 2, 3)
                                       or phase != "first-answer"):
            raise ValueError("Invalid draft confidence")
        if not text.strip():
            confidence = None
        with self._transaction(write=True) as db:
            attempt = self._find_attempt(db, key, attempt_id)
            if attempt["status"] != "active":
                raise ValueError("Cannot write to a completed or retired attempt")
            if phase == "first-answer" and db.execute("""SELECT 1 FROM progress_first_answers
                    WHERE attempt_id = ? AND question_number = ?""", (attempt_id, question_number)).fetchone():
                raise SubmissionConflict("The first answer is already submitted")
            if phase == "final-answer" and db.execute("""SELECT 1 FROM progress_final_answers
                    WHERE attempt_id = ? AND question_number = ?""", (attempt_id, question_number)).fetchone():
                raise SubmissionConflict("The final answer is already submitted")
            draft_key = (attempt_id, question_number, phase)
            current = db.execute("""SELECT revision FROM progress_drafts
                WHERE attempt_id = ? AND question_number = ? AND phase = ?""", draft_key).fetchone()
            revision = current["revision"] if current else 0
            if revision != expected_revision:
                raise DraftConflict("Draft changed; reload the saved revision before retrying")
            saved = {"text": text, "revision": revision + 1, "saved_at": _now()}
            if phase == "first-answer":
                saved["confidence"] = confidence
            db.execute("""INSERT INTO progress_drafts
                (attempt_id, question_number, phase, text, revision, saved_at, confidence) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(attempt_id, question_number, phase) DO UPDATE SET
                    text = excluded.text, revision = excluded.revision, saved_at = excluded.saved_at,
                    confidence = excluded.confidence""",
                       (*draft_key, saved["text"], saved["revision"], saved["saved_at"], confidence))
        return saved

    def submit_first_answer(self, key, attempt_id, question_number, text=None, *, unknown_confirmed=False,
                            confidence=None):
        """Atomically preserve an original first answer and enter the search phase.

        Unknown answers require an explicit boolean confirmation and no text.
        Identical retries return the original answer; different payloads conflict.
        Confidence is collected for typed answers and queued in the same transaction.
        """
        if (type(question_number) is not int or not 1 <= question_number <= 3
                or type(unknown_confirmed) is not bool):
            raise ValueError("Invalid question number or unknown-answer confirmation")
        if unknown_confirmed:
            if text is not None or confidence is not None:
                raise ValueError("A confirmed unknown answer must not include text or confidence")
            outcome = "unknown"
        else:
            if not isinstance(text, str) or not text.strip():
                raise ValueError("A non-blank first answer or confirmed unknown choice is required")
            outcome = "answered"
            if confidence is not None and (type(confidence) is not int or confidence not in (1, 2, 3)):
                raise ValueError("Choose confidence for the first answer")
        with self._transaction(write=True) as db:
            attempt = self._find_attempt(db, key, attempt_id)
            if attempt["status"] != "active":
                raise SubmissionConflict("Cannot submit to a completed or retired attempt")
            existing = db.execute("""SELECT text, outcome, confidence, submitted_at FROM progress_first_answers
                WHERE attempt_id = ? AND question_number = ?""", (attempt_id, question_number)).fetchone()
            if existing is not None:
                if (existing["text"] != text or existing["outcome"] != outcome
                        or existing["confidence"] != confidence):
                    raise SubmissionConflict("The original first answer cannot be replaced")
                return dict(existing)
            if attempt["question_number"] != question_number or attempt["phase"] != "first-answer":
                raise SubmissionConflict("The submission does not match the current question and phase")
            if outcome == "answered" and confidence is None:
                raise ValueError("Choose confidence for the first answer")
            answer = {"text": text, "outcome": outcome, "confidence": confidence, "submitted_at": _now()}
            db.execute("""INSERT INTO progress_first_answers
                (attempt_id, question_number, text, outcome, confidence, submitted_at) VALUES (?, ?, ?, ?, ?, ?)""",
                       (attempt_id, question_number, text, outcome, confidence, answer["submitted_at"]))
            self._queue_answer_event(db, attempt, question_number, answer, "OwnKnowledgeAnswerSubmitted")
            db.execute("UPDATE progress_attempts SET phase = 'search' WHERE attempt_id = ?", (attempt_id,))
        return answer

    def record_session_event(self, key, attempt_id, event_type):
        """Keep completion/explicit closure events after retiring reward screens."""
        if event_type not in ("sessionCompleted", "experimentFinished"):
            raise ValueError("Invalid session event")
        with self._transaction(write=True) as db:
            attempt = self._find_attempt(db, key, attempt_id)
            if attempt["status"] != "completed":
                raise SubmissionConflict("Session events require all three confirmed final answers")
            self._queue_recap_event(db, attempt, event_type, {})

    @staticmethod
    def _queue_recap_event(db, attempt, event_type, extra, event_suffix=""):
        attempt_id = attempt["attempt_id"]
        topics = [json.loads(row["snapshot"])["topic_id"] for row in db.execute(
            "SELECT snapshot FROM progress_tasks WHERE attempt_id = ? ORDER BY number", (attempt_id,))]
        timestamp = _now()
        payload = {"event_id": uuid.uuid4().hex, "type": event_type, "timestamp": timestamp,
                   "uid": attempt["participant_id"], "study_id": attempt["study_id"],
                   "study_session_id": attempt["study_session_id"], "attempt_id": attempt_id,
                   "is_test": bool(attempt["is_test"]), "task_number": 3, "actual_topic_number": topics[2],
                   "task_order": topics, "totalTasks": 3, **extra}
        db.execute("""INSERT INTO progress_events
            (event_id, event_key, attempt_id, question_number, type, payload, created_at)
            VALUES (?, ?, ?, 3, ?, ?, ?) ON CONFLICT(event_key) DO NOTHING""",
                   (payload["event_id"], f"{attempt_id}:3:{event_type}{event_suffix}", attempt_id,
                    event_type, _json(payload), timestamp))

    def review_state(self, attempt_id, browser_scope):
        with self._transaction() as db:
            return dict(db.execute("""SELECT question_number, continued FROM progress_reviews
                WHERE attempt_id = ? AND browser_scope = ? ORDER BY question_number""", (attempt_id, browser_scope)))

    def finish_review(self, attempt_id, browser_scope, question_number):
        with self._transaction(write=True) as db:
            db.execute("""UPDATE progress_reviews SET continued = 1
                WHERE attempt_id = ? AND browser_scope = ? AND question_number = ?""",
                       (attempt_id, browser_scope, question_number))

    def submit_final_answer(self, key, attempt_id, question_number, text, *, browser_scope=None):
        """Preserve a confirmed post-search answer and atomically advance once.

        Identical retries return the original, including after Q3 completes the
        attempt into recap. Finishing the recap/session is a separate action.
        Retired attempts reject all submissions, including identical retries.
        """
        if (type(question_number) is not int or not 1 <= question_number <= 3
                or not isinstance(text, str) or not text.strip()):
            raise ValueError("A valid question number and non-blank final answer are required")
        with self._transaction(write=True) as db:
            attempt = self._find_attempt(db, key, attempt_id)
            if attempt["status"] == "retired":
                raise SubmissionConflict("Cannot submit to a retired attempt")
            existing = db.execute("""SELECT text, submitted_at FROM progress_final_answers
                WHERE attempt_id = ? AND question_number = ?""", (attempt_id, question_number)).fetchone()
            if existing is not None:
                if existing["text"] != text:
                    raise SubmissionConflict("The original final answer cannot be replaced")
                return dict(existing)
            first = db.execute("""SELECT 1 FROM progress_first_answers
                WHERE attempt_id = ? AND question_number = ?""", (attempt_id, question_number)).fetchone()
            if (attempt["status"] != "active" or attempt["question_number"] != question_number
                    or attempt["phase"] != "search" or first is None):
                raise SubmissionConflict("The final answer requires the current question's search phase and first answer")
            answer = {"text": text, "submitted_at": _now()}
            db.execute("""INSERT INTO progress_final_answers
                (attempt_id, question_number, text, submitted_at) VALUES (?, ?, ?, ?)""",
                       (attempt_id, question_number, text, answer["submitted_at"]))
            if browser_scope:
                db.execute("""INSERT INTO progress_reviews (attempt_id, question_number, browser_scope)
                    VALUES (?, ?, ?)""", (attempt_id, question_number, browser_scope))
            self._queue_answer_event(db, attempt, question_number, answer, "TaskEnded")
            if question_number < 3:
                db.execute("""UPDATE progress_attempts SET question_number = ?, phase = 'first-answer'
                    WHERE attempt_id = ?""", (question_number + 1, attempt_id))
            else:
                db.execute("""UPDATE progress_attempts SET status = 'completed', phase = 'recap'
                    WHERE attempt_id = ?""", (attempt_id,))
        return answer


def init_progress(app):
    """Configure storage explicitly; the new participant flow will call this."""
    directory = app.config.get("RESEARCH_STATE_DIR") or os.getenv("RESEARCH_STATE_DIR", "research_state")
    app.config.setdefault("SOL_PROGRESS_DB_PATH", os.getenv("SOL_PROGRESS_DB_PATH") or
                          str(Path(directory) / "study-progress.sqlite3"))
    store = ProgressStore(app.config["SOL_PROGRESS_DB_PATH"])
    app.extensions["study_progress"] = store
    return store
