"""Fresh, explicit question assignments for the next study sessions.

Historical CSV questions are a library only. Enrollment and a study date never
copy an old assignment into a new session or implicitly approve its content.
"""
from copy import deepcopy
from datetime import date, datetime
from hashlib import sha256
from zoneinfo import ZoneInfo
import json
import math
import re


STUDY_TIMEZONE = ZoneInfo("Europe/Zurich")
QUESTION_FIELDS = {"id", "topic", "question", "metadata"}
QUESTION_SET_FIELDS = {"questions", "theme", "metadata", "approved"}


def _text(value, limit):
    return (isinstance(value, str) and len(value) <= limit
            and not any(ord(character) < 32 and character not in "\n\t"
                        or ord(character) == 127 for character in value))


def _metadata(value, depth=0):
    if depth > 8:
        return False
    if isinstance(value, dict):
        return all(isinstance(key, str) and _metadata(item, depth + 1)
                   for key, item in value.items())
    if isinstance(value, list):
        return all(_metadata(item, depth + 1) for item in value)
    return (value is None or isinstance(value, (str, bool, int))
            or isinstance(value, float) and math.isfinite(value))


def validate_question_set(value, require_ready=False):
    """Validate an editable set; incomplete drafts are valid until approved.

    Exactly three complete questions and explicit approval are required for a
    participant to start, but researchers can save a draft with fewer rows or
    empty text. Optional metadata is independent of question readiness.
    """
    if (not isinstance(value, dict) or set(value) - QUESTION_SET_FIELDS
            or not isinstance(value.get("questions"), list)
            or len(value["questions"]) > 3
            or not _text(value.get("theme", ""), 200)
            or type(value.get("approved", False)) is not bool):
        raise ValueError("invalid_question_set")
    for container in [value, *value["questions"]]:
        if not isinstance(container, dict):
            raise ValueError("invalid_question_set")
        if "metadata" in container:
            metadata = container["metadata"]
            if (not isinstance(metadata, dict) or not _metadata(metadata)
                    or len(json.dumps(metadata, ensure_ascii=False)) > 32000):
                raise ValueError("invalid_question_metadata")
    identifiers = set()
    for question in value["questions"]:
        if (set(question) - QUESTION_FIELDS
                or not _text(question.get("id", ""), 100)
                or not _text(question.get("topic", ""), 200)
                or not _text(question.get("question", ""), 2000)):
            raise ValueError("invalid_question_set")
        identifier = question.get("id", "").strip()
        if identifier:
            if identifier in identifiers:
                raise ValueError("duplicate_question_id")
            identifiers.add(identifier)
    if require_ready:
        problem = question_set_problem(value)
        if problem:
            raise ValueError(problem)
    return value


def question_set_problem(question_set):
    if question_set is None:
        return "question_set_missing"
    try:
        validate_question_set(question_set)
    except ValueError:
        return "questions_invalid"
    if (len(question_set["questions"]) != 3
            or any(not question.get(field, "").strip()
                   for question in question_set["questions"] for field in ("id", "topic", "question"))):
        return "questions_incomplete"
    if question_set.get("approved") is not True:
        return "questions_unapproved"
    return None


def question_set_topics(question_set):
    """Adapt question content to the existing student task renderer.

    Reward assets are optional; empty values select the plain completion flow.
    The positional keys do not replace the stable IDs in the question snapshot.
    """
    topics = {f"{number}_{field}": "" for number in range(1, 4)
              for field in ("short", "full", "gif")}
    topics["full_gif"] = ""
    if not question_set:
        return topics
    for number, question in enumerate(question_set.get("questions", [])[:3], 1):
        topics[f"{number}_short"] = question.get("topic", "")
        topics[f"{number}_full"] = question.get("question", "")
        gif = question.get("metadata", {}).get("gif", "")
        topics[f"{number}_gif"] = gif if isinstance(gif, str) else ""
    full_gif = question_set.get("metadata", {}).get("full_gif", "")
    topics["full_gif"] = full_gif if isinstance(full_gif, str) else ""
    return topics


def _range_ids(rule):
    return [rule["prefix"] + str(number).zfill(rule["width"])
            for number in range(rule["start"], rule["end"] + 1)]


def _participant_grade(settings, uid):
    if not isinstance(uid, str):
        return None
    for rule in settings["ranges"]:
        if not uid.startswith(rule["prefix"]):
            continue
        number = uid[len(rule["prefix"]):]
        if not re.fullmatch(r"[0-9]{1,8}", number):
            continue
        value = int(number)
        if (rule["start"] <= value <= rule["end"]
                and rule["prefix"] + str(value).zfill(rule["width"]) == uid):
            return rule["grade"]
    return None


def _resolved_set(study_session, uid):
    overrides = study_session.get("participant_questions", {})
    source = "participant" if uid in overrides else "shared"
    question_set = overrides.get(uid) if source == "participant" else study_session.get("question_set")
    problem = question_set_problem(question_set)
    if not study_session["date"]:
        problem = "session_date_missing"
    return question_set, source, problem


