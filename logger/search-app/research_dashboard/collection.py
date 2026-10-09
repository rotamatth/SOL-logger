"""Write one immutable metadata sidecar for each newly started v2 run."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import re

from .state import DEFAULT_STUDY_ID, roster


def record_run(directory, state, user_id, session_id, log_id, order, topics, settings=None):
    started = datetime.now(ZoneInfo("Europe/Zurich"))
    settings = settings if settings is not None else state.settings()
    grade = roster(settings).get(user_id)
    study_session = next((s["id"] for s in settings["sessions"]
                          if s["grade"] == grade and s["date"] == started.date().isoformat()), None)
    metadata = {
        "schema_version": 1, "collection": "v2", "study_id_at_collection": DEFAULT_STUDY_ID,
        "participant_id": user_id,
        "technical_session_id": session_id, "log_id": log_id,
        "started_at": started.isoformat(timespec="milliseconds"),
        "experiment_date": started.date().isoformat(), "timezone": "Europe/Zurich",
        "grade_at_collection": grade, "study_session_at_collection": study_session,
        "school_year_at_collection": settings.get("current_school_year") or None,
        "settings_revision_at_collection": settings["revision"],
        "app_version": os.getenv("SOL_APP_VERSION") or None,
        "git_commit": os.getenv("SOL_GIT_COMMIT") or None,
        "task_order": order,
        "tasks": [{"presented_number": n, "topic_id": topic,
                   "topic_title": topics.get(f"{topic}_short"),
                   "question": topics.get(f"{topic}_full")}
                  for n, topic in enumerate(order, 1)],
    }
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
