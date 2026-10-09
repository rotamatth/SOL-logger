"""Rebuildable file index. Original logs are read-only; registry entries are not runs."""
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import re
import sqlite3
import stat
import time

from .state import DEFAULT_STUDY_ID, GRADES, historical_grade, identity, roster, valid_school_year

MAX_LINE = 1024 * 1024
MODULUS = 2 ** 256
SUFFIX = re.compile(r"^(.*)_(FULL|task([0-9]+)_topic([^/]+)|INCOMPLETE)\.log$")
LOG_ID_SUFFIX = re.compile(r"_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_[0-9a-f]{8})$")


def file_identity(name):
    if name.endswith(".run.json"):
        return name[:-9], "metadata", None
    match = SUFFIX.fullmatch(name)
    if match:
        return match[1], "full" if match[2] == "FULL" else "task" if match[3] else "recovery", match[3]
    return name, "other", None


def date_of(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo:
            parsed = parsed.astimezone(ZoneInfo("Europe/Zurich"))
        return parsed.date().isoformat()
    except (ValueError, OverflowError):
        return None


def safe_open(root, name):
    """Only direct regular files in a server-configured directory; never follow symlinks."""
    if name != Path(name).name or name in (".", ".."):
        raise OSError("invalid_source_name")
    fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise OSError("not_regular_file")
    return os.fdopen(fd, "rb")


class Index:
    def __init__(self, directory, roots, refresh_seconds=30):
        self.path = Path(directory) / "index.sqlite3"
        self.roots = {name: Path(path).resolve() for name, path in roots.items()}
        if len(set(self.roots.values())) != len(self.roots):
            raise ValueError("v2 and legacy must use different directories")
        self.refresh_seconds = refresh_seconds
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY, collection TEXT NOT NULL, name TEXT NOT NULL,
                    signature TEXT NOT NULL, info TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    file_id TEXT NOT NULL, line INTEGER NOT NULL, offset INTEGER NOT NULL,
                    length INTEGER NOT NULL, task TEXT, valid INTEGER NOT NULL,
                    PRIMARY KEY(file_id, line));
                CREATE INDEX IF NOT EXISTS task_events ON events(file_id, task, line);
                CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, summary TEXT NOT NULL, detail TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scan (id INTEGER PRIMARY KEY, at REAL NOT NULL, problems TEXT NOT NULL);
            """)
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=60)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def refresh(self, force=False):
        with self.connect() as db:
            last = db.execute("SELECT at FROM scan WHERE id = 1").fetchone()
            if not force and last and time.time() - last[0] < self.refresh_seconds:
                return
            db.execute("BEGIN IMMEDIATE")
            last = db.execute("SELECT at FROM scan WHERE id = 1").fetchone()
            if not force and last and time.time() - last[0] < self.refresh_seconds:
                return
            seen, problems = set(), []
            for collection, root in self.roots.items():
                try:
                    entries = sorted(root.iterdir())
                except OSError:
                    problems.append({"collection": collection, "code": "directory_unavailable"})
                    continue
                for path in entries:
                    if not (path.name.endswith(".log") or path.name.endswith(".run.json")):
                        continue
                    key = identity(collection + "\0" + path.name)
                    seen.add(key)
                    try:
                        s = path.lstat()
                        signature = f"{s.st_ino}:{s.st_size}:{s.st_mtime_ns}:{s.st_mode}"
                    except OSError:
                        signature = "unreadable"
                    previous = db.execute("SELECT signature FROM files WHERE id = ?", (key,)).fetchone()
                    if previous and previous[0] == signature:
                        continue
                    db.execute("DELETE FROM events WHERE file_id = ?", (key,))
                    info = self._parse(db, collection, path.name, key)
                    db.execute("INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?)",
                               (key, collection, path.name, signature, json.dumps(info)))
            for row in db.execute("SELECT id FROM files").fetchall():
                if row[0] not in seen:
                    db.execute("DELETE FROM files WHERE id = ?", (row[0],))
                    db.execute("DELETE FROM events WHERE file_id = ?", (row[0],))
            groups = defaultdict(list)
            for row in db.execute("SELECT collection, info FROM files"):
                info = json.loads(row["info"])
                groups[(row["collection"], info["stem"])].append(info)
            db.execute("DELETE FROM runs")
            for (collection, stem), files in groups.items():
                summary, detail = self._run(collection, stem, files)
                db.execute("INSERT INTO runs VALUES (?, ?, ?)",
                           (summary["id"], json.dumps(summary), json.dumps(detail)))
            db.execute("INSERT OR REPLACE INTO scan VALUES (1, ?, ?)", (time.time(), json.dumps(problems)))

    def _parse(self, db, collection, name, key):
        stem, kind, position = file_identity(name)
        info = {"id": key, "name": name, "stem": stem, "kind": kind, "position": position,
                "collection": collection, "issues": [], "uids": [], "session_ids": [],
                "dates": [], "tasks": {}, "event_count": 0, "signature_sum": 0,
                "finished": False, "size": 0, "mtime": 0, "metadata": {}}
        try:
            with safe_open(self.roots[collection], name) as f:
                s = os.fstat(f.fileno())
                info.update(size=s.st_size, mtime=s.st_mtime, inode=s.st_ino, mtime_ns=s.st_mtime_ns)
                if kind == "metadata":
                    body = f.read(MAX_LINE + 1)
                    if len(body) > MAX_LINE:
                        raise ValueError("metadata_too_large")
                    info["sha256"] = sha256(body).hexdigest()
                    meta = json.loads(body)
                    if (not isinstance(meta, dict) or meta.get("schema_version") != 1
                            or not isinstance(meta.get("tasks"), list)
                            or any(not isinstance(t, dict) for t in meta["tasks"])):
                        raise ValueError("invalid_metadata")
                    info["metadata"] = meta
                    return info
                digest = sha256()
                uids, sessions, dates = set(), set(), set()
                line_number = 0
                while f.tell() < s.st_size:
                    offset = f.tell()
                    line = f.readline(min(MAX_LINE + 1, s.st_size - offset))
                    if not line:
                        break
                    line_number += 1
                    digest.update(line)
                    too_large = len(line) > MAX_LINE
                    if too_large:
                        while not line.endswith(b"\n") and f.tell() < s.st_size:
                            line = f.readline(min(MAX_LINE + 1, s.st_size - f.tell()))
                            if not line:
                                break
                            digest.update(line)
                    length = f.tell() - offset
                    task, valid = None, False
                    try:
                        if too_large:
                            raise ValueError("line_too_large")
                        if not line.endswith(b"\n"):
                            raise ValueError("partial_line")
                        event = json.loads(line)
                        if not isinstance(event, dict):
                            raise ValueError("not_an_object")
                        valid = True
                        info["event_count"] += 1
                        info["signature_sum"] = (info["signature_sum"] + int.from_bytes(
                            sha256(json.dumps(event, sort_keys=True, ensure_ascii=True).encode()).digest())) % MODULUS
                        uid = event.get("uid")
                        if uid is not None:
                            if not isinstance(uid, (str, int)) or isinstance(uid, bool):
                                raise ValueError("invalid_participant_id")
                            uids.add(str(uid))
                        sid = event.get("sessionID")
                        if isinstance(sid, str):
                            sessions.add(sid)
                        event_date = date_of(event.get("timestamp"))
                        if event_date:
                            dates.add(event_date)
                        task_value = event.get("task_number")
                        task = str(task_value) if isinstance(task_value, (str, int)) else position
                        if task is not None:
                            t = info["tasks"].setdefault(task, {"topics": [], "questions": [], "answers": [], "events": 0})
                            t["events"] += 1
                            topic = event.get("actual_topic_number")
                            if isinstance(topic, (str, int)) and str(topic) not in t["topics"]:
                                t["topics"].append(str(topic))
                            question = event.get("task_question")
                            if event.get("type") == "TaskStarted" and question is None:
                                question = event.get("question")
                            if isinstance(question, str) and question not in t["questions"]:
                                t["questions"].append(question)
                            if event.get("type") == "TaskEnded":
                                t["answers"].append({"present": "answer" in event,
                                                     "value": event.get("answer"),
                                                     "timestamp": event.get("timestamp"),
                                                     "source_file": key, "line": line_number})
                        if event.get("type") == "experimentFinished":
                            info["finished"] = True
                    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
                        valid = False
                        if len(info["issues"]) < 50:
                            code = str(exc) if str(exc) in {"line_too_large", "partial_line", "not_an_object", "invalid_participant_id"} else "malformed_json"
                            info["issues"].append(f"{code}:line={line_number}")
                    db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
                               (key, line_number, offset, length, task, int(valid)))
                info.update(uids=sorted(uids), session_ids=sorted(sessions), dates=sorted(dates), sha256=digest.hexdigest())
                end = os.fstat(f.fileno())
                if (end.st_size, end.st_mtime_ns) != (s.st_size, s.st_mtime_ns):
                    info["issues"].append("changed_during_indexing")
        except (OSError, ValueError, UnicodeError, TypeError, RecursionError):
            info["issues"].append("unreadable_or_invalid_file")
        return info

    def _run(self, collection, stem, files):
        meta = next((f["metadata"] for f in files if f["kind"] == "metadata"), {})
        uids = {u for f in files for u in f["uids"]}
        if isinstance(meta.get("participant_id"), str):
            uids.add(meta["participant_id"])
        sessions = {s for f in files for s in f["session_ids"]}
        if isinstance(meta.get("technical_session_id"), str):
            sessions.add(meta["technical_session_id"])
        issues = [f"{f['name']}: {issue}" for f in files for issue in f["issues"]]
        if len(uids) > 1:
            issues.append("conflicting_participant_ids")
        if len(sessions) > 1:
            issues.append("conflicting_technical_sessions")
        uid = next(iter(uids)) if len(uids) == 1 and len(sessions) <= 1 else None
        full = [f for f in files if f["kind"] == "full"]
        task_files = [f for f in files if f["kind"] == "task"]
        canonical = full or sorted((f for f in files if f["kind"] != "metadata"), key=lambda f: f["name"])
        if not full and any(f["kind"] != "metadata" for f in files):
            issues.append("full_log_missing_using_available_files")
        if full and task_files:
            if (sum(f["event_count"] for f in full), sum(f["signature_sum"] for f in full) % MODULUS) != (
                    sum(f["event_count"] for f in task_files), sum(f["signature_sum"] for f in task_files) % MODULUS):
                issues.append("full_and_task_copies_differ")
        tasks = {str(n): {"number": str(n), "topics": [], "questions": [], "answers": [], "events": 0} for n in (1, 2, 3)}
        for f in canonical:
            for number, t in f["tasks"].items():
                if number not in tasks:
                    issues.append(f"unrecognized_task_number:{number}")
                    continue
                dest = tasks.setdefault(number, {"number": number, "topics": [], "questions": [], "answers": [], "events": 0})
                dest["events"] += t["events"]
                dest["answers"].extend(t["answers"])
                for field in ("topics", "questions"):
                    dest[field] = list(dict.fromkeys(dest[field] + t[field]))
        for recorded in meta.get("tasks", []):
            number = str(recorded.get("presented_number"))
            if number not in tasks:
                continue
            for field, key in (("topics", "topic_id"), ("questions", "question")):
                value = recorded.get(key)
                if isinstance(value, (str, int)) and str(value) not in tasks[number][field]:
                    tasks[number][field].append(str(value))
        for t in tasks.values():
            t["status"] = "completed" if any(a["present"] and isinstance(a["value"], str) for a in t["answers"]) else "incomplete" if t["events"] else "no_data"
            if len(t["topics"]) > 1 or len(t["questions"]) > 1:
                t["status"] = "unknown"
                issues.append(f"conflicting_task_metadata:task={t['number']}")
            if len(t["answers"]) > 1:
                issues.append(f"multiple_answer_records:task={t['number']}")
            if any(a["present"] and not isinstance(a["value"], str) for a in t["answers"]):
                issues.append(f"non_text_answer:task={t['number']}")
        event_count = sum(f["event_count"] for f in canonical)
        complete = all(tasks[str(n)]["status"] == "completed" for n in (1, 2, 3))
        date = date_of(meta.get("started_at")) or min((d for f in canonical for d in f["dates"]), default=None)
        filename_log_id = LOG_ID_SUFFIX.search(stem)
        summary = {"id": identity(collection + "\0" + stem), "collection": collection,
                   "participant_id": uid, "participant_token": identity(uid) if uid is not None else None,
                   "date": date, "study_id_at_collection": meta.get("study_id_at_collection"),
                   "grade_at_collection": meta.get("grade_at_collection"),
                   "school_year_at_collection": meta.get("school_year_at_collection"),
                   "app_version": meta.get("app_version"), "git_commit": meta.get("git_commit"),
                   "status": "unknown" if uid is None else "completed" if complete else "incomplete",
                   "answered_tasks": sum(t["status"] == "completed" for t in tasks.values()),
                   "finished": any(f["finished"] for f in canonical), "event_count": event_count,
                   "log_file_count": sum(f["kind"] != "metadata" and bool(f.get("sha256")) for f in files),
                   "last_saved": max((f["mtime"] for f in files), default=0), "issue_count": len(issues),
                   "technical_session_ids": sorted(sessions),
                   "log_id": meta.get("log_id") or (filename_log_id[1] if filename_log_id else None),
                   "log_id_source": "metadata" if meta.get("log_id") else "filename" if filename_log_id else None,
                   "started_at": meta.get("started_at")}
        detail = {**summary, "files": files, "tasks": tasks, "issues": issues,
                  "metadata": meta, "canonical_files": [f["id"] for f in canonical]}
        return summary, detail

    def scan_status(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM scan WHERE id = 1").fetchone()
        return {"at": row["at"], "problems": json.loads(row["problems"])} if row else {"at": 0, "problems": []}

    def summaries(self, settings):
        with self.connect() as db:
            rows = db.execute("SELECT summary FROM runs ORDER BY id").fetchall()
        return [classify(json.loads(r[0]), settings) for r in rows]

    def run(self, key, settings):
        with self.connect() as db:
            row = db.execute("SELECT detail FROM runs WHERE id = ?", (key,)).fetchone()
        return classify(json.loads(row[0]), settings) if row else None

    def event_page(self, run, task=None, page=1, page_size=100, source_id=None):
        # Combined run views use canonical files; individual viewers use exactly one original.
        files = {f["id"]: f for f in run["files"]}
        if source_id is not None:
            source = files.get(source_id)
            keys = [source_id] if source and source["kind"] != "metadata" else []
        else:
            keys = run["canonical_files"]
        if not keys:
            return [], 0
        placeholders = ",".join("?" for _ in keys)
        where = f"file_id IN ({placeholders})"
        args = list(keys)
        if task is not None:
            where += " AND task = ?"
            args.append(task)
        with self.connect() as db:
            total = db.execute(f"SELECT COUNT(*) FROM events WHERE {where}", args).fetchone()[0]
            rows = db.execute(f"SELECT * FROM events WHERE {where} ORDER BY file_id, line LIMIT ? OFFSET ?",
                              args + [page_size, (page - 1) * page_size]).fetchall()
        result = []
        for row in rows:
            f = files[row["file_id"]]
            item = {"file": f["name"], "line": row["line"], "event": None, "problem": None}
            try:
                with safe_open(self.roots[run["collection"]], f["name"]) as source:
                    s = os.fstat(source.fileno())
                    if (s.st_ino, s.st_size, s.st_mtime_ns) != (f["inode"], f["size"], f["mtime_ns"]):
                        raise ValueError("source_changed_refresh")
                    if not row["valid"] or row["length"] > MAX_LINE:
                        raise ValueError("malformed_or_partial_line")
                    source.seek(row["offset"])
                    item["event"] = json.loads(source.read(row["length"]))
            except (OSError, ValueError, KeyError, UnicodeError) as exc:
                item["problem"] = str(exc) if str(exc) in {"source_changed_refresh", "malformed_or_partial_line"} else "source_unavailable"
            result.append(item)
        return result, total


def classify(run, settings):
    grade, school_year, source, rule_id, current_grade = None, None, "unknown", None, None
    issues = list(run.get("issues", []))
    year_source = "unknown"
    recorded_study = run.get("study_id_at_collection")
    study_id = DEFAULT_STUDY_ID if recorded_study is None else recorded_study
    if not isinstance(study_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", study_id):
        study_id = None
        issues.append("invalid_recorded_study_id")
    if run["collection"] == "v2" and run.get("school_year_at_collection"):
        if valid_school_year(run["school_year_at_collection"]):
            school_year, year_source = run["school_year_at_collection"], "recorded"
        else:
            issues.append("invalid_recorded_school_year")
    if run["participant_id"] is not None:
        rule = (historical_grade(settings, run["collection"], run["participant_id"], run["date"])
                if study_id == DEFAULT_STUDY_ID else None)
        rule_id = rule["id"] if rule else None
        recorded = run.get("grade_at_collection") if run["collection"] == "v2" else None
        if run["collection"] == "v2" and study_id == DEFAULT_STUDY_ID:
            current_grade = roster(settings).get(run["participant_id"])
        if recorded in GRADES:
            grade, source = recorded, "recorded"
            if rule and rule["grade"] != recorded:
                issues.append("historical_grade_conflict")
        elif rule:
            grade, source = rule["grade"], "historical_assignment"
        elif current_grade:
            grade, source = current_grade, "current_roster"
        if rule and rule["grade"] == grade:
            if school_year and school_year != rule["school_year"]:
                issues.append("historical_school_year_conflict")
            elif not school_year:
                school_year, year_source = rule["school_year"], "historical_assignment"
    study_session = next((s for s in settings["sessions"]
                          if study_id == DEFAULT_STUDY_ID and s["grade"] == grade
                          and s["date"] and s["date"] == run["date"]), None)
    return {**run, "study_id": study_id, "grade": grade, "study_session": study_session,
            "school_year": school_year, "grade_source": source, "historical_assignment_id": rule_id,
            "school_year_source": year_source,
            "current_grade": current_grade, "issues": issues,
            "issue_count": run["issue_count"] + len(issues) - len(run.get("issues", [])),
            "settings_revision": settings["revision"]}
