"""Standalone library choices deduplicate text without guessing conditions."""
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
import sys

import pytest
from flask import Flask

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from research_dashboard.study_config import question_choices, question_library, validate_question_set
from .test_research_dashboard import app, login
from .test_session_question_editor import (URL, EditorFields, configured, working_set, editor_form,
                                           save_shared, shared_set)


def entry(identifier, question, set_metadata=None):
    return {"id": identifier, "label": f"Source {identifier}", "question_set": {
        "questions": [question], "metadata": set_metadata or {}, "approved": False}}


def test_identical_wording_is_one_choice_with_stable_token_across_sources():
    library = [
        entry("first", {"id": "source-id", "topic": "The Moon", "question": "Why is it bright?"}),
        entry("second", {"id": "source-id", "topic": "  THE\tMOON ",
                         "question": "  WHY is\nit bright?  "}),
    ]
    choices = question_choices(library)
    assert len(choices) == 1
    choice = choices[0]
    assert choice["count"] == 2
    assert choice["question_data"]["id"] == "source-id"
    assert choice["has_variants"] is False
    assert choice["id"] == question_choices(library[::-1])[0]["id"]
    assert choice["id"] == question_choices(library[1:])[0]["id"]
    assert [(source["library_id"], source["slot"]) for source in choice["sources"]] == [
        ("first", 0), ("second", 0)]


def test_different_question_text_or_topic_remains_separate():
    library = [entry(str(number), {"id": str(number), "topic": topic, "question": text})
               for number, (topic, text) in enumerate([
                   ("Moon", "Why is it bright?"), ("Moon", "How large is it?"),
                   ("Astronomy", "Why is it bright?")])]
    assert len(question_choices(library)) == 3


def test_conflicting_condition_metadata_is_disclosed_and_not_arbitrarily_copied():
    original = {"id": "stable", "topic": "Moon", "question": "Why is it bright?",
                "metadata": {"source_question_id": "stable", "high_interest": True,
                             "nested": {"same": [1, 2]}, "first_only": "not shared"}}
    other = deepcopy(original)
    other["metadata"].pop("first_only")
    other["metadata"]["high_interest"] = False
    library = [entry("first", original, {"condition": "first"}),
               entry("second", other, {"condition": "second"})]
    before = deepcopy(library)
    choice = question_choices(library)[0]
    assert choice["has_variants"] is True
    assert choice["question_data"]["metadata"] == {
        "source_question_id": "stable", "nested": {"same": [1, 2]}}
    assert choice["sources"][0]["question_data"]["metadata"]["high_interest"] is True
    assert choice["sources"][1]["question_data"]["metadata"]["high_interest"] is False
    assert choice["sources"][0]["set_metadata"] == {"condition": "first"}
    choice["question_data"]["metadata"]["nested"]["same"].append(3)
    choice["sources"][0]["question_data"]["metadata"]["nested"]["same"].append(4)
    assert library == before


def test_identity_changes_get_stable_choice_identity_and_keep_original_sources():
    library = [entry("first", {"id": "old-id", "topic": "Moon", "question": "Why?",
                               "metadata": {"source_question_id": "old-id"}}),
               entry("second", {"id": "other-id", "topic": " Moon ", "question": "WHY?",
                                "metadata": {"source_question_id": "other-id"}})]
    choice = question_choices(library)[0]
    assert choice["has_variants"] is True
    assert choice["question_data"]["id"] == choice["id"]
    assert "source_question_id" not in choice["question_data"]["metadata"]
    assert choice["sources"][0]["question_data"]["id"] == "old-id"
    validate_question_set({"questions": [choice["question_data"]], "approved": False})


def test_common_metadata_requires_identical_types_and_can_be_absent():
    library = [entry("first", {"id": "same", "topic": "Moon", "question": "Why?",
                               "metadata": {"flag": False, "number": 1,
                                            "same": {"a": 1, "b": 2}}}),
               entry("second", {"id": "same", "topic": "Moon", "question": "Why?",
                                "metadata": {"flag": 0, "number": 1.0,
                                             "same": {"b": 2, "a": 1}}})]
    assert question_choices(library)[0]["question_data"]["metadata"] == {"same": {"a": 1, "b": 2}}
    library.append(entry("third", {"id": "same", "topic": "Moon", "question": "Why?"}))
    assert question_choices(library)[0]["question_data"]["metadata"] == {}


def test_historical_conditions_remain_available_but_per_question_duplicates_disappear():
    app = Flask(__name__)
    topics = {f"{number}_{field}": value for number in range(1, 4)
              for field, value in (("short", f"Topic {number}"), ("full", f"Question {number}?"))}
    app.config.update(STUDENT_TOPICS={"1": topics, "2": topics, "3": topics},
                      STUDENT_TOPIC_METADATA={str(index): {"high_interest_topic_column": condition}
                                              for index, condition in enumerate(
                                                  ("first", "second", "third"), 1)})
    library = question_library(app, {"sessions": []})
    assert len(library) == 3
    choices = question_choices(library)
    assert len(choices) == 3
    assert all(choice["count"] == 3 and choice["has_variants"] for choice in choices)
    assert all("high_interest" not in choice["question_data"]["metadata"] for choice in choices)
    assert all(choice["question_data"]["id"] == choice["question_data"]["metadata"]["source_question_id"]
               for choice in choices)


def test_empty_library_has_no_choices():
    assert question_choices([]) == []


def historical_conditions(app):
    topics = {f"{number}_{field}": value for number in range(1, 4)
              for field, value in (("short", f"Library topic {number}"),
                                   ("full", f"Library question {number}?"))}
    app.config.update(STUDENT_TOPICS={"1": topics, "2": topics, "3": topics},
                      STUDENT_TOPIC_METADATA={str(index): {"high_interest_topic_column": condition}
                                              for index, condition in enumerate(
                                                  ("first", "second", "third"), 1)})
    return question_library(app, {"sessions": []})


