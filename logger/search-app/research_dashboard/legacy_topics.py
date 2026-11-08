"""Names of the questions in the first app's runs, whose logs record only the topic number.

The first app read each child's three topics from ``data/user_topics.csv``. Its logs say "topic 3", so the
dashboard looks the name up there: "Bandiera India simbolo" instead of "3". The file last changed on
19 May 2026, the day of May's experiment, so older runs may have had other topics and get no name.
"""
import csv
from functools import lru_cache
from pathlib import Path

TOPICS_FILE = Path(__file__).resolve().parents[1] / "data" / "user_topics.csv"
VALID_FROM = "2026-05-19"


@lru_cache(maxsize=1)
def _topics():
    try:
        with TOPICS_FILE.open(newline="", encoding="utf-8") as handle:
            return {row["uid"].strip(): {str(number): (row.get(f"topic{number}_keyword") or "").strip()
                                         for number in (1, 2, 3)}
                    for row in csv.DictReader(handle) if row.get("uid")}
    except (OSError, csv.Error, KeyError, UnicodeError):
        return {}


def topic_name(run, topic):
    """The name of a topic of a legacy run from May's experiment on, or None."""
    if run.get("collection") != "legacy" or not isinstance(run.get("date"), str) or run["date"] < VALID_FROM:
        return None
    return _topics().get(str(run.get("participant_id")), {}).get(str(topic)) or None


def named_task_stats(run):
    """The run's task figures, with a ``topic_name`` where the log has a topic number but no question."""
    stats = run.get("task_stats") or {}
    return {number: {**task, "topic_name": topic_name(run, task.get("topic"))}
            if not task.get("question") and task.get("topic") is not None else task
            for number, task in stats.items()}
