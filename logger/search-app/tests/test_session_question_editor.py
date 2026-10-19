"""Researcher question editor tests against synthetic settings only."""
from copy import deepcopy
from html.parser import HTMLParser

import pytest

from .test_research_dashboard import app, csrf, login
from research_dashboard.state import State
from research_dashboard.study_config import assignment_for, question_library


URL = "/dashboard/settings/questions/grade-4-session-1"


class EditorFields(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.fields = {}
        self.active = False
        self.textarea = None
        self.feed(response.text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and "question-editor" in attrs.get("class", "").split():
            self.active = True
        if not self.active:
            return
        name = attrs.get("name")
        if tag == "input" and name:
            if attrs.get("type") != "checkbox" or "checked" in attrs:
                self.fields[name] = attrs.get("value", "")
        if tag == "textarea" and name:
            self.textarea = name
            self.fields[name] = ""

    def handle_endtag(self, tag):
        if tag == "form":
            self.active = False
        if tag == "textarea":
            self.textarea = None

    def handle_data(self, data):
        if self.active and self.textarea:
            self.fields[self.textarea] += data


def editor_form(client, url=URL, action="save_questions", **changes):
    response = client.get(url)
    assert response.status_code == 200
    return {**EditorFields(response).fields, "action": action, **changes}


def custom_fields(theme="Fresh V2", approved=True):
    fields = {"theme": theme}
    for slot in range(3):
        fields[f"topic_{slot}"] = f"{theme} topic {slot + 1}"
        fields[f"question_{slot}"] = f"{theme} question {slot + 1}?"
    if approved:
        fields["approved"] = "1"
    return fields


def configured(app, **changes):
    state = app.extensions["research"]["state"]
    settings = state.settings()
    settings["sessions"][0].update(date="2026-10-15", **changes)
    state.save_settings(settings, settings["revision"])
    return state.settings()


def shared_set(app):
    return app.extensions["research"]["state"].settings()["sessions"][0]["question_set"]


def save_shared(app, client, **changes):
    fields = editor_form(client, **custom_fields(), **changes)
    response = client.post(URL, data=fields)
    assert response.status_code == 302
    return shared_set(app)


def test_editor_starts_with_empty_fields_and_no_legacy_assignment_carryover(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    before = state.settings()
    response = client.get(URL)
    fields = EditorFields(response).fields
    assert fields["theme"] == "" and "approved" not in fields
    assert all(fields[f"topic_{slot}"] == fields[f"question_{slot}"] == "" for slot in range(3))
    assert "Session date missing" in response.text
    assert "0 / 20" in response.text
    assert state.settings() == before
    assert client.get("/dashboard/settings?section=sessions&grade=4").text.count("Configure questions") >= 3


def test_custom_draft_can_save_incomplete_but_approval_requires_three_questions(app):
    client = app.test_client()
    login(client)
    configured(app)
    draft = editor_form(client, theme="A draft", topic_0="One topic", question_0="One question?")
    assert client.post(URL, data=draft).status_code == 302
    saved = shared_set(app)
    assert not saved["approved"] and saved["questions"][0]["topic"] == "One topic"
    before = app.extensions["research"]["state"].settings()
    response = client.post(URL, data=editor_form(client, approved="1"))
    assert response.status_code == 400 and "Complete all three topics and questions" in response.text
    assert EditorFields(response).fields["theme"] == "A draft"
    assert app.extensions["research"]["state"].settings() == before
    saved = save_shared(app, client)
    assert saved["approved"] and len(saved["questions"]) == 3
    assert "20 / 20" in client.get(URL).text
    assert "20 / 20 configuration complete" in client.get("/dashboard/settings?section=sessions&grade=4").text
    roster = client.get("/dashboard/settings?section=participants&grade=4&participant_session=grade-4-session-1")
    assert "20</strong><span>configuration complete" in roster.text
    assert all("metadata" not in question for question in saved["questions"])


def test_approved_question_edit_preserves_metadata_and_stable_identity(app):
    client = app.test_client()
    login(client)
    configured(app)
    original = save_shared(app, client)
    original["metadata"] = {"keywords": ["research"], "full_gif": "optional.mp4"}
    original["questions"][0]["metadata"] = {"difficulty": 2, "gif": "optional.gif"}
    configured(app, question_set=original)
    before = deepcopy(original)
    response = client.post(URL, data=editor_form(client, question_0="Edited question <&>"))
    assert response.status_code == 302
    saved = shared_set(app)
    assert saved["metadata"] == before["metadata"]
    assert saved["questions"][0]["metadata"] == before["questions"][0]["metadata"]
    assert saved["questions"][0]["id"] == before["questions"][0]["id"]
    assert saved["questions"][0]["question"] == "Edited question <&>"
    assert "Edited question &lt;&amp;&gt;" in client.get(URL).text


def test_loading_library_set_previews_without_saving_and_requires_approval(app):
    client = app.test_client()
    login(client)
    configured(app)
    state = app.extensions["research"]["state"]
    before = state.settings()
    historical = question_library(app, before)[0]
    response = client.post(URL, data=editor_form(client, action="load_set", approved="1",
                                                library_set=historical["id"]))
    assert response.status_code == 200
    fields = EditorFields(response).fields
    assert "approved" not in fields
    assert fields["topic_0"] == historical["question_set"]["questions"][0]["topic"]
    assert state.settings() == before
    fields.update(action="save_questions", approved="1", question_0="Edited after library load?")
    assert client.post(URL, data=fields).status_code == 302
    saved = shared_set(app)
    assert saved["approved"] and saved["questions"][0]["question"] == "Edited after library load?"
    assert saved["questions"][1]["id"] == historical["question_set"]["questions"][1]["id"]
    assert saved["questions"][1]["metadata"] == historical["question_set"]["questions"][1]["metadata"]


def test_individual_library_question_reuse_preserves_unselected_slots_and_provenance(app):
    client = app.test_client()
    login(client)
    configured(app)
    original = deepcopy(save_shared(app, client))
    historical = next(item for item in question_library(app) if item["question_set"].get("metadata", {}).get("origin") == "legacy")
    selected = historical["question_set"]["questions"][2]
    state = app.extensions["research"]["state"]
    before = state.settings()
    response = client.post(URL, data=editor_form(client, action="load_questions",
                                                library_question_1=historical["id"] + ":2"))
    assert response.status_code == 200
    fields = EditorFields(response).fields
    assert "approved" not in fields
    assert fields["question_1"] == selected["question"]
    assert fields["question_0"] == original["questions"][0]["question"]
    assert fields["question_2"] == original["questions"][2]["question"]
    assert state.settings() == before
    fields.update(action="save_questions", approved="1")
    assert client.post(URL, data=fields).status_code == 302
    saved = shared_set(app)
    assert saved["questions"][1] == selected
    assert saved["questions"][0] == original["questions"][0]
    assert saved["questions"][2] == original["questions"][2]


def test_duplicate_library_questions_preserve_draft_and_can_be_corrected(app):
    client = app.test_client()
    login(client)
    configured(app)
    save_shared(app, client)
    historical = next(item for item in question_library(app)
                      if item["question_set"].get("metadata", {}).get("origin") == "legacy")
    loaded = client.post(URL, data=editor_form(
        client, action="load_questions", question_2="Unsaved third question?",
        library_question_0=historical["id"] + ":0", library_question_1=historical["id"] + ":0"))
    assert loaded.status_code == 200
    fields = EditorFields(loaded).fields
    fields.update(action="save_questions", approved="1")
    rejected = client.post(URL, data=fields)
    assert rejected.status_code == 400
    fields = EditorFields(rejected).fields
    assert fields["question_2"] == "Unsaved third question?"
    assert fields["question_0"] == fields["question_1"] == historical["question_set"]["questions"][0]["question"]
    fields.update(action="load_questions", library_question_1=historical["id"] + ":1")
    corrected = client.post(URL, data=fields)
    assert corrected.status_code == 200
    fields = EditorFields(corrected).fields
    fields.update(action="save_questions", approved="1")
    assert client.post(URL, data=fields).status_code == 302
    saved = shared_set(app)
    assert saved["questions"][1] == historical["question_set"]["questions"][1]
    assert saved["questions"][2]["question"] == "Unsaved third question?"


def test_participant_exception_save_remove_are_isolated_to_one_id_and_session(app):
    client = app.test_client()
    login(client)
    configured(app)
    shared = deepcopy(save_shared(app, client))
    state = app.extensions["research"]["state"]
    before = state.settings()
    exception_url = URL + "?participant=1"
    preview = client.get(exception_url)
    fields = EditorFields(preview).fields
    assert fields["question_0"] == shared["questions"][0]["question"]
    assert "approved" not in fields
    assert state.settings() == before
    fields.update(action="save_questions", approved="1", question_0="Individual question?")
    assert client.post(exception_url, data=fields).status_code == 302
    settings = state.settings()
    assert settings["sessions"][0]["question_set"] == shared
    assert settings["sessions"][1:] == before["sessions"][1:]
    assert settings["ranges"] == before["ranges"]
    assert assignment_for(settings, "1", "grade-4-session-1")["source"] == "participant"
    assert assignment_for(settings, "2", "grade-4-session-1")["question_set"] == shared
    assert client.post(exception_url, data=editor_form(client, exception_url,
                       action="remove_exception")).status_code == 302
    settings = state.settings()
    assert not settings["sessions"][0].get("participant_questions")
    assert assignment_for(settings, "1", "grade-4-session-1")["question_set"] == shared


def test_stale_editor_retains_submitted_draft_and_never_overwrites_new_revision(app):
    client = app.test_client()
    login(client)
    configured(app)
    fields = editor_form(client, **custom_fields("My stale draft"))
    state = app.extensions["research"]["state"]
    worker = State(state.path.parent)
    changed = worker.settings()
    changed["current_school_year"] = "2026/2027"
    worker.save_settings(changed, changed["revision"])
    latest = state.settings()
    for _ in range(2):
        response = client.post(URL, data=fields)
        assert response.status_code == 400 and "Another researcher updated the settings" in response.text
        returned = EditorFields(response).fields
        assert returned["theme"] == "My stale draft"
        assert returned["question_0"] == "My stale draft question 1?"
        assert returned["revision"] == fields["revision"]
        assert state.settings() == latest


def test_changing_shared_questions_preserves_previously_saved_individual_assignment(app):
    client = app.test_client()
    login(client)
    configured(app)
    save_shared(app, client)
    exception_url = URL + "?participant=1"
    fields = editor_form(client, exception_url, approved="1", question_0="My individual question?")
    assert client.post(exception_url, data=fields).status_code == 302
    state = app.extensions["research"]["state"]
    exception = deepcopy(state.settings()["sessions"][0]["participant_questions"]["1"])
    fields = editor_form(client, question_0="Changed shared question?")
    assert client.post(URL, data=fields).status_code == 302
    settings = state.settings()
    assert settings["sessions"][0]["participant_questions"]["1"] == exception
    assert assignment_for(settings, "1", "grade-4-session-1")["question_set"] == exception
    assert assignment_for(settings, "2", "grade-4-session-1")["question_set"]["questions"][0]["question"] == "Changed shared question?"


def test_concurrent_worker_save_is_rejected_atomically_and_retains_draft(app, monkeypatch):
    client = app.test_client()
    login(client)
    configured(app)
    fields = editor_form(client, **custom_fields("Concurrent draft"))
    state = app.extensions["research"]["state"]
    save = state.save_settings
    worker = State(state.path.parent)

    def concurrent_save(value, revision):
        changed = worker.settings()
        changed["current_school_year"] = "2026/2027"
        worker.save_settings(changed, changed["revision"])
        return save(value, revision)

    monkeypatch.setattr(state, "save_settings", concurrent_save)
    response = client.post(URL, data=fields)
    assert response.status_code == 400 and "Another researcher updated the settings" in response.text
    assert EditorFields(response).fields["question_2"] == "Concurrent draft question 3?"
    latest = worker.settings()
    assert latest["current_school_year"] == "2026/2027"
    assert "question_set" not in latest["sessions"][0]


def test_new_route_requires_research_login_and_csrf_for_every_action(app):
    client = app.test_client()
    before = app.extensions["research"]["state"].settings()
    assert client.get(URL).status_code == 302
    assert client.post(URL, data={"action": "save_questions"}).status_code == 302
    login(client)
    for action in ("save_questions", "load_set", "load_questions", "remove_exception"):
        response = client.post(URL + "?participant=1", data={"action": action,
                               "revision": before["revision"], **custom_fields()})
        assert response.status_code == 400
    assert app.extensions["research"]["state"].settings() == before
    response = client.get(URL)
    assert "no-store" in response.headers["Cache-Control"]
    assert "script-src 'none'" in response.headers["Content-Security-Policy"]


@pytest.mark.parametrize("url", [
    "/dashboard/settings/questions/grade-4-session-999",
    URL + "?participant=21", URL + "?participant=999", URL + "?participant=001",
])
def test_unknown_session_or_wrong_grade_participant_is_rejected(app, url):
    client = app.test_client()
    login(client)
    assert client.get(url).status_code == 404
    token = csrf(client.get(URL))
    assert client.post(url, data={"csrf": token, "revision": 1,
                                 "action": "save_questions", **custom_fields()}).status_code == 404


@pytest.mark.parametrize("action, selection", [
    ("load_set", {"library_set": "forged"}),
    ("load_questions", {"library_question_1": "forged:1"}),
])
def test_forged_library_selection_does_not_save(app, action, selection):
    client = app.test_client()
    login(client)
    before = app.extensions["research"]["state"].settings()
    response = client.post(URL, data=editor_form(client, action=action, **selection))
    assert response.status_code == 400
    assert app.extensions["research"]["state"].settings() == before


@pytest.mark.parametrize("change, target", [
    ("tamper", URL),
    ("revision", URL),
    ("none", "/dashboard/settings/questions/grade-4-session-2"),
    ("none", URL + "?participant=1"),
])
def test_draft_token_cannot_be_modified_or_reused_for_another_assignment(app, change, target):
    client = app.test_client()
    login(client)
    before = app.extensions["research"]["state"].settings()
    fields = editor_form(client, **custom_fields())
    assert fields["draft_token"]
    if change == "tamper":
        fields["draft_token"] += "invalid"
    elif change == "revision":
        fields["revision"] = str(int(fields["revision"]) + 1)
    response = client.post(target, data=fields)
    assert response.status_code == 400
    assert app.extensions["research"]["state"].settings() == before


def test_individual_draft_token_is_bound_to_exact_participant(app):
    client = app.test_client()
    login(client)
    before = app.extensions["research"]["state"].settings()
    fields = editor_form(client, URL + "?participant=1", **custom_fields())
    response = client.post(URL + "?participant=2", data=fields)
    assert response.status_code == 400
    assert app.extensions["research"]["state"].settings() == before


def test_editor_round_trips_valid_metadata_larger_than_generic_form_limit(app):
    import random
    import string
    from urllib.parse import urlencode

    client = app.test_client()
    login(client)
    question_set = save_shared(app, client)
    rng = random.Random(14)
    for container in [question_set, *question_set["questions"]]:
        container["metadata"] = {"condition": "".join(rng.choices(string.ascii_letters + string.digits, k=28000))}
    configured(app, question_set=question_set)
    fields = editor_form(client)
    assert len(urlencode(fields).encode()) > 64 * 1024
    assert client.post(URL, data=fields).status_code == 302
    assert shared_set(app) == question_set
    assert client.post("/dashboard/settings", data={**fields, "oversize": "x" * 65536}).status_code == 413
