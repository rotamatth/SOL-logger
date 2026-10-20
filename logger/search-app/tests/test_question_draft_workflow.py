"""Draft/approved question lifecycle and private editor recovery through the routes."""
from copy import deepcopy
import json

from .test_research_dashboard import app, login  # noqa: F401 - pytest fixture
from .test_session_question_editor import (
    URL, EditorFields, configured, editor_form, save_shared, working_set,
)
from research_dashboard import editor_views
from research_dashboard.participants import audit_rows
from research_dashboard.study_config import assignment_for


SESSION_ID = "grade-4-session-1"
RECOVERY = "/dashboard/editor/recovery"
KEY = f"questions:{SESSION_ID}:"
PREP = f"/dashboard/prepare?grade=4&year=2026/2027&session={SESSION_ID}"


def session(app):
    return app.extensions["research"]["state"].settings()["sessions"][0]


def test_approving_a_draft_replaces_published_questions_and_clears_the_draft(app):
    client = app.test_client()
    login(client)
    configured(app)
    save_shared(app, client)
    fields = editor_form(client, action="save_draft", question_0="Replacement question?")
    assert client.post(URL, data=fields).status_code == 302
    assert session(app)["question_set"]["questions"][0]["question"] != "Replacement question?"
    fields = editor_form(client, action="approve_questions")
    assert fields["question_0"] == "Replacement question?"
    assert client.post(URL, data=fields).status_code == 302
    saved = session(app)
    assert "question_draft" not in saved
    assert saved["question_set"]["approved"] is True
    assert saved["question_set"]["questions"][0]["question"] == "Replacement question?"


def test_discarding_a_draft_keeps_published_questions_and_requires_csrf(app):
    client = app.test_client()
    login(client)
    configured(app)
    published = deepcopy(save_shared(app, client))
    assert client.post(URL, data=editor_form(client, action="save_draft", question_1="Abandoned?")).status_code == 302
    page = client.get(URL)
    assert 'value="discard_draft"' in page.text and "Working draft" in page.text
    fields = editor_form(client, action="discard_draft")
    without_token = dict(fields)
    without_token.pop("csrf")
    assert client.post(URL, data=without_token).status_code == 400
    assert "question_draft" in session(app)
    response = client.post(URL, data=fields)
    assert response.status_code == 302 and "discarded=1" in response.location
    assert "question_draft" not in session(app)
    assert session(app)["question_set"] == published
    reopened = EditorFields(client.get(URL)).fields
    assert reopened["question_1"] == published["questions"][1]["question"]
    assert 'value="discard_draft"' not in client.get(URL).text


def test_preparation_lists_approved_questions_and_the_draft_separately(app):
    client = app.test_client()
    login(client)
    configured(app)
    save_shared(app, client)
    client.post(URL, data=editor_form(client, action="save_draft", question_2="Draft-only wording?"))
    page = client.get(PREP).text
    approved_at = page.index("Fresh V2 question 3?")
    draft_at = page.index("Draft-only wording?")
    assert approved_at < page.index("Unpublished draft") < draft_at
    assert "Students continue to use the approved questions" in page


def test_individual_draft_approval_and_removal_round_trip(app):
    client = app.test_client()
    login(client)
    configured(app)
    shared = deepcopy(save_shared(app, client))
    own = URL + "?participant=1"
    client.post(own, data=editor_form(client, own, action="save_draft", question_0="Only for child 1?"))
    settings = app.extensions["research"]["state"].settings()
    assert assignment_for(settings, "1", SESSION_ID)["question_set"] == shared
    assert client.post(own, data=editor_form(client, own, action="approve_questions")).status_code == 302
    settings = app.extensions["research"]["state"].settings()
    assert assignment_for(settings, "1", SESSION_ID)["question_set"]["questions"][0]["question"] == "Only for child 1?"
    assert "participant_question_drafts" not in settings["sessions"][0]
    assert client.post(own, data=editor_form(client, own, action="remove_exception")).status_code == 302
    settings = app.extensions["research"]["state"].settings()
    assert assignment_for(settings, "1", SESSION_ID)["question_set"] == shared


def test_editor_page_loads_protection_script_under_a_strict_policy(app):
    client = app.test_client()
    login(client)
    configured(app)
    page = client.get(URL)
    assert 'src="/dashboard/static/editor.js"' in page.text
    assert f'data-recovery-key="{KEY}"' in page.text
    assert "<script>" not in page.text
    policy = page.headers["Content-Security-Policy"]
    assert "script-src 'self'" in policy and "unsafe-inline" not in policy
    script = client.get("/dashboard/static/editor.js")
    assert script.status_code == 200 and "javascript" in script.mimetype


