"""Protect participant records when removing unused session configuration."""
from .state import DEFAULT_STUDY_ID


def session_removal_problem(index, settings, study_session):
    index.refresh(force=True)
    runs = index.summaries(settings)
    for run in runs:
        if run.get("study_id") != DEFAULT_STUDY_ID:
            continue
        recorded = run.get("study_session_at_collection")
        classified = run.get("study_session") or {}
        if recorded == study_session["id"] or classified.get("id") == study_session["id"]:
            return "session_has_records"
    if index.scan_status()["problems"]:
        return "session_usage_unavailable"
    # Unknown or unreadable sources cannot prove that a session is unused.
    for run in runs:
        detail = index.run(run["id"], settings)
        if detail is None:
            return "session_usage_unavailable"
        if run.get("study_id") is None or run.get("participant_id") is None:
            return "session_usage_unavailable"
        if any(file.get("issues") for file in detail["files"]):
            return "session_usage_unavailable"
    return None
