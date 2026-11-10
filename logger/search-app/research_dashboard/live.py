"""Progress of a running session, read from started attempts and their original logs.

Attempts come from authoritative state and progress from each attempt's _FULL.log. The reporting
index is not used here: it rescans every file inside a write transaction, too heavy to poll.
Nothing in this module writes. Missing data only means nothing has been saved yet, never that a
child has stopped.
"""
from datetime import datetime
import json
import os
from zoneinfo import ZoneInfo

from .collection import safe_participant
from .index import MAX_LINE, safe_open
from .participants import participant_sort_key
from .state import identity
from .study_config import session_readiness
from .task_stats import add_event, new_stats, question_rows, summarize

ZURICH = ZoneInfo("Europe/Zurich")
TASKS = ("1", "2", "3")
CACHE_LIMIT = 2000


def _read_log(root, name, cache):
    """What one log says per task, read again only when the file changed. None if nothing is saved yet."""
    try:
        with safe_open(root, name) as source:
            status = os.fstat(source.fileno())
            signature = (status.st_ino, status.st_size, status.st_mtime_ns)
            cached = cache.get(name)
            if cached and cached["signature"] == signature:
                return cached
            tasks = {}
            for line in iter(lambda: source.readline(MAX_LINE + 1), b""):
                try:
                    if not line.endswith(b"\n"):  # Still being written, or too long to be an event.
                        continue
                    event = json.loads(line)
                except (ValueError, UnicodeError, RecursionError):
                    continue
                number = event.get("task_number") if isinstance(event, dict) else None
                if not isinstance(number, (int, str)) or isinstance(number, bool):
                    continue
                task = tasks.setdefault(str(number), {"stats": new_stats(), "answered": False})
                add_event(task["stats"], event)
                if event.get("type") == "TaskEnded" and isinstance(event.get("answer"), str):
                    task["answered"] = True
    except OSError:
        return None
    if len(cache) >= CACHE_LIMIT:
        cache.clear()
    entry = {"signature": signature, "tasks": tasks, "saved_at": status.st_mtime}
    cache[name] = entry
    return entry


def _clock(value):
    """HH:MM of a logged local timestamp; None if it is not one."""
    return value[11:16] if isinstance(value, str) and len(value) >= 16 and value[10] == "T" else None


def _run_progress(root, metadata, cache):
    log = _read_log(root, f"{safe_participant(metadata['participant_id'])}_{metadata['log_id']}_FULL.log", cache)
    logged = log["tasks"] if log else {}
    snapshots = {str(item.get("presented_number")): item for item in metadata.get("tasks", []) if isinstance(item, dict)}
    tasks, figures = [], {}
    for number in TASKS:
        snapshot, task = snapshots.get(number, {}), logged.get(number)
        question = snapshot.get("question") or snapshot.get("topic_title")
        status = "not_reached" if not task else "finished" if task["answered"] else "in_progress"
        entry = {"number": number, "question": question, "status": status, "since": None, "figures": None}
        if status == "finished":
            entry["figures"] = summarize(task["stats"])
            figures[number] = {**entry["figures"], "finished": True, "question": question,
                               "topic": snapshot.get("topic_id")}
        elif status == "in_progress":
            entry["since"] = _clock(task["stats"]["started_at"])
        tasks.append(entry)
    finished = sum(task["status"] == "finished" for task in tasks)
    current = next((task["number"] for task in tasks if task["status"] == "in_progress"),
                   None if finished == len(TASKS) else next(task["number"] for task in tasks if task["status"] != "finished"))
    return {"tasks": tasks, "finished": finished, "current": current,
            "searches": sum(task["stats"]["searches"] for task in logged.values()),
            "saved_at": log["saved_at"] if log else None,
            "as_run": {"id": metadata["technical_session_id"], "participant_id": metadata["participant_id"],
                       "study_participant_id": metadata["participant_id"], "started_at": metadata.get("started_at"),
                       "date": metadata.get("experiment_date"), "assignment_source": metadata.get("assignment_source"),
                       "task_stats": figures}}


def session_progress(state, settings, root, study_session, cache):
    """One row per child who is expected or has started, with class totals and question figures."""
    trashed = state.trashed_run_ids()
    runs = {}
    for metadata in state.session_attempts(study_session["id"]):
        stem = f"{safe_participant(metadata['participant_id'])}_{metadata['log_id']}"
        if identity("v2\0" + stem) not in trashed:
            runs.setdefault(metadata["participant_id"], []).append(metadata)
    expected = {person["id"] for person in session_readiness(settings, study_session)["participants"]}
    children, class_runs = [], []
    for uid in sorted(expected | set(runs), key=participant_sort_key):
        child_runs = sorted(runs.get(uid, []), key=lambda item: item.get("started_at") or "")
        child = {"id": uid, "token": identity(uid), "status": "not_started", "runs": len(child_runs), "finished": 0,
                 "current": None, "searches": 0, "saved": None, "tasks": []}
        if child_runs:
            progress = [_run_progress(root, metadata, cache) for metadata in child_runs]
            class_runs.extend(item["as_run"] for item in progress)
            latest = progress[-1]
            child.update(status="completed" if latest["finished"] == len(TASKS) else "in_progress",
                         finished=latest["finished"], current=latest["current"], searches=latest["searches"],
                         tasks=latest["tasks"],
                         saved=(datetime.fromtimestamp(latest["saved_at"], ZURICH).strftime("%H:%M:%S")
                                if latest["saved_at"] else None))
        children.append(child)
    totals = {status: sum(child["status"] == status for child in children)
              for status in ("not_started", "in_progress", "completed")}
    return {"children": children, "totals": {**totals, "expected": len(children)},
            "questions": question_rows(class_runs, len(children))}