class LibrarySelects(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.selects = {}
        self.active = None
        self.option = None
        self.feed(response.text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select":
            self.active = attrs.get("name")
            self.selects[self.active] = []
        if tag == "option" and self.active and attrs.get("value"):
            self.option = {"id": attrs["value"], "label": ""}
            self.selects[self.active].append(self.option)

    def handle_endtag(self, tag):
        if tag == "option":
            self.option = None
        if tag == "select":
            self.active = None

    def handle_data(self, data):
        if self.option is not None:
            self.option["label"] += data


def test_editor_displays_each_question_once_and_keeps_explicit_condition_set_choices(app):
    library = historical_conditions(app)
    client = app.test_client()
    login(client)
    response = client.get(URL)
    assert response.status_code == 200
    selects = LibrarySelects(response).selects
    expected_ids = {choice["id"] for choice in question_choices(library)}
    for slot in range(3):
        options = selects[f"library_question_{slot}"]
        normalized_labels = [" ".join(option["label"].split()).casefold() for option in options]
        assert len(options) == len(set(normalized_labels)) == 3
        assert {option["id"] for option in options} == expected_ids
    full_sets = selects["library_set"]
    assert len(full_sets) == 3
    assert {option["id"] for option in full_sets} == {item["id"] for item in library}
    assert all(any(f"high_interest_topic_column={condition}" in option["label"] for option in full_sets)
               for condition in ("first", "second", "third"))


@pytest.mark.parametrize("save_action", ["save_draft", "approve_questions"])
def test_unique_question_selection_saves_without_guessing_condition_or_losing_other_fields(app, save_action):
    library = historical_conditions(app)
    client = app.test_client()
    login(client)
    configured(app)
    original = deepcopy(save_shared(app, client))
    choice = question_choices(library)[0]
    state = app.extensions["research"]["state"]
    before = state.settings()
    response = client.post(URL, data=editor_form(
        client, action="load_questions", library_question_1=choice["id"],
        theme="Still my theme", topic_2="Unsaved third topic", question_2="Unsaved third question?"))
    assert response.status_code == 200
    fields = EditorFields(response).fields
    assert fields["question_1"] == choice["question"]
    assert fields["topic_2"] == "Unsaved third topic"
    assert fields["question_2"] == "Unsaved third question?"
    assert fields["theme"] == "Still my theme"
    assert "approved" not in fields
    assert state.settings() == before
    fields["action"] = save_action
    assert client.post(URL, data=fields).status_code == 302
    saved = working_set(app)
    assert saved["approved"] is (save_action == "approve_questions")
    assert saved["theme"] == "Still my theme"
    assert saved["questions"][1] == choice["question_data"]
    assert "high_interest" not in saved["questions"][1]["metadata"]
    assert saved["questions"][0] == original["questions"][0]
    assert saved["questions"][2]["id"] == original["questions"][2]["id"]
    assert saved["questions"][2]["topic"] == "Unsaved third topic"
    assert saved["questions"][2]["question"] == "Unsaved third question?"


@pytest.mark.parametrize("save_action", ["save_draft", "approve_questions"])
def test_unique_choice_with_loaded_set_context_keeps_that_explicit_condition(app, save_action):
    library = historical_conditions(app)
    selected_set = next(item for item in library
                        if item["question_set"]["metadata"]["high_interest_topic_column"] == "second")
    choice = question_choices(library)[0]
    client = app.test_client()
    login(client)
    configured(app)
    before = app.extensions["research"]["state"].settings()
    loaded = client.post(URL, data=editor_form(client, action="load_set", library_set=selected_set["id"]))
    assert loaded.status_code == 200
    fields = EditorFields(loaded).fields
    fields.update(action="load_questions", library_question_0=choice["id"], theme="Explicit condition")
    applied = client.post(URL, data=fields)
    assert applied.status_code == 200
    assert app.extensions["research"]["state"].settings() == before
    fields = EditorFields(applied).fields
    fields["action"] = save_action
    assert client.post(URL, data=fields).status_code == 302
    saved = working_set(app)
    assert saved["approved"] is (save_action == "approve_questions")
    assert saved["theme"] == "Explicit condition"
    assert saved["metadata"] == selected_set["question_set"]["metadata"]
    assert saved["questions"] == selected_set["question_set"]["questions"]
    assert saved["questions"][0]["metadata"]["high_interest"] is False
    assert saved["questions"][1]["metadata"]["high_interest"] is True


def test_conflicting_sources_with_same_set_context_still_do_not_guess_question_metadata(app):
    library = historical_conditions(app)
    original = next(item["question_set"] for item in library
                    if item["question_set"]["metadata"]["high_interest_topic_column"] == "first")
    edited = deepcopy(original)
    edited["questions"][0]["metadata"]["high_interest"] = False
    configured(app, question_set=edited)
    choice = next(item for item in question_choices(question_library(app))
                  if item["topic"] == edited["questions"][0]["topic"])
    client = app.test_client()
    login(client)
    response = client.post(URL, data=editor_form(client, action="load_questions", library_question_0=choice["id"]))
    assert response.status_code == 200
    fields = EditorFields(response).fields
    fields["action"] = "save_draft"
    assert client.post(URL, data=fields).status_code == 302
    saved = working_set(app)
    assert "high_interest" not in saved["questions"][0]["metadata"]
    assert saved["questions"][0]["id"] == original["questions"][0]["id"]
    assert saved["questions"][1:] == edited["questions"][1:]
