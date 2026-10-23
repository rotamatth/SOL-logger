"""Recovered editor text keeps a reused set's question IDs and conditions when that is safe."""
from html import unescape
import re

from itsdangerous import URLSafeSerializer

from .test_enrollment_controls import Controls
from .test_research_dashboard import app, configure, login  # noqa: F401

URL = "/dashboard/settings/questions/grade-4-session-1"
TEXT_FIELDS = ("theme", "topic_0", "question_0", "topic_1", "question_1", "topic_2", "question_2")


def editor(response):
    form = next(f for f in Controls(response).forms if any(c.get("name") == "draft_token" for c in f["controls"]))
    fields = {c["name"]: unescape(c.get("value", "")) for c in form["controls"]
              if c.get("name") and c["tag"] == "input"}
    for slot in range(3):
        fields[f"question_{slot}"] = unescape(re.search(rf'name="question_{slot}"[^>]*>(.*?)</textarea>',
                                                        response.text, re.S)[1])
    library = next(c for c in form["controls"] if c.get("name") == "library_set")
    return fields, [option["value"] for option in library["options"] if option.get("value")]


def signed(app, token):
    return URLSafeSerializer(app.config["RESEARCH_PASSWORD_HASH"], salt="sol-question-draft").loads(token)


def session_questions(state):
    return next(s for s in state.settings()["sessions"] if s["id"] == "grade-4-session-1")


def save_elsewhere(state, session_id="grade-5-session-1", **values):
    settings = state.settings()
    next(s for s in settings["sessions"] if s["id"] == session_id).update(values)
    state.save_settings(settings, settings["revision"])


def conflicted_copy(app, client):
    """A reused set loaded in the editor, then a save rejected by a change in another tab."""
    fields, sets = editor(client.get(URL))
    preview, _ = editor(client.post(URL, data={**fields, "action": "load_set", "library_set": sets[0]}))
    loaded = signed(app, preview["draft_token"])["question_set"]
    assert loaded["metadata"] and all(question.get("metadata") for question in loaded["questions"])
    return preview, loaded


def test_reused_set_keeps_conditions_after_an_unrelated_conflict(app):
    configure(app)
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    preview, loaded = conflicted_copy(app, client)
    save_elsewhere(state, name="Unrelated change")
    assert client.post(URL, data={**preview, "action": "approve_questions"}).status_code == 400
    # "Use this text with the current version": text plus the copy's signed structure.
    fresh, _ = editor(client.get(URL))
    restored = {**fresh, **{name: preview[name] for name in TEXT_FIELDS},
                "recovered_draft_token": preview["draft_token"]}
    assert client.post(URL, data={**restored, "action": "approve_questions"}).status_code == 302
    approved = session_questions(state)["question_set"]
    assert approved["metadata"] == loaded["metadata"]
    assert [q["id"] for q in approved["questions"]] == [q["id"] for q in loaded["questions"]]
    assert [q["metadata"] for q in approved["questions"]] == [q["metadata"] for q in loaded["questions"]]
    assert approved["approved"] is True


def test_structure_is_refused_when_this_sessions_questions_changed_meanwhile(app):
    configure(app)
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    preview, _ = conflicted_copy(app, client)
    other = {"approved": False, "theme": "Other tab", "questions": [
        {"id": "other-1", "topic": "Other topic", "question": "Saved in another tab?"}]}
    save_elsewhere(state, session_id="grade-4-session-1", question_draft=other)
    latest = state.settings()
    fresh, _ = editor(client.get(URL))
    restored = {**fresh, **{name: preview[name] for name in TEXT_FIELDS},
                "recovered_draft_token": preview["draft_token"]}
    refused = client.post(URL, data={**restored, "action": "approve_questions"})
    assert refused.status_code == 400 and "after your copy was made" in refused.text
    assert state.settings() == latest
    again, _ = editor(refused)
    assert again["recovered_draft_token"] == ""  # A second save keeps only the text, as the message says.
    assert again["question_0"] == preview["question_0"]
    assert client.post(URL, data={**again, "action": "save_draft"}).status_code == 302
    draft = session_questions(state)["question_draft"]
    assert draft["questions"][0]["question"] == preview["question_0"]


def test_recovered_structure_from_another_editor_or_unsigned_is_rejected(app):
    configure(app)
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    fields, _ = editor(client.get(URL))
    foreign, _ = editor(client.get("/dashboard/settings/questions/grade-4-session-2"))
    before = state.settings()
    for token in (foreign["draft_token"], "unsigned-token"):
        response = client.post(URL, data={**fields, "question_0": "Text", "recovered_draft_token": token,
                                          "action": "save_draft"})
        assert response.status_code == 400
    assert state.settings() == before