def test_recovery_requires_login_and_csrf_and_never_changes_settings(app):
    client = app.test_client()
    state = app.extensions["research"]["state"]
    before = state.settings()
    expired = client.get(RECOVERY + "?key=" + KEY)
    assert expired.status_code == 401 and expired.get_json() == {"error": "login"}
    login(client)
    first = client.get(RECOVERY + "?key=" + KEY).get_json()
    assert first["recovery"] is None and first["csrf"]
    fields = json.dumps({"question_0": "Typed but not saved", "revision": str(before["revision"])})
    assert client.post(RECOVERY, data={"key": KEY, "sequence": "0", "fields": fields}).status_code == 400
    saved = client.post(RECOVERY, data={"csrf": first["csrf"], "key": KEY, "sequence": "0", "fields": fields})
    assert saved.status_code == 200
    record = client.get(RECOVERY + "?key=" + KEY).get_json()["recovery"]
    assert record["fields"]["question_0"] == "Typed but not saved"
    assert state.settings() == before
    stale = client.post(RECOVERY, data={"csrf": first["csrf"], "key": KEY, "sequence": "0", "fields": fields})
    assert stale.status_code == 409


def test_successful_save_clears_the_matching_recovery_copy(app):
    client = app.test_client()
    login(client)
    configured(app)
    token = client.get(RECOVERY + "?key=" + KEY).get_json()["csrf"]
    fields = json.dumps({"question_0": "Protected text"})
    record = client.post(RECOVERY, data={"csrf": token, "key": KEY, "sequence": "0", "fields": fields}).get_json()["recovery"]
    form = editor_form(client, action="save_draft", question_0="Protected text",
                       recovery_sequence=str(record["sequence"]))
    assert client.post(URL, data=form).status_code == 302
    assert working_set(app)["questions"][0]["question"] == "Protected text"
    cleared = client.get(RECOVERY + "?key=" + KEY).get_json()["recovery"]
    assert cleared["fields"] is None


def test_logout_removes_private_recovery_copies(app):
    client = app.test_client()
    login(client)
    token = client.get(RECOVERY + "?key=" + KEY).get_json()["csrf"]
    client.post(RECOVERY, data={"csrf": token, "key": KEY, "sequence": "0",
                                "fields": json.dumps({"question_0": "Private"})})
    client.post("/dashboard/logout", data={"csrf": token})
    login(client)
    assert client.get(RECOVERY + "?key=" + KEY).get_json()["recovery"] is None


def test_validation_error_page_is_marked_unsaved_for_immediate_protection(app):
    client = app.test_client()
    login(client)
    configured(app)
    response = client.post(URL, data=editor_form(client, action="approve_questions", question_0="Only one?"))
    assert response.status_code == 400
    assert "data-unsaved" in response.text
    assert EditorFields(response).fields["question_0"] == "Only one?"


def test_a_broken_recovery_store_never_undoes_a_successful_save(app, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("Editor recovery database has an invalid schema")

    client = app.test_client()
    login(client)
    configured(app)
    monkeypatch.setattr(editor_views.EditorRecovery, "clear", broken)
    form = editor_form(client, action="save_draft", question_0="Still saved?", recovery_sequence="1")
    assert client.post(URL, data=form).status_code == 302
    assert working_set(app)["questions"][0]["question"] == "Still saved?"


def test_change_history_lists_affected_ids_with_before_and_after_values(app):
    assert audit_rows("add", {"ids": ["41"], "grade": "4"}) == [
        {"id": "41", "before": [("new", None)], "after": [("grade", "4")]}]
    assert audit_rows("enroll", {"changes": [{"id": "7", "before_grade": None, "grade": "5"}]}) == [
        {"id": "7", "before": [("none", None)], "after": [("grade", "5")]}]
    assert audit_rows("update", {"id": "3", "before": {"active": True, "grade": "4"},
                                 "after": {"active": False, "grade": "4"}}) == [
        {"id": "3", "before": [("grade", "4"), ("status", True)], "after": [("grade", "4"), ("status", False)]}]
    assert audit_rows("promote", {"participants": [{"id": "1", "from_grade": "5", "to_grade": None}]}) == [
        {"id": "1", "before": [("grade", "5")], "after": [("none", None)]}]
    assert audit_rows("unknown", {"ids": ["1"]}) == [] and audit_rows("update", {"broken": True}) == []
    client = app.test_client()
    login(client)
    configured(app)
    page = client.get("/dashboard/settings/enrollment?lang=en&grade=4&year=2026/2027")
    assert 'class="audit-table"' in page.text and "<th scope=\"row\">1</th>" in page.text
