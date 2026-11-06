"""Statistics per task, computed from logged events. Original logs are never changed.

``add_event`` is fed one event at a time by the reporting index and the live view.
A count of 0 means the task has events but none of that kind. ``None`` means there is
nothing to measure, and pages show it as a dash.
"""
from datetime import datetime
from statistics import median

COUNTED_EVENTS = {
    "querySubmitted": "searches",
    "searchNoResults": "no_results",
    "choseAutoCompleteSuggestion": "suggestions",
    "clickedDidYouMeanSuggestion": "suggestions",
    "clickedResult": "results_opened",
    "taskQuestionHelpClicked": "help_opened",
    "searchError": "search_errors",
    "webpageLoadFailed": "pages_failed",
}
COUNTERS = ("events", "searches", "no_results", "suggestions", "results_opened", "help_opened",
            "search_errors", "pages_failed")


def new_stats():
    return {**dict.fromkeys(COUNTERS, 0), "started_at": None, "ended_at": None,
            "rank_sum": 0, "rank_count": 0, "page_ms": 0, "pages_timed": 0}


def _number(value):
    """A non-negative number. The result rank is logged as text, for example "3"."""
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def add_event(stats, event):
    """Count one logged event of a task."""
    stats["events"] += 1
    kind = event.get("type")
    counter = COUNTED_EVENTS.get(kind)
    if counter:
        stats[counter] += 1
    timestamp = event.get("timestamp")
    if kind == "TaskStarted" and isinstance(timestamp, str):
        # A resumed task logs TaskStarted again: time runs from the first one.
        stats["started_at"] = min(stats["started_at"] or timestamp, timestamp)
    elif kind == "TaskEnded" and isinstance(timestamp, str) and not stats["ended_at"]:
        stats["ended_at"] = timestamp
    if kind == "clickedResult" and (rank := _number(event.get("rank"))) is not None:
        stats["rank_sum"] += rank
        stats["rank_count"] += 1
    if kind == "webpageClosed" and (duration := _number(event.get("durationMs"))) is not None:
        stats["page_ms"] += duration
        stats["pages_timed"] += 1
    return stats


def merge_stats(first, second):
    """Combine the statistics of one task recorded across several source files."""
    if not first or not second:
        return dict(first or second or new_stats())
    merged = {key: first[key] + second[key] for key in (*COUNTERS, "rank_sum", "rank_count", "page_ms", "pages_timed")}
    starts = [value for value in (first["started_at"], second["started_at"]) if value]
    ends = [value for value in (first["ended_at"], second["ended_at"]) if value]
    merged.update(started_at=min(starts) if starts else None, ended_at=min(ends) if ends else None)
    return merged


def _seconds_between(start, end):
    try:
        seconds = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    except (TypeError, ValueError):  # Missing, malformed, or mixing naive and timezone-aware values.
        return None
    return seconds if seconds >= 0 else None


def summarize(stats):
    """The figures pages show for one task."""
    if not stats or not stats["events"]:
        return {**dict.fromkeys(COUNTERS), "seconds": None, "mean_rank": None, "page_seconds": None, "finished": False}
    return {**{key: stats[key] for key in COUNTERS},
            "seconds": _seconds_between(stats["started_at"], stats["ended_at"]),
            "mean_rank": _plain(round(stats["rank_sum"] / stats["rank_count"], 1)) if stats["rank_count"] else None,
            "page_seconds": round(stats["page_ms"] / 1000) if stats["pages_timed"] else None,
            "finished": bool(stats["ended_at"])}


def _plain(value):
    """5.0 reads as 5 on the page; 2.5 stays as it is."""
    return int(value) if isinstance(value, float) and value.is_integer() else value


def _spread(values):
    values = [value for value in values if value is not None]
    if not values:
        return {"median": None, "low": None, "high": None}
    return {"median": _plain(median(values)), "low": min(values), "high": max(values)}


def question_rows(runs, expected=None):
    """One row per question of a session, across children.

    Questions are grouped by what was asked, not by position, because the order is shuffled
    per child. Each child counts once per question: their latest run that finished it.
    """
    latest = {}
    collected = [run for run in runs if not run.get("recovery_only")]
    for run in sorted(collected, key=lambda item: (item.get("started_at") or "", item.get("date") or "", item["id"])):
        child = run.get("study_participant_id") or run.get("participant_id")
        for task in (run.get("task_stats") or {}).values():
            if child is not None and task.get("finished") and task.get("question"):
                key = (task.get("topic"), task["question"])
                latest[(key, child)] = {**task, "individual": run.get("assignment_source") == "participant"}
    grouped = {}
    for (key, _), task in latest.items():
        grouped.setdefault(key, []).append(task)
    rows = []
    for (topic, question), tasks in grouped.items():
        rows.append({"topic": topic, "question": question, "finished": len(tasks), "expected": expected,
                     "individual": any(task["individual"] for task in tasks),
                     "seconds": _spread(task.get("seconds") for task in tasks),
                     "searches": _spread(task.get("searches") for task in tasks),
                     "results_opened": _spread(task.get("results_opened") for task in tasks),
                     "events": _spread(task.get("events") for task in tasks)})
    rows.sort(key=lambda row: (row["individual"], str(row["topic"]), row["question"]))
    return rows


