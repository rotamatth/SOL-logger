"""A session removed or moved elsewhere never turns an open form into a 404 that drops typed input."""
from .test_enrollment_controls import Controls
from .test_research_dashboard import app, configure, csrf, login  # noqa: F401

YEAR = "2026/2027"
SESSION = "grade-4-session-1"
PREPARE_URL = f"/dashboard/prepare?grade=4&year={YEAR}&session={SESSION}"
EDITOR_URL = f"/dashboard/settings/questions/{SESSION}"
NAME = "Typed but never saved"
TEXT = "A long question typed for ten minutes"


def fields_of(form):
    return {item["name"]: item.get("value", "") for item in form["controls"] if item.get("name")}


def form_with(response, name, value):
    return next(form for form in Controls(response).forms
                if any(item.get("name") == name and item.get("value") == value for item in form["controls"]))


def form_containing(response, control_name):
    return next(form for form in Controls(response).forms
                if any(item.get("name") == control_name for item in form["controls"]))


def review_link(response, text):
    return next(link for link in Controls(response).links if link["text"] == text)


def change_session(state, **values):
    settings = state.settings()
    next(item for item in settings["sessions"] if item["id"] == SESSION).update(values)
    state.save_settings(settings, settings["revision"])
    return state.settings()


def open_client(app):
    configure(app)
    client = app.test_client()
    login(client)
    return client


def test_preparation_details_survive_removal_elsewhere(app):
    client = open_client(app)
    page = client.get(PREPARE_URL)
    details = form_with(page, "action", "save_details")
    values = {**fields_of(details), "name": NAME, "date": "2026-11-20"}
    latest = change_session(app.extensions["research"]["state"], removed=True)

    rejected = client.post(details["attrs"]["action"], data=values)
    assert rejected.status_code == 400
    assert "This session was removed or moved" in rejected.text
    retained = form_with(rejected, "action", "save_details")
    assert fields_of(retained)["name"] == NAME and fields_of(retained)["date"] == "2026-11-20"
    assert "data-unsaved" in retained["attrs"]
    link = review_link(rejected, "Review saved session in a new tab")
    assert link["target"] == "_blank" and "removed=1" in link["href"] and link["href"].endswith("#removed-sessions")
    # Saving again is still refused: the form keeps pointing at the changed session.
    assert client.post(retained["attrs"]["action"], data=fields_of(retained)).status_code == 400
    assert app.extensions["research"]["state"].settings() == latest
    assert client.get(PREPARE_URL).status_code == 404  # A fresh GET of a removed session is still 404.


def test_preparation_details_survive_a_move_to_another_school_year(app):
    client = open_client(app)
    page = client.get(PREPARE_URL)
    details = form_with(page, "action", "save_details")
    latest = change_session(app.extensions["research"]["state"], school_year="2027/2028", date="2027-10-01")

    rejected = client.post(details["attrs"]["action"], data={**fields_of(details), "name": NAME, "date": "2026-11-20"})
    assert rejected.status_code == 400 and NAME in rejected.text
    link = review_link(rejected, "Review saved session in a new tab")
    assert "year=2027/2028" in link["href"] and f"edit={SESSION}" in link["href"]
    assert app.extensions["research"]["state"].settings() == latest


def test_question_text_survives_session_removal_elsewhere(app):
    client = open_client(app)
    page = client.get(EDITOR_URL)
    editor = fields_of(form_containing(page, "draft_token"))
    latest = change_session(app.extensions["research"]["state"], removed=True)

    rejected = client.post(EDITOR_URL, data={**editor, "action": "save_draft", "topic_0": "Topic", "question_0": TEXT})
    assert rejected.status_code == 400
    assert "This session was removed in another tab" in rejected.text and TEXT in rejected.text
    assert "removed=1" in review_link(rejected, "Review saved session in a new tab")["href"]
    assert app.extensions["research"]["state"].settings() == latest
    assert client.get(EDITOR_URL).status_code == 404


def test_individual_question_text_survives_a_class_change_elsewhere(app):
    client = open_client(app)
    url = EDITOR_URL + "?participant=1"
    page = client.get(url)
    editor = fields_of(form_containing(page, "draft_token"))
    state = app.extensions["research"]["state"]
    state.change_participants("update", {"uid": "1", "year": YEAR, "grade": "5", "active": True},
                              state.settings()["revision"])
    latest = state.settings()

    rejected = client.post(url, data={**editor, "action": "save_draft", "topic_0": "Topic", "question_0": TEXT})
    assert rejected.status_code == 400
    assert "no longer enrolled in this session" in rejected.text and TEXT in rejected.text
    link = review_link(rejected, "Review the enrollment in a new tab")
    assert "/dashboard/settings/enrollment" in link["href"] and "q=1" in link["href"]
    assert state.settings() == latest


def test_ids_typed_in_preparation_survive_session_removal_elsewhere(app):
    client = open_client(app)
    page = client.get(PREPARE_URL)
    add = next(form for form in Controls(page).forms if "/settings/enrollment" in form["attrs"].get("action", ""))
    state = app.extensions["research"]["state"]
    latest = change_session(state, removed=True)

    rejected = client.post(add["attrs"]["action"], data={**fields_of(add), "ids": "41, 42", "operation": "add"})
    assert rejected.status_code == 400
    assert "This session was removed or moved" in rejected.text and "41, 42" in rejected.text
    assert "Review saved session in a new tab" in rejected.text
    assert state.settings() == latest and "41" not in latest["participant_registry"]


def test_after_a_stale_session_edit_other_forms_on_the_page_save_normally(app):
    client = open_client(app)
    url = f"/dashboard/settings?section=sessions&grade=4&year={YEAR}"
    page = client.get(url)
    first = form_with(page, "session_id", SESSION)
    stale = fields_of(first)
    state = app.extensions["research"]["state"]
    settings = state.settings()
    next(item for item in settings["sessions"] if item["id"] == "grade-4-session-3")["name"] = "Saved elsewhere"
    state.save_settings(settings, settings["revision"])
    current = state.settings()["revision"]

    rejected = client.post(first["attrs"]["action"], data={**stale, "name": NAME})
    assert rejected.status_code == 400 and "changed in another tab or by another researcher" in rejected.text
    forms = [form for form in Controls(rejected).forms
             if fields_of(form).get("action") == "save_session"]
    by_session = {fields_of(form)["session_id"]: form for form in forms}
    assert fields_of(by_session[SESSION])["revision"] == stale["revision"]  # the rejected form stays stale
    other = by_session["grade-4-session-2"]
    assert fields_of(other)["revision"] == str(current)
    saved = client.post(other["attrs"]["action"], data={**fields_of(other), "name": "Second visit"})
    assert saved.status_code == 302
    assert next(item for item in state.settings()["sessions"] if item["id"] == "grade-4-session-2")["name"] == "Second visit"