def assignment_for(settings, uid, session_id):
    """Resolve one explicit session assignment, including its blocking reason."""
    grade = _participant_grade(settings, uid)
    study_session = next((item for item in settings["sessions"]
                          if item["id"] == session_id and item["grade"] == grade), None)
    if study_session is None:
        return None
    question_set, source, problem = _resolved_set(study_session, uid)
    return {"session": deepcopy(study_session), "question_set": deepcopy(question_set),
            "topics": question_set_topics(question_set), "source": source,
            "settings_revision": settings.get("revision"),
            "ready": problem is None, "problem": problem}


def session_readiness(settings, study_session):
    """Summarize configuration readiness without requiring today's date."""
    ids = [uid for rule in settings["ranges"] if rule["grade"] == study_session["grade"]
           for uid in _range_ids(rule)]
    participants = []
    for uid in ids:
        question_set, source, problem = _resolved_set(study_session, uid)
        questions = question_set["questions"] if question_set else []
        participants.append({"id": uid, "ready": problem is None,
                             "problem": problem, "source": source,
                             "titles": [question.get("topic", "") for question in questions],
                             "questions": [question.get("question", "") for question in questions]})
    missing = [participant["id"] for participant in participants if not participant["ready"]]
    return {"count": len(ids), "ready": len(ids) - len(missing), "missing": missing,
            "participants": participants, "complete": bool(ids) and not missing}


def scheduled_assignment(settings, uid, now=None):
    """Return only an approved assignment scheduled for today in Zurich.

    Naive datetimes are interpreted as local study time, and a date may be
    supplied directly by a caller that already resolved the study timezone.
    """
    if now is None:
        today = datetime.now(STUDY_TIMEZONE).date()
    elif isinstance(now, datetime):
        today = (now.replace(tzinfo=STUDY_TIMEZONE) if now.tzinfo is None
                 else now.astimezone(STUDY_TIMEZONE)).date()
    elif isinstance(now, date):
        today = now
    else:
        raise ValueError("invalid_study_time")
    grade = _participant_grade(settings, uid)
    study_session = next((item for item in settings["sessions"]
                          if item["grade"] == grade and item["date"] == today.isoformat()), None)
    if study_session is None:
        return None
    assignment = assignment_for(settings, uid, study_session["id"])
    return assignment if assignment["ready"] else None


def _content_id(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def question_library(app, settings=None):
    """Offer historical and saved text for explicit reuse, even without assets."""
    if settings is None:
        research = app.extensions.get("research", {})
        settings = research["state"].settings() if "state" in research else {"sessions": []}
    catalog = {}

    def add(question_set, label=None):
        if not question_set or not question_set.get("questions"):
            return
        if any(not question.get("topic", "").strip() or not question.get("question", "").strip()
               for question in question_set["questions"]):
            return
        draft = deepcopy(question_set)
        draft["approved"] = False
        token = _content_id(draft)
        catalog[token] = {"id": token,
                          "label": label or draft.get("theme") or draft["questions"][0]["topic"],
                          "question_set": draft}

    for uid, topics in app.config.get("STUDENT_TOPICS", {}).items():
        source_metadata = deepcopy(app.config.get("STUDENT_TOPIC_METADATA", {}).get(uid, {}))
        high_interest = {"first": 1, "second": 2, "third": 3}.get(
            source_metadata.get("high_interest_topic_column"))
        questions = []
        high_interest_question_id = None
        for number in range(1, 4):
            topic, question = topics.get(f"{number}_short", ""), topics.get(f"{number}_full", "")
            if not isinstance(topic, str) or not isinstance(question, str) or not topic.strip() or not question.strip():
                continue
            question_id = _content_id({"topic": topic, "question": question})
            question_metadata = {"legacy_topic_id": str(number), "source_question_id": question_id}
            if high_interest is not None:
                question_metadata["high_interest"] = number == high_interest
                if number == high_interest:
                    high_interest_question_id = question_id
            questions.append({"id": question_id,
                              "topic": topic, "question": question,
                              "metadata": question_metadata})
        metadata = {**source_metadata, "origin": "legacy"}
        if "origin" in source_metadata:
            metadata["source_origin"] = source_metadata["origin"]
        if high_interest_question_id is not None:
            metadata["high_interest_question_id"] = high_interest_question_id
        if questions:
            label = questions[0]["topic"]
            condition = ", ".join(f"{key}={value}" for key, value in sorted(source_metadata.items()) if value)
            if condition:
                label += f" · {condition}"
            add({"questions": questions, "theme": "", "metadata": metadata}, label)
    for study_session in settings["sessions"]:
        add(study_session.get("question_set"))
        for question_set in study_session.get("participant_questions", {}).values():
            add(question_set)
    return list(catalog.values())
