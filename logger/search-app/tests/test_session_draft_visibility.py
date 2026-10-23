"""Saved question drafts stay discoverable without granting student access."""
from copy import deepcopy
from datetime import datetime, timedelta
from html import unescape
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest
from werkzeug.security import generate_password_hash

from .test_research_dashboard import PASSWORD, app, login
from .test_session_history_snapshot import rendered_context, write_dashboard_snapshot
from .test_session_question_editor import (
    URL, EditorFields, configured, custom_fields, editor_form, save_shared, shared_set, working_set,
)
from .enrollment_helpers import enroll_initial_roster, school_year
from .test_study_enrollment import metadata_files, student_modules
from research_dashboard.state import State
from research_dashboard.study_config import assignment_for, question_library


SESSION_ID = "grade-4-session-1"
SESSION_SETTINGS = "/dashboard/settings?section=sessions&grade=4"
SESSION_OVERVIEW = f"/dashboard?grade=4&session={SESSION_ID}"


def test_incomplete_draft_is_visible_in_session_and_can_be_resumed_without_retyping(app):
    client = app.test_client()
    login(client)
    configured(app)
    fields = editor_form(client, action="save_draft_return", theme="Work in progress",
                         topic_0="Water <&>", question_0="Where does rain come from?",
                         approved="1")
    response = client.post(URL, data=fields)
    assert response.status_code == 302
    redirect = urlsplit(response.location)
    assert redirect.path.rstrip("/") == "/dashboard"
    assert parse_qs(redirect.query)["grade"] == ["4"]
    assert parse_qs(redirect.query)["session"] == [SESSION_ID]
    saved = deepcopy(working_set(app))
    assert saved["approved"] is False

    for path in (SESSION_SETTINGS, response.location):
        page = client.get(path)
        assert page.status_code == 200
        assert "Work in progress" in page.text
        assert "Water &lt;&amp;&gt;" in page.text
        assert "Where does rain come from?" in page.text
        assert page.text.count("Question not written yet") >= 2
        assert "draft" in page.text.lower()
        assert "Continue editing draft" in page.text
        assert f"/dashboard/settings/questions/{SESSION_ID}" in unescape(page.text)

    reopened = EditorFields(client.get(URL)).fields
    assert reopened["theme"] == "Work in progress"
    assert reopened["topic_0"] == "Water <&>"
    assert reopened["question_0"] == "Where does rain come from?"
    assert reopened["topic_1"] == reopened["question_1"] == ""
    assert reopened["topic_2"] == reopened["question_2"] == ""
    assert "approved" not in reopened
    assert working_set(app) == saved


def test_question_editor_exposes_separate_draft_and_approval_actions(app):
    client = app.test_client()
    login(client)
    response = client.get(URL)
    assert 'value="save_draft"' in response.text
    assert 'value="save_draft_return"' in response.text
    assert 'value="approve_questions"' in response.text
    assert "Save draft" in response.text
    assert "Approve questions" in response.text
    assert 'type="checkbox" name="approved"' not in response.text
    assert "approved" not in EditorFields(response).fields


@pytest.mark.parametrize("action", ["save_draft", "save_draft_return"])
def test_draft_save_keeps_approved_questions_available_even_when_form_carries_approval(app, action):
    client = app.test_client()
    login(client)
    configured(app)
    published = deepcopy(save_shared(app, client))
    fields = editor_form(client, action=action, approved="1", question_0="Revised draft?")
    assert client.post(URL, data=fields).status_code == 302
    settings = app.extensions["research"]["state"].settings()
    assert settings["sessions"][0]["question_set"] == published
    assert settings["sessions"][0]["question_draft"]["approved"] is False
    assert settings["sessions"][0]["question_draft"]["questions"][0]["question"] == "Revised draft?"
    assert assignment_for(settings, "1", SESSION_ID)["ready"] is True
    assert assignment_for(settings, "1", SESSION_ID)["question_set"] == published


