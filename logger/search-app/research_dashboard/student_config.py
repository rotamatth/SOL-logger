"""Shared participant enrollment and existing question/reward assignments."""
from hashlib import sha256
from pathlib import Path
import csv
import json
import re

APP_ROOT = Path(__file__).resolve().parents[1]
TOPIC_FIELDS = tuple(f"{n}_{kind}" for n in range(1, 4) for kind in ("short", "full", "gif")) + ("full_gif",)


def load_topics(path):
    with open(path, newline="", encoding="utf-8") as source:
        return {row["uid"]: {key: row.get(
            "full_gif" if key == "full_gif" else "topic" + key.replace("_short", "_keyword").replace("_full", "_question"), "").strip()
            for key in TOPIC_FIELDS} for row in csv.DictReader(source)}


def configure_students(app):
    if "STUDENT_TOPICS" not in app.config:
        app.config["STUDENT_TOPICS"] = load_topics(APP_ROOT / "data/user_topics.csv")
    if "STUDENT_LEGACY_IDS" not in app.config:
        app.config["STUDENT_LEGACY_IDS"] = set((APP_ROOT / "data/uids.txt").read_text().split())
    app.config.setdefault("STUDENT_ASSET_DIR", str(APP_ROOT / "static/puzzle_pieces"))


def validate_topics(topics):
    if not isinstance(topics, dict) or set(topics) != set(TOPIC_FIELDS):
        raise ValueError("invalid_task_assignment")
    for key, value in topics.items():
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError("invalid_task_assignment")
        if key.endswith("gif"):
            extensions = (".gif", ".mp4") if key == "full_gif" else (".gif",)
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", value) or value in (".", "..") or not value.lower().endswith(extensions):
                raise ValueError("invalid_task_assignment")
    return topics


def topics_ready(topics, asset_dir):
    return assignment_problem(topics, asset_dir) is None


def assignment_problem(topics, asset_dir):
    if topics is None:
        return "assignment_missing"
    try:
        validate_topics(topics)
    except ValueError:
        return "assignment_invalid"
    if not all((Path(asset_dir) / topics[key]).is_file() for key in TOPIC_FIELDS if key.endswith("gif")):
        return "assignment_rewards_missing"
    return None


def task_catalog(app):
    unique = {}
    for topics in app.config["STUDENT_TOPICS"].values():
        normalized = {key: topics.get(key, "") for key in TOPIC_FIELDS}
        if not topics_ready(normalized, app.config["STUDENT_ASSET_DIR"]):
            continue
        token = sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
        unique[token] = {"id": token, "topics": normalized,
                         "label": normalized["1_short"]}
    return list(unique.values())


def range_ids(rule):
    return [rule["prefix"] + str(n).zfill(rule["width"]) for n in range(rule["start"], rule["end"] + 1)]


def configured_topics(app, rule, uid):
    original = app.config["STUDENT_TOPICS"].get(uid) if uid in app.config["STUDENT_LEGACY_IDS"] else None
    original = {key: original.get(key, "") for key in TOPIC_FIELDS} if original else None
    assignment = rule.get("assignment")
    if assignment and (assignment["mode"] == "all" or not topics_ready(original, app.config["STUDENT_ASSET_DIR"])):
        return assignment["topics"]
    return original


def eligible_students(app, settings):
    return {uid: topics for rule in settings["ranges"] for uid in range_ids(rule)
            if (topics := configured_topics(app, rule, uid))
            and topics_ready(topics, app.config["STUDENT_ASSET_DIR"])}


def range_summary(app, rule):
    ids = range_ids(rule)
    participants = []
    for uid in ids:
        topics = configured_topics(app, rule, uid)
        problem = assignment_problem(topics, app.config["STUDENT_ASSET_DIR"])
        participants.append({"id": uid, "ready": problem is None, "problem": problem,
                             "titles": [topics.get(f"{n}_short", "") for n in range(1, 4)] if topics else [],
                             "questions": [topics.get(f"{n}_full", "") for n in range(1, 4)] if topics else []})
    missing = [person["id"] for person in participants if not person["ready"]]
    return {"grade": rule["grade"], "count": len(ids), "first": ids[0], "last": ids[-1],
            "examples": ids[:5], "ready": len(ids) - len(missing), "missing": missing,
            "participants": participants,
            "ids": ids, "assignment": rule.get("assignment")}