def session_rows(runs):
    """One row per session for one child, oldest first: totals over the tasks that child finished."""
    grouped = {}
    for run in runs:
        session = run.get("study_session")
        if (session and not run.get("recovery_only")
                and any(task.get("finished") for task in (run.get("task_stats") or {}).values())):
            grouped.setdefault(session["id"], (session, []))[1].append(run)
    rows = []
    for session, session_runs in grouped.values():
        finished = {}
        for run in sorted(session_runs, key=lambda item: (item.get("started_at") or "", item["id"])):
            for task in run["task_stats"].values():
                if task.get("finished"):
                    finished[(task.get("topic"), task.get("question"))] = task
        tasks = list(finished.values())
        timed = [task["seconds"] for task in tasks if task.get("seconds") is not None]
        rows.append({"session": session, "finished": len(tasks),
                     "seconds": sum(timed) if timed else None,
                     "searches": sum(task.get("searches") or 0 for task in tasks),
                     "results_opened": sum(task.get("results_opened") or 0 for task in tasks),
                     "events": sum(task.get("events") or 0 for task in tasks)})
    rows.sort(key=lambda row: (row["session"].get("date") or "", row["session"].get("number") or 0))
    return rows


CHART_WIDTH, CHART_BASE, CHART_TOP = 240, 88, 14
CHART_MAX_COLUMNS = 12
MAX_COLUMN_WIDTH = 24
COLUMN_RADIUS = 4


def _clean_top(value):
    """A round number at or above the largest value, for the top of a chart."""
    if value <= 5:
        return 5
    magnitude = 10 ** (len(str(int(value))) - 1)
    for step in (1, 2, 5, 10):
        if value <= step * magnitude:
            return step * magnitude
    return value


def chart_columns(values):
    """Geometry of a small column chart: rounded at the data end, square at the baseline.

    Sessions without a value keep their slot and draw nothing, so a gap never reads as zero.
    """
    known = [value for value in values if value is not None]
    top = _clean_top(max(known, default=0))
    slot = CHART_WIDTH / max(len(values), 1)
    width = min(MAX_COLUMN_WIDTH, slot - 2)
    columns = []
    for position, value in enumerate(values):
        left = round(position * slot + (slot - width) / 2, 1)
        column = {"left": left, "center": round(left + width / 2, 1), "slot_left": round(position * slot, 1),
                  "slot_width": round(slot, 1), "value": value, "path": None, "label_y": CHART_BASE - 4}
        if value:
            height = max((CHART_BASE - CHART_TOP) * value / top, 2)
            radius = min(COLUMN_RADIUS, height, width / 2)
            y = round(CHART_BASE - height, 1)
            column["label_y"] = round(y - 4, 1)
            column["path"] = (f"M{left} {CHART_BASE}V{round(y + radius, 1)}Q{left} {y} {round(left + radius, 1)} {y}"
                              f"H{round(left + width - radius, 1)}Q{round(left + width, 1)} {y} "
                              f"{round(left + width, 1)} {round(y + radius, 1)}V{CHART_BASE}Z")
        columns.append(column)
    return {"top": top, "columns": columns, "width": CHART_WIDTH, "base": CHART_BASE}


def trend_charts(rows):
    """The three small charts of one child across their most recent sessions."""
    recent = rows[-CHART_MAX_COLUMNS:]
    minutes = [None if row["seconds"] is None else _plain(round(row["seconds"] / 60, 1)) for row in recent]
    return {"sessions": [row["session"] for row in recent],
            "charts": [("stats_minutes", chart_columns(minutes)),
                       ("stats_searches", chart_columns([row["searches"] for row in recent])),
                       ("stats_results", chart_columns([row["results_opened"] for row in recent]))]}


def format_duration(seconds):
    """Compact time for pages, the same in English and Italian. Missing values stay a dash."""
    if seconds is None:
        return "—"
    total = round(seconds)
    minutes, rest = divmod(total, 60)
    if not minutes:
        return f"{rest} s"
    return f"{minutes} min {rest} s" if rest else f"{minutes} min"