def test_approval_requires_complete_questions_and_keeps_incomplete_text_for_correction(app):
    client = app.test_client()
    login(client)
    configured(app)
    state = app.extensions["research"]["state"]
    before = state.settings()
    fields = editor_form(client, action="approve_questions", theme="Incomplete session",
                         topic_0="Rain", question_0="How does rain form?")
    response = client.post(URL, data=fields)
    assert response.status_code == 400
    assert "Complete all three topics and questions" in response.text
    retained = EditorFields(response).fields
    assert retained["theme"] == "Incomplete session"
    assert retained["question_0"] == "How does rain form?"
    assert state.settings() == before
    retained.update(action="approve_questions", topic_1="Snow", question_1="How does snow form?",
                    topic_2="Clouds", question_2="How do clouds form?")
    retained.pop("approved", None)
    assert client.post(URL, data=retained).status_code == 302
    assert shared_set(app)["approved"] is True
    assert assignment_for(state.settings(), "1", SESSION_ID)["ready"] is True


def test_library_preview_marks_unsaved_changes_and_can_be_saved_then_resumed(app):
    client = app.test_client()
    login(client)
    configured(app)
    state = app.extensions["research"]["state"]
    before = state.settings()
    historical = question_library(app, before)[0]
    selected = historical["question_set"]["questions"][0]
    response = client.post(URL, data=editor_form(
        client, action="load_questions", theme="Mixed draft", topic_2="My own topic",
        question_2="My question still needs research?", library_question_0=historical["id"] + ":0"))
    assert response.status_code == 200
    assert "Unsaved changes" in response.text
    assert "save" in response.text.lower()
    fields = EditorFields(response).fields
    assert fields["question_0"] == selected["question"]
    assert fields["question_2"] == "My question still needs research?"
    assert fields["theme"] == "Mixed draft"
    assert state.settings() == before

    fields["action"] = "save_draft"
    assert client.post(URL, data=fields).status_code == 302
    assert "My question still needs research?" in client.get(SESSION_OVERVIEW).text
    reopened = EditorFields(client.get(URL)).fields
    assert reopened["question_0"] == selected["question"]
    assert reopened["question_2"] == "My question still needs research?"
    assert reopened["theme"] == "Mixed draft"


def test_individual_draft_reopens_for_exact_participant_and_keeps_shared_assignment(app):
    client = app.test_client()
    login(client)
    configured(app)
    shared = deepcopy(save_shared(app, client))
    own_url = URL + "?participant=1"
    response = client.post(own_url, data=editor_form(
        client, own_url, action="save_draft", theme="Individual work in progress",
        question_0="An individual unfinished question?", approved="1"))
    assert response.status_code == 302
    assert parse_qs(urlsplit(response.location).query)["participant"] == ["1"]
    state = app.extensions["research"]["state"]
    settings = state.settings()
    assert settings["sessions"][0]["question_set"] == shared
    assert "1" not in settings["sessions"][0].get("participant_questions", {})
    assert settings["sessions"][0]["participant_question_drafts"]["1"]["approved"] is False
    # An unapproved individual draft never blocks the child: the class questions stay in use.
    assert assignment_for(settings, "1", SESSION_ID)["ready"] is True
    assert assignment_for(settings, "1", SESSION_ID)["question_set"] == shared
    assert assignment_for(settings, "2", SESSION_ID)["ready"] is True

    for path in (SESSION_SETTINGS, SESSION_OVERVIEW):
        summary = client.get(path)
        assert "Individual assignments" in summary.text
        assert "Continue editing draft" in summary.text
        assert f"{own_url}&" in unescape(summary.text)
    reopened = client.get(own_url)
    fields = EditorFields(reopened).fields
    assert "draft" in reopened.text.lower()
    assert fields["theme"] == "Individual work in progress"
    assert fields["question_0"] == "An individual unfinished question?"
    assert "approved" not in fields
    assert EditorFields(client.get(URL + "?participant=2")).fields["question_0"] == shared["questions"][0]["question"]
    assert not state.settings()["sessions"][1].get("participant_questions")


