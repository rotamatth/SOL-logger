"""Write one immutable metadata sidecar for each newly started v2 run."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import re

from .state import DEFAULT_STUDY_ID, roster


def record_run(directory, state, user_id, session_id, log_id, order, topics, settings=None,
               study_session=None, question_set=None, assignment_source=None):
    started = datetime.now(ZoneInfo("Europe/Zurich"))
    settings = settings if settings is not None else state.settings()
    grade = roster(settings).get(user_id)
    chosen_session = study_session if study_session is not None else next(
        (s for s in settings["sessions"]
         if s["grade"] == grade and s["date"] == started.date().isoformat()), None)
    session_snapshot = ({key: deepcopy(chosen_session[key])
                         for key in ("id", "name", "date", "theme", "grade", "number")
                         if key in chosen_session} if chosen_session else None)
    if session_snapshot is not None and question_set and question_set.get("theme"):
        session_snapshot.setdefault("theme", question_set["theme"])
    questions = question_set.get("questions", []) if question_set else []

    def task_snapshot(number, topic):
        task = {"presented_number": number, "topic_id": topic,
                "topic_title": topics.get(f"{topic}_short"),
                "question": topics.get(f"{topic}_full")}
        if questions:
            question = questions[int(topic) - 1]
            task.update(question_id=question["id"],
                        question_metadata=deepcopy(question.get("metadata", {})))
        return task
    metadata = {
        "schema_version": 1, "collection": "v2", "study_id_at_collection": DEFAULT_STUDY_ID,
        "participant_id": user_id,
        "technical_session_id": session_id, "log_id": log_id,
        "started_at": started.isoformat(timespec="milliseconds"),
        "experiment_date": started.date().isoformat(), "timezone": "Europe/Zurich",
        "grade_at_collection": grade,
        "study_session_at_collection": chosen_session["id"] if chosen_session else None,
        "study_session_snapshot": session_snapshot,
        "school_year_at_collection": settings.get("current_school_year") or None,
        "settings_revision_at_collection": settings["revision"],
        "app_version": os.getenv("SOL_APP_VERSION") or None,
        "git_commit": os.getenv("SOL_GIT_COMMIT") or None,
        "task_order": order,
        "tasks": [task_snapshot(n, topic) for n, topic in enumerate(order, 1)],
    }
    if question_set is not None:
        metadata.update(question_set_snapshot=deepcopy(question_set),
                        question_set_theme=question_set.get("theme"),
                        question_set_metadata=deepcopy(question_set.get("metadata", {})),
                        assignment_source=assignment_source)
    safe_user = re.sub(r"[^A-Za-z0-9._-]", "_", str(user_id))[:64] or "anon"
    path = Path(directory) / f"{safe_user}_{log_id}.run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # A temp file + hard-link publishes the complete sidecar without replacing a prior one.
    import tempfile
    fd, temporary = tempfile.mkstemp(prefix=".run-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)
