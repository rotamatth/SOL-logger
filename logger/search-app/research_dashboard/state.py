"""Persistent research settings and opaque login sessions, separate from students."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import re
import secrets
import sqlite3
import time

from .student_config import validate_topics
from .study_config import scheduled_assignment, validate_question_set
from .question_versions import validate_question_drafts
from . import participants as identities
from .participants import GRADES, roster, valid_school_year  # noqa: F401 - roster is re-exported for callers

MAX_STUDY_SESSIONS = 100
DEFAULT_STUDY_ID = "sol-longitudinal"
SETTING_FIELDS = ("schema_version", "ranges", "sessions", "historical_grades", "current_school_year")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def identity(value):
    return sha256(str(value).encode("utf-8")).hexdigest()


def default_settings():
    return {
        "schema_version": 1,
        "historical_grades": [],
        "current_school_year": "",
        "ranges": [
            {"grade": "4", "start": 1, "end": 20, "prefix": "", "width": 0},
            {"grade": "5", "start": 21, "end": 40, "prefix": "", "width": 0},
        ],
        "sessions": [
            {"id": f"grade-{grade}-session-{number}", "grade": grade,
             "number": number, "date": "", "name": ""}
            for grade in ("4", "5") for number in (1, 2, 3)
        ],
    }


def participant_matches(rule, uid):
    if not isinstance(uid, str) or not uid.startswith(rule["prefix"]):
        return False
    number = uid[len(rule["prefix"]):]
    if not re.fullmatch(r"[0-9]{1,8}", number):
        return False
    value = int(number)
    return rule["start"] <= value <= rule["end"] and rule["prefix"] + str(value).zfill(rule["width"]) == uid


def historical_grade(settings, collection, uid, study_date):
    if not study_date:
        return None
    return next((rule for rule in settings.get("historical_grades", [])
                 if rule["collection"] == collection and rule["date_from"] <= study_date <= rule["date_to"]
                 and participant_matches(rule, uid)), None)


def normalize_session_name(value):
    if not isinstance(value, str):
        raise ValueError("invalid_session_name")
    name = value.strip()
    if len(name) > 80 or any(ord(character) < 32 or ord(character) == 127 for character in name):
        raise ValueError("invalid_session_name")
    return name


ID_PREFIX = re.compile(r"[A-Za-z0-9_-]{0,24}")
PARTICIPANT_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")
HEX_ID = re.compile(r"[0-9a-f]{24}")


def _valid_id_range(rule):
    """start/end/width/prefix of a generated ID range (at most 1,000 IDs)."""
    return (type(rule.get("start")) is int and type(rule.get("end")) is int
            and 0 <= rule["start"] <= rule["end"] <= 999999 and rule["end"] - rule["start"] <= 999
            and type(rule.get("width")) is int and 0 <= rule["width"] <= 8
            and isinstance(rule.get("prefix"), str) and ID_PREFIX.fullmatch(rule["prefix"]) is not None)


def _range_ids(rule):
    return {rule["prefix"] + str(n).zfill(rule["width"]) for n in range(rule["start"], rule["end"] + 1)}


def _valid_iso_date(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _validate_ranges(rules):
    if (not isinstance(rules, list) or not 2 <= len(rules) <= 3
            or any(not isinstance(r, dict) for r in rules)
            or len({r.get("grade") for r in rules}) != len(rules)
            or not {"4", "5"} <= {r.get("grade") for r in rules} <= set(GRADES)):
        raise ValueError("invalid_ranges")
    seen = set()
    for rule in rules:
        if not _valid_id_range(rule):
            raise ValueError("invalid_ranges")
        ids = _range_ids(rule)
        if seen & ids:
            raise ValueError("overlapping_ranges")
        seen |= ids
        assignment = rule.get("assignment")
        if assignment is not None:
            if (not isinstance(assignment, dict) or assignment.get("mode") not in ("missing", "all")
                    or not isinstance(assignment.get("id"), str) or not HEX_ID.fullmatch(assignment["id"])):
                raise ValueError("invalid_task_assignment")
            validate_topics(assignment.get("topics"))


def _validate_session_questions(study_session):
    if "question_set" in study_session:
        validate_question_set(study_session["question_set"])
    if "participant_questions" in study_session:
        overrides = study_session["participant_questions"]
        if (not isinstance(overrides, dict) or len(overrides) > 3000
                or any(not isinstance(uid, str) or not PARTICIPANT_ID.fullmatch(uid) for uid in overrides)):
            raise ValueError("invalid_participant_questions")
        for question_set in overrides.values():
            validate_question_set(question_set)
    validate_question_drafts(study_session)


def _validate_sessions(sessions):
    if not isinstance(sessions, list) or not 2 <= len(sessions) <= len(GRADES) * MAX_STUDY_SESSIONS:
        raise ValueError("invalid_sessions")
    dates, numbers = set(), {grade: set() for grade in GRADES}
    for s in sessions:
        if (not isinstance(s, dict) or s.get("grade") not in numbers
                or type(s.get("number")) is not int or not 1 <= s["number"] <= MAX_STUDY_SESSIONS
                or s["number"] in numbers[s["grade"]]):
            raise ValueError("invalid_sessions")
        numbers[s["grade"]].add(s["number"])
        if s.get("id") != f"grade-{s['grade']}-session-{s['number']}":
            raise ValueError("invalid_sessions")
        if s.get("school_year") and not valid_school_year(s["school_year"]):
            raise ValueError("invalid_school_year")
        if type(s.get("removed", False)) is not bool:
            raise ValueError("invalid_sessions")
        if normalize_session_name(s.get("name", "")) != s.get("name", ""):
            raise ValueError("invalid_session_name")
        _validate_session_questions(s)
        if not isinstance(s.get("date"), str):
            raise ValueError("invalid_date")
        if not s["date"]:
            continue
        if not _valid_iso_date(s["date"]):
            raise ValueError("invalid_date")
        if s.get("school_year") and not identities.year_contains(s["school_year"], s["date"]):
            raise ValueError("session_year_mismatch")
        if not s.get("removed"):
            # Two active sessions of one grade cannot share a date.
            if (s["grade"], s["date"]) in dates:
                raise ValueError("overlapping_dates")
            dates.add((s["grade"], s["date"]))
    # Session numbers per grade are 1..n without gaps; 4th and 5th grade always have sessions.
    if any(values != set(range(1, len(values) + 1)) for values in numbers.values()) or not numbers["4"] or not numbers["5"]:
        raise ValueError("invalid_sessions")


def _validate_historical_grades(history):
    if not isinstance(history, list) or len(history) > 100:
        raise ValueError("invalid_historical_grade")
    identifiers, checked = set(), []
    for rule in history:
        if (not isinstance(rule, dict) or rule.get("grade") not in GRADES
                or rule.get("collection") not in ("v2", "legacy")
                or not isinstance(rule.get("id"), str) or not HEX_ID.fullmatch(rule["id"])
                or rule["id"] in identifiers or not valid_school_year(rule.get("school_year"))
                or not _valid_id_range(rule)):
            raise ValueError("invalid_historical_grade")
        identifiers.add(rule["id"])
        if (not all(_valid_iso_date(rule.get(key)) for key in ("date_from", "date_to"))
                or rule["date_from"] > rule["date_to"]):
            raise ValueError("invalid_date")
        ids = _range_ids(rule)
        if any(old["collection"] == rule["collection"] and old["date_from"] <= rule["date_to"]
               and rule["date_from"] <= old["date_to"] and ids & old_ids for old, old_ids in checked):
            raise ValueError("overlapping_historical_grades")
        checked.append((rule, ids))


def validate_settings(value):
    """Validate a complete settings document; fills in optional defaults. Raises ValueError(code)."""
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("invalid_settings")
    _validate_ranges(value.get("ranges", []))
    _validate_sessions(value.get("sessions", []))
    current_year = value.setdefault("current_school_year", "")
    if current_year and not valid_school_year(current_year):
        raise ValueError("invalid_school_year")
    _validate_historical_grades(value.setdefault("historical_grades", []))
    return value


def make_study_session(settings, grade, study_date, name="", school_year=None):
    """Build a session consistently for administration and guided preparation."""
    if grade not in GRADES:
        raise ValueError("invalid_sessions")
    number = max((s["number"] for s in settings["sessions"] if s["grade"] == grade), default=0) + 1
    if number > MAX_STUDY_SESSIONS:
        raise ValueError("session_limit")
    if not study_date:
        raise ValueError("invalid_date")
    study_session = {"id": f"grade-{grade}-session-{number}", "grade": grade,
                     "number": number, "date": study_date, "name": normalize_session_name(name),
                     "school_year": settings.get("current_school_year", "") if school_year is None else school_year}
    if not valid_school_year(study_session["school_year"]):
        raise ValueError("school_year_required")
    return study_session


class State:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "research.sqlite3"
        with self.connect() as db:
            db.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS settings (
                    revision INTEGER PRIMARY KEY AUTOINCREMENT, updated_at TEXT NOT NULL,
                    body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS auth (
                    token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, created REAL NOT NULL,
                    seen REAL NOT NULL, credential TEXT NOT NULL, authenticated INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (ip TEXT NOT NULL, at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS attempts_time ON attempts(at);
                CREATE TABLE IF NOT EXISTS trashed_runs (
                    run_id TEXT PRIMARY KEY, trashed_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS study_attempts (
                    technical_session_id TEXT PRIMARY KEY, study_session_id TEXT NOT NULL,
                    participant_id TEXT NOT NULL, metadata TEXT NOT NULL,
                    published INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS study_attempt_session ON study_attempts(study_session_id);
            """)
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > identities.SCHEMA_VERSION:
                raise RuntimeError("Research database requires a newer application version")
            if not db.execute("SELECT 1 FROM settings LIMIT 1").fetchone():
                db.execute("INSERT INTO settings(updated_at, body) VALUES (?, ?)",
                           (utc_now(), json.dumps(default_settings())))
            if version < 2:
                latest = json.loads(db.execute("SELECT body FROM settings ORDER BY revision DESC LIMIT 1").fetchone()[0])
                identities.migrate(db, latest)
                for item in latest["sessions"]:
                    item["school_year"] = self._initial_session_year(item, latest)
                db.execute("INSERT INTO settings(updated_at, body) VALUES (?,?)", (utc_now(), json.dumps(latest)))
            db.execute("PRAGMA user_version=2")
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _initial_session_year(item, settings):
        year = settings.get("current_school_year", "")
        return year if year and (not item.get("date") or identities.year_contains(year, item["date"])) else ""

    def settings(self):
        with self.connect() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM settings ORDER BY revision DESC LIMIT 1").fetchone()
            value = validate_settings(json.loads(row["body"]))
            registry = identities.projection(db)
        return {**value, **registry, "revision": row["revision"], "updated_at": row["updated_at"]}

    def settings_body(self, revision):
        """The stored settings document of an earlier revision, or None. Revisions are never deleted."""
        with self.connect() as db:
            row = db.execute("SELECT body FROM settings WHERE revision=?", (revision,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_settings(self, value, expected_revision):
        value = json.loads(json.dumps({key: value[key] for key in SETTING_FIELDS}))
        for item in value["sessions"]:
            item.setdefault("school_year", self._initial_session_year(item, value))
        value = validate_settings(value)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            revision = db.execute("SELECT MAX(revision) FROM settings").fetchone()[0]
            if revision != expected_revision:
                raise ValueError("settings_changed")
            previous = json.loads(db.execute("SELECT body FROM settings WHERE revision=?", (revision,)).fetchone()[0])
            if previous.get("current_school_year") and not value.get("current_school_year"):
                raise ValueError("school_year_required")
            removed_before = {item["id"] for item in previous["sessions"] if item.get("removed")}
            previous_sessions = {item["id"]: item for item in previous["sessions"]}
            for item in value["sessions"]:
                prior = previous_sessions.get(item["id"], {})
                if prior.get("school_year") != item.get("school_year"):
                    if db.execute("SELECT 1 FROM study_attempts WHERE study_session_id=? LIMIT 1", (item["id"],)).fetchone():
                        raise ValueError("session_year_has_records")
                if item.get("removed") and item["id"] not in removed_before:
                    if db.execute("SELECT 1 FROM study_attempts WHERE study_session_id=? LIMIT 1", (item["id"],)).fetchone():
                        raise ValueError("session_has_records")
            saved = db.execute("INSERT INTO settings(updated_at, body) VALUES (?, ?)",
                               (utc_now(), json.dumps(value))).lastrowid
            identities.sync_range_edits(db, previous, value, saved)

    def change_participants(self, operation, arguments, expected_revision, *, dry_run=False):
        """The public write boundary for enrollment and reviewed identity links."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision,body FROM settings ORDER BY revision DESC LIMIT 1").fetchone()
            if row["revision"] != expected_revision:
                raise ValueError("settings_changed")
            settings = json.loads(row["body"])
            projected = {**settings, **identities.projection(db)}
            if operation == "promote":
                settings["current_school_year"] = arguments["target_year"]
            revision = db.execute("INSERT INTO settings(updated_at,body) VALUES (?,?)",
                                  (utc_now(), json.dumps(settings))).lastrowid
            if operation == "add":
                details = identities.add_participants(db, **arguments)
            elif operation == "enroll":
                details = identities.enroll_participants(db, **arguments)
            elif operation == "update":
                details = identities.update_participant(db, **arguments)
            elif operation == "promote":
                details = identities.promote(db, projected, **arguments)
            elif operation == "link":
                details = identities.link_legacy(db, **arguments, revision=revision)
            elif operation == "unlink":
                link = db.execute("SELECT * FROM participant_links WHERE id=? AND revoked_at IS NULL",
                                  (arguments["link_id"],)).fetchone()
                if not link:
                    raise ValueError("invalid_identity_link")
                details = dict(link)
                db.execute("UPDATE participant_links SET revoked_at=? WHERE id=?", (utc_now(), link["id"]))
            else:
                raise ValueError("invalid_enrollment")
            identities.audit(db, revision, operation, details)
            if dry_run:
                db.rollback()
        return details

    def participant_changes(self, limit=20):
        """Recent audit entries with the affected IDs and their before/after values."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("invalid_audit_limit")
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT revision,at,operation,details FROM participant_audit ORDER BY id DESC LIMIT ?", (limit,))]
        for row in rows:
            try:
                details = json.loads(row.pop("details") or "{}")
            except (TypeError, ValueError):
                details = {}
            row["school_year"] = details.get("school_year") if isinstance(details, dict) else None
            row["changes"] = identities.audit_rows(row["operation"], details)
        return rows

    def admit_attempt(self, metadata):
        """Serialize eligibility and immutable attempt creation with settings edits."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision,body FROM settings ORDER BY revision DESC LIMIT 1").fetchone()
            if row["revision"] != metadata["settings_revision_at_collection"]:
                raise ValueError("settings_changed")
            configuration = {**json.loads(row["body"]), **identities.projection(db)}
            selected = scheduled_assignment(configuration, metadata["participant_id"])
            if not selected or selected["session"]["id"] != metadata["study_session_at_collection"]:
                raise ValueError("session_unavailable")
            context = selected.get("enrollment")
            if not context or any(metadata.get(key) != context[field] for key, field in (
                    ("participant_key", "participant_key"), ("enrollment_id", "enrollment_id"),
                    ("school_year_at_collection", "school_year"), ("grade_at_collection", "grade"))):
                raise ValueError("invalid_enrollment")
            db.execute("""INSERT INTO study_attempts
                       (technical_session_id,study_session_id,participant_id,metadata,published)
                       VALUES (?,?,?,?,0)""",
                       (metadata["technical_session_id"], metadata["study_session_at_collection"],
                        metadata["participant_id"], json.dumps(metadata, ensure_ascii=False)))

    def attempt_metadata(self, technical_session_id):
        with self.connect() as db:
            row = db.execute("SELECT metadata FROM study_attempts WHERE technical_session_id=?", (technical_session_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def progress_run_for_date(self, participant_id, study_date):
        """Recover a progress-enabled admission from its frozen collection date."""
        with self.connect() as db:
            rows = db.execute("SELECT metadata FROM study_attempts WHERE participant_id=? ORDER BY rowid",
                              (participant_id,)).fetchall()
        for row in rows:
            metadata = json.loads(row[0])
            if (metadata.get("progress_enabled") is True
                    and metadata.get("study_id_at_collection") == DEFAULT_STUDY_ID
                    and metadata.get("study_session_snapshot", {}).get("date") == study_date):
                return metadata
        return None

    def progress_ids_for_date(self, study_date):
        """Already admitted children remain available for same-day resume."""
        with self.connect() as db:
            rows = db.execute("SELECT participant_id,metadata FROM study_attempts").fetchall()
        return {row["participant_id"] for row in rows
                if (metadata := json.loads(row["metadata"])).get("progress_enabled") is True
                and metadata.get("study_id_at_collection") == DEFAULT_STUDY_ID
                and metadata.get("study_session_snapshot", {}).get("date") == study_date}

    def pending_attempts(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT metadata FROM study_attempts WHERE published=0")]

    def mark_attempt_published(self, technical_session_id):
        with self.connect() as db:
            db.execute("UPDATE study_attempts SET published=1 WHERE technical_session_id=?", (technical_session_id,))

    def add_study_session(self, grade, study_date, expected_revision, name="", school_year=None):
        current = self.settings()
        if current["revision"] != expected_revision:
            raise ValueError("settings_changed")
        study_session = make_study_session(current, grade, study_date, name, school_year)
        current["sessions"].append(study_session)
        self.save_settings({key: current[key] for key in SETTING_FIELDS}, expected_revision)
        return study_session

    def new_session(self, credential, authenticated=False):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = time.time()
        with self.connect() as db:
            db.execute("DELETE FROM auth WHERE created < ? OR seen < ?", (now - 28800, now - 1800))
            db.execute("INSERT INTO auth VALUES (?, ?, ?, ?, ?, ?)",
                       (identity(token), csrf, now, now, credential, int(authenticated)))
        return token, self.session(token, credential)

    def session(self, token, credential):
        if not token or len(token) > 100:
            return None
        now = time.time()
        with self.connect() as db:
            row = db.execute("SELECT * FROM auth WHERE token_hash = ?", (identity(token),)).fetchone()
            if not row:
                return None
            if (row["credential"] != credential or now - row["created"] >= 28800
                    or now - row["seen"] >= 1800):
                db.execute("DELETE FROM auth WHERE token_hash = ?", (identity(token),))
                return None
            db.execute("UPDATE auth SET seen = ? WHERE token_hash = ?", (now, identity(token)))
        return dict(row)

    def revoke(self, token):
        with self.connect() as db:
            db.execute("DELETE FROM auth WHERE token_hash = ?", (identity(token),))

    def trashed_runs(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT run_id, trashed_at FROM trashed_runs ORDER BY trashed_at DESC, run_id")]

    def trashed_run_ids(self):
        with self.connect() as db:
            return {row[0] for row in db.execute("SELECT run_id FROM trashed_runs")}

    def trash_run(self, run_id):
        with self.connect() as db:
            return db.execute("INSERT OR IGNORE INTO trashed_runs(run_id, trashed_at) VALUES (?, ?)",
                              (run_id, utc_now())).rowcount == 1

    def restore_run(self, run_id):
        with self.connect() as db:
            return db.execute("DELETE FROM trashed_runs WHERE run_id = ?", (run_id,)).rowcount == 1

    def reserve_login_attempt(self, ip):
        """Atomic across Gunicorn workers; never trust client-supplied proxy headers."""
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM attempts WHERE at < ?", (now - 900,))
            local = db.execute("SELECT COUNT(*) FROM attempts WHERE ip = ?", (ip,)).fetchone()[0]
            total = db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            if local >= 5 or total >= 100:
                return False
            attempt = db.execute("INSERT INTO attempts VALUES (?, ?)", (ip, now)).lastrowid
        return attempt

    def successful_attempt(self, attempt):
        with self.connect() as db:
            db.execute("DELETE FROM attempts WHERE rowid = ?", (attempt,))