def test_explicit_draft_save_rejects_stale_revision_and_retains_typed_values(app):
    client = app.test_client()
    login(client)
    configured(app)
    fields = editor_form(client, action="save_draft_return", theme="Unsaved stale draft",
                         question_0="Do not lose this text?")
    state = app.extensions["research"]["state"]
    worker = State(state.path.parent)
    changed = worker.settings()
    changed["current_school_year"] = "2027/2028"
    worker.save_settings(changed, changed["revision"])
    latest = worker.settings()
    response = client.post(URL, data=fields)
    assert response.status_code == 400
    assert "changed in another tab or by another researcher" in response.text
    returned = EditorFields(response).fields
    assert returned["theme"] == "Unsaved stale draft"
    assert returned["question_0"] == "Do not lose this text?"
    assert returned["revision"] == fields["revision"]
    assert state.settings() == latest


def test_current_draft_preview_does_not_replace_recorded_session_labels(app):
    state = app.extensions["research"]["state"]
    settings = state.settings()
    settings["sessions"][0].update(name="Current preparation", date="2026-10-15")
    state.save_settings(settings, settings["revision"])
    snapshot = {"id": SESSION_ID, "grade": "4", "number": 1,
                "name": "Recorded study visit", "date": "2026-10-01", "theme": "", "school_year": ""}
    write_dashboard_snapshot(app, snapshot)
    client = app.test_client()
    login(client)
    fields = editor_form(client, action="save_draft", theme="Next draft",
                         topic_0="Climate", question_0="A current question? ")
    assert client.post(URL, data=fields).status_code == 302
    response, context = rendered_context(app, client, SESSION_OVERVIEW)
    assert context["selected_session"] == snapshot
    assert "Recorded study visit" in response.text
    assert "Climate" in response.text and "A current question?" in response.text
    assert "Continue editing draft" in response.text


def test_future_session_stays_closed_and_today_draft_never_blocks_approved_questions(student_modules, tmp_path):
    module = student_modules()
    module.app.config.update(
        RESEARCH_PASSWORD_HASH=generate_password_hash(PASSWORD, method="pbkdf2:sha256:1000"),
        RESEARCH_PASSWORD_HASH_FILE="")
    state = module.RESEARCH_STATE
    today = datetime.now(ZoneInfo("Europe/Zurich")).date()
    settings = state.settings()
    settings["sessions"][0]["date"] = (today + timedelta(days=1)).isoformat()
    state.save_settings(settings, settings["revision"])
    researcher = module.app.test_client()
    login(researcher)
    fields = editor_form(researcher, action="approve_questions", **custom_fields("Future session", approved=False))
    assert researcher.post(URL, data=fields).status_code == 302
    assert "Future session question 1?" in researcher.get(SESSION_OVERVIEW).text
    student = module.app.test_client()
    response = student.post("/start", data={"user_id": "1"})
    assert response.status_code == 400 and "Session not available" in response.text
    assert "Future session question" not in response.text
    assert not metadata_files(tmp_path)

    settings = state.settings()
    settings["sessions"][0]["date"] = today.isoformat()
    enroll_initial_roster(settings, school_year(today))
    state.save_settings(settings, settings["revision"])
    fields = editor_form(researcher, action="save_draft", approved="1", question_0="Unapproved draft question?")
    assert researcher.post(URL, data=fields).status_code == 302
    assert "Continue editing draft" in researcher.get(SESSION_OVERVIEW).text
    # A working draft never withdraws the approved questions: children can still start
    # today, and they receive the approved text, never the unapproved draft.
    assert student.post("/start", data={"user_id": "1"}).status_code == 302
    task = student.get("/task").text
    assert "Unapproved draft question" not in task
    started = metadata_files(tmp_path)
    assert len(started) == 1
    assert "Unapproved draft question" not in str(started[0])
    assert "Future session question 1?" in str(started[0])


@pytest.mark.parametrize("action", ["save_draft", "save_draft_return", "approve_questions"])
def test_new_explicit_question_actions_require_csrf_and_do_not_change_state(app, action):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    before = state.settings()
    fields = editor_form(client, action=action, **custom_fields())
    fields.pop("csrf")
    assert client.post(URL, data=fields).status_code == 400
    assert state.settings() == before
