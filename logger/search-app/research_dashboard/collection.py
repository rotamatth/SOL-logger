"""Write one immutable metadata sidecar for each newly started v2 run."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import re
import tempfile

from .state import DEFAULT_STUDY_ID, roster
from .runtime import sync_directory
from .participants import enrollment


def record_run(directory, state, user_id, session_id, log_id, order, topics, settings=None,
               study_session=None, question_set=None, assignment_source=None, admit=False):
    started = datetime.now(ZoneInfo("Europe/Zurich"))
    settings = settings if settings is not None else state.settings()
    grade = roster(settings).get(user_id)
    chosen_session = study_session if study_session is not None else next(
        (s for s in settings["sessions"]
         if s["grade"] == grade and s["date"] == started.date().isoformat()), None)
    year = chosen_session.get("school_year") if chosen_session else settings.get("current_school_year")
    context = enrollment(settings, user_id, year)
    grade = context["grade"] if context else grade
    session_snapshot = ({key: deepcopy(chosen_session[key])
                         for key in ("id", "name", "date", "theme", "grade", "number", "school_year")
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
        "school_year_at_collection": year or None,
        "participant_key": context["participant_key"] if context else None,
        "enrollment_id": context["enrollment_id"] if context else None,
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
    if admit:
        state.admit_attempt(metadata)
    publish_metadata(directory, metadata)
    if admit:
        state.mark_attempt_published(session_id)
    return metadata


def publish_metadata(directory, metadata):
    safe_user = re.sub(r"[^A-Za-z0-9._-]", "_", str(metadata["participant_id"]))[:64] or "anon"
    path = Path(directory) / f"{safe_user}_{metadata['log_id']}.run.json"
    if path.exists():
        if path.is_symlink() or json.loads(path.read_text()) != metadata:
            raise FileExistsError("Conflicting immutable run metadata")
        sync_directory(path.parent)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # A temp file + hard-link publishes the complete sidecar without replacing a prior one.
    fd, temporary = tempfile.mkstemp(prefix=".run-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or json.loads(path.read_text()) != metadata:
                raise FileExistsError("Conflicting immutable run metadata") from None
        sync_directory(path.parent)
    finally:
        os.unlink(temporary)


def publish_pending_runs(directory, state):
    for metadata in state.pending_attempts():
        publish_metadata(directory, metadata)
        state.mark_attempt_published(metadata["technical_session_id"])
