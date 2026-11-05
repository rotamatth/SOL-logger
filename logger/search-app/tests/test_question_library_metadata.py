"""Historical experimental conditions are explicit library choices, never enrollment."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import csv
import json
import sys

from flask import Flask

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from research_dashboard.state import default_settings
from research_dashboard.student_config import TOPIC_FIELDS, configure_students, load_topic_metadata, load_topics
from research_dashboard.study_config import question_library, scheduled_assignment, validate_question_set


def csv_library(tmp_path):
    path = tmp_path / "questions.csv"
    fields = ["uid", *[f"topic{number}_{field}" for number in range(1, 4)
                       for field in ("keyword", "question", "gif")],
              "full_gif", "high_interest_topic_column", "experimental_condition"]
    rows = []
    for uid, interest in (("1", "first"), ("2", "second"), ("3", "third"), ("4", "first")):
        row = {"uid": uid, "high_interest_topic_column": interest,
               "experimental_condition": "  compare sources  ", "full_gif": "missing.mp4"}
        for number in range(1, 4):
            row.update({f"topic{number}_keyword": f"Topic {number}",
                        f"topic{number}_question": f"Question {number}?",
                        f"topic{number}_gif": "missing.gif"})
        rows.append(row)
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def configured_library(tmp_path):
    app = Flask(__name__)
    app.config.update(STUDENT_TOPICS_PATH=csv_library(tmp_path), STUDENT_LEGACY_IDS=set(),
                      STUDENT_ASSET_DIR=str(tmp_path / "no-assets"))
    configure_students(app)
    return app


def test_csv_conditions_load_separately_without_changing_strict_topic_shape(tmp_path):
    path = csv_library(tmp_path)
    topics, metadata = load_topics(path), load_topic_metadata(path)
    assert set(topics["1"]) == set(TOPIC_FIELDS)
    assert metadata["2"] == {"high_interest_topic_column": "second",
                              "experimental_condition": "compare sources"}
    assert "uid" not in metadata["2"]
    assert not any(field.startswith("topic") for field in metadata["2"])
    app = configured_library(tmp_path)
    assert app.config["STUDENT_TOPICS"] == topics
    assert app.config["STUDENT_TOPIC_METADATA"] == metadata


def test_preloaded_matching_topics_get_metadata_and_custom_content_does_not(tmp_path):
    path = csv_library(tmp_path)
    topics = load_topics(path)
    topics["2"]["1_full"] = "A different source question"
    app = Flask(__name__)
    app.config.update(STUDENT_TOPICS_PATH=path, STUDENT_TOPICS=topics, STUDENT_LEGACY_IDS=set())
    configure_students(app)
    assert app.config["STUDENT_TOPIC_METADATA"]["1"]["high_interest_topic_column"] == "first"
    assert "2" not in app.config["STUDENT_TOPIC_METADATA"]
    assert app.config["STUDENT_TOPICS"]["2"]["1_full"] == "A different source question"


def test_library_distinguishes_conditions_and_maps_interest_to_stable_source_identity(tmp_path):
    app = configured_library(tmp_path)
    catalog = question_library(app, {"sessions": []})
    assert len(catalog) == 3  # Repeated source rows with the same condition deduplicate.
    assert len({entry["label"] for entry in catalog}) == 3
    for position, condition in enumerate(("first", "second", "third")):
        entry = next(item for item in catalog
                     if item["question_set"]["metadata"]["high_interest_topic_column"] == condition)
        draft = entry["question_set"]
        assert f"high_interest_topic_column={condition}" in entry["label"]
        assert draft["metadata"]["experimental_condition"] == "compare sources"
        assert draft["metadata"]["high_interest_question_id"] == draft["questions"][position]["id"]
        assert [question["metadata"]["high_interest"] for question in draft["questions"]] == [
            index == position for index in range(3)]
        assert all(question["id"] == question["metadata"]["source_question_id"]
                   for question in draft["questions"])
        assert draft["approved"] is False
        validate_question_set(draft)
        assert "uid" not in json.dumps(draft)
    assert len({tuple(question["id"] for question in item["question_set"]["questions"])
                for item in catalog}) == 1


def test_explicit_copy_and_text_edits_retain_original_interest_identity_and_metadata(tmp_path):
    app = configured_library(tmp_path)
    original = next(item["question_set"] for item in question_library(app, {"sessions": []})
                    if item["question_set"]["metadata"]["high_interest_topic_column"] == "second")
    edited = deepcopy(original)
    edited["questions"][1].update(topic="An edited topic", question="An edited question?")
    edited["approved"] = True
    settings = {"sessions": [{"question_set": edited}]}
    only_saved = Flask(__name__)
    saved = question_library(only_saved, settings)[0]["question_set"]
    assert saved["metadata"] == original["metadata"]
    assert saved["questions"][1]["metadata"] == original["questions"][1]["metadata"]
    assert saved["metadata"]["high_interest_question_id"] == original["questions"][1]["id"]
    assert saved["questions"][1]["question"] == "An edited question?"
    assert saved["approved"] is False
    assert settings["sessions"][0]["question_set"]["approved"] is True
    saved["metadata"]["experimental_condition"] = "mutated copy"
    assert settings["sessions"][0]["question_set"]["metadata"]["experimental_condition"] == "compare sources"


def test_loading_condition_library_never_assigns_or_approves_a_student_session(tmp_path):
    app = configured_library(tmp_path)
    settings = default_settings()
    settings["sessions"][0]["date"] = date.today().isoformat()
    before = deepcopy(settings)
    assert len(question_library(app, settings)) == 3
    assert scheduled_assignment(settings, "1", date.today()) is None
    assert settings == before
