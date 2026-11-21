"""The practice question before the ID: one question on a topic no class studies, set in the dashboard.

It is stored apart from the study settings, in its own table with its own revisions, so saving it never
changes a session, an ID or the settings revision that admission checks. Older versions of the application
ignore the table, so a rollback still opens the database. Nothing a child does in the practice is stored.
"""
import re

PRACTICE_DEFAULT = {
    "enabled": True,
    "topic": "Vulcani",
    "question": "Le eruzioni vulcaniche possono essere di diversi tipi. Sapete elencarne 3?",
}
TOPIC_MAX = 80
QUESTION_MAX = 300
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _text(value, limit, error):
    if not isinstance(value, str):
        raise ValueError(error)
    value = " ".join(value.split())
    if not value or len(value) > limit or _CONTROL.search(value):
        raise ValueError(error)
    return value


def validate_practice(value):
    """A complete, normalized practice document. Raises ValueError(code) for the dashboard to show."""
    if not isinstance(value, dict) or type(value.get("enabled")) is not bool:
        raise ValueError("invalid_practice")
    return {"enabled": value["enabled"],
            "topic": _text(value.get("topic"), TOPIC_MAX, "practice_topic_invalid"),
            "question": _text(value.get("question"), QUESTION_MAX, "practice_question_invalid")}
