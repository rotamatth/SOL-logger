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
# The two question sets of 19 May 2026: the 3rd class had India; the 4th class had space, with the questions
# this year's 4th class has again.
THEMES = {("Fiume sacro India", "Bandiera India simbolo", "Animali India"): "India",
          ("Sistema solare Giove", "Primo animale nello spazio", "Altre galassie"): "Spazio"}


@lru_cache(maxsize=1)
def _questions():
    """Each ID's three (topic, question) pairs, in the order of the file's columns."""
    try:
        with TOPICS_FILE.open(newline="", encoding="utf-8") as handle:
            return {row["uid"].strip(): tuple(((row.get(f"topic{number}_keyword") or "").strip(),
                                               (row.get(f"topic{number}_question") or "").strip())
                                              for number in (1, 2, 3))
                    for row in csv.DictReader(handle) if row.get("uid")}
    except (OSError, csv.Error, KeyError, UnicodeError):
        return {}


def _dated(date):
    return isinstance(date, str) and date >= VALID_FROM


def legacy_question(run, topic):
    """The topic name and question of a legacy run from May's experiment on, or None."""
    if run.get("collection") != "legacy" or not _dated(run.get("date")) or str(topic) not in ("1", "2", "3"):
        return None
    questions = _questions().get(str(run.get("participant_id")))
    if not questions or not questions[int(topic) - 1][0]:
        return None
    name, question = questions[int(topic) - 1]
    return {"topic": name, "question": question}


def topic_name(run, topic):
    """The name of a topic of a legacy run from May's experiment on, or None."""
    found = legacy_question(run, topic)
    return found["topic"] if found else None


def experiment_questions(uids, date):
    """The theme and the three questions that all these IDs had in a past experiment, or None if they differ."""
    questions = _questions()
    sets = {questions.get(uid) for uid in uids}
    if not uids or not _dated(date) or len(sets) != 1 or None in sets:
        return None
    pairs = sets.pop()
    return {"theme": THEMES.get(tuple(topic for topic, _ in pairs)),
            "questions": [{"topic": topic, "question": question} for topic, question in pairs]}


def named_task_stats(run):
    """The run's task figures, with a ``topic_name`` where the log has a topic number but no question."""
    stats = run.get("task_stats") or {}
    return {number: {**task, "topic_name": topic_name(run, task.get("topic"))}
            if not task.get("question") and task.get("topic") is not None else task
            for number, task in stats.items()}
