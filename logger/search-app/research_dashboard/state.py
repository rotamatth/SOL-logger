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

MAX_STUDY_SESSIONS = 100
DEFAULT_STUDY_ID = "sol-longitudinal"
GRADES = ("3", "4", "5")
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


def roster(settings):
    return {
        rule["prefix"] + str(n).zfill(rule["width"]): rule["grade"]
        for rule in settings["ranges"]
        for n in range(rule["start"], rule["end"] + 1)
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


def valid_school_year(value):
    return (isinstance(value, str) and bool(re.fullmatch(r"[0-9]{4}/[0-9]{4}", value))
            and 1 <= int(value[:4]) < 9999 and int(value[5:]) == int(value[:4]) + 1)


def normalize_session_name(value):
    if not isinstance(value, str):
        raise ValueError("invalid_session_name")
    name = value.strip()
    if len(name) > 80 or any(ord(character) < 32 or ord(character) == 127 for character in name):
        raise ValueError("invalid_session_name")
    return name


def validate_settings(value):
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("invalid_settings")
    rules = value.get("ranges", [])
    if (not isinstance(rules, list) or not 2 <= len(rules) <= 3
            or any(not isinstance(r, dict) for r in rules)
            or len({r.get("grade") for r in rules}) != len(rules)
            or not {"4", "5"} <= {r.get("grade") for r in rules} <= set(GRADES)):
        raise ValueError("invalid_ranges")
    seen = set()
    for r in rules:
        if (type(r.get("start")) is not int or type(r.get("end")) is not int
                or not 0 <= r["start"] <= r["end"] <= 999999
                or r["end"] - r["start"] > 999
                or type(r.get("width")) is not int or not 0 <= r["width"] <= 8
                or not isinstance(r.get("prefix"), str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{0,24}", r["prefix"])):
            raise ValueError("invalid_ranges")
        ids = {r["prefix"] + str(n).zfill(r["width"]) for n in range(r["start"], r["end"] + 1)}
        if seen & ids:
            raise ValueError("overlapping_ranges")
        seen |= ids
        assignment = r.get("assignment")
        if assignment is not None:
            if (not isinstance(assignment, dict) or assignment.get("mode") not in ("missing", "all")
                    or not isinstance(assignment.get("id"), str)
                    or not re.fullmatch(r"[0-9a-f]{24}", assignment["id"])):
                raise ValueError("invalid_task_assignment")
            validate_topics(assignment.get("topics"))
    sessions = value.get("sessions", [])
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
        if normalize_session_name(s.get("name", "")) != s.get("name", ""):
            raise ValueError("invalid_session_name")
        if not isinstance(s.get("date"), str):
            raise ValueError("invalid_date")
        if s["date"]:
            try:
                if date.fromisoformat(s["date"]).isoformat() != s["date"]:
                    raise ValueError()
            except ValueError:
                raise ValueError("invalid_date") from None
            key = (s["grade"], s["date"])
            if key in dates:
                raise ValueError("overlapping_dates")
            dates.add(key)
    if any(values != set(range(1, len(values) + 1)) for values in numbers.values()) or not numbers["4"] or not numbers["5"]:
        raise ValueError("invalid_sessions")
    current_year = value.setdefault("current_school_year", "")
    if current_year and not valid_school_year(current_year):
        raise ValueError("invalid_school_year")
    history = value.setdefault("historical_grades", [])
    if not isinstance(history, list) or len(history) > 100:
        raise ValueError("invalid_historical_grade")
    identifiers, checked = set(), []
    for rule in history:
        if (not isinstance(rule, dict) or rule.get("grade") not in GRADES
                or rule.get("collection") not in ("v2", "legacy")
                or not isinstance(rule.get("id"), str) or not re.fullmatch(r"[0-9a-f]{24}", rule["id"])
                or rule["id"] in identifiers or not valid_school_year(rule.get("school_year"))
                or type(rule.get("start")) is not int or type(rule.get("end")) is not int
                or not 0 <= rule["start"] <= rule["end"] <= 999999 or rule["end"] - rule["start"] > 999
                or type(rule.get("width")) is not int or not 0 <= rule["width"] <= 8
                or not isinstance(rule.get("prefix"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{0,24}", rule["prefix"])):
            raise ValueError("invalid_historical_grade")
        identifiers.add(rule["id"])
        try:
            if any(not isinstance(rule.get(key), str) or date.fromisoformat(rule[key]).isoformat() != rule[key]
                   for key in ("date_from", "date_to")) or rule["date_from"] > rule["date_to"]:
                raise ValueError()
        except ValueError:
            raise ValueError("invalid_date") from None
        ids = {rule["prefix"] + str(n).zfill(rule["width"]) for n in range(rule["start"], rule["end"] + 1)}
        if any(old["collection"] == rule["collection"] and old["date_from"] <= rule["date_to"]
               and rule["date_from"] <= old["date_to"] and ids & old_ids for old, old_ids in checked):
            raise ValueError("overlapping_historical_grades")
        checked.append((rule, ids))
    return value


class State:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "research.sqlite3"
        with self.connect() as db:
            db.executescript("""
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
            """)
            if not db.execute("SELECT 1 FROM settings LIMIT 1").fetchone():
                db.execute("INSERT INTO settings(updated_at, body) VALUES (?, ?)",
                           (utc_now(), json.dumps(default_settings())))
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def settings(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM settings ORDER BY revision DESC LIMIT 1").fetchone()
        value = validate_settings(json.loads(row["body"]))
        return {**value, "revision": row["revision"], "updated_at": row["updated_at"]}

    def save_settings(self, value, expected_revision):
        value = validate_settings(value)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            revision = db.execute("SELECT MAX(revision) FROM settings").fetchone()[0]
            if revision != expected_revision:
                raise ValueError("settings_changed")
            db.execute("INSERT INTO settings(updated_at, body) VALUES (?, ?)",
                       (utc_now(), json.dumps(value)))

    def add_study_session(self, grade, study_date, expected_revision, name=""):
        current = self.settings()
        if current["revision"] != expected_revision:
            raise ValueError("settings_changed")
        if grade not in GRADES:
            raise ValueError("invalid_sessions")
        number = max((s["number"] for s in current["sessions"] if s["grade"] == grade), default=0) + 1
        if number > MAX_STUDY_SESSIONS:
            raise ValueError("session_limit")
        if not study_date:
            raise ValueError("invalid_date")
        study_session = {"id": f"grade-{grade}-session-{number}", "grade": grade,
                         "number": number, "date": study_date, "name": normalize_session_name(name)}
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
