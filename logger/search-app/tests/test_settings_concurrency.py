"""Rejected session edits survive concurrent year, removal and other-tab changes."""
import pytest

from .test_enrollment_controls import Controls
from .test_research_dashboard import app, configure, csrf, login  # noqa: F401

YEAR = "2026/2027"
FUTURE = "2027/2028"
SESSION = "grade-4-session-1"
URL = f"/dashboard/prepare?grade=4&year={YEAR}&session={SESSION}"
NAME = 'Unsaved <class> & "visit"'


def concurrent_change(state, change):
    settings = state.settings()
    if change == "remove_other":
        next(item for item in settings["sessions"] if item["id"] == "grade-4-session-3")["removed"] = True
    else:
        target = next(item for item in settings["sessions"] if item["id"] == SESSION)
        if change == "move_edited":
            target.update(school_year=FUTURE, date="2027-10-01", name="Other tab's saved visit")
        else:
            target["removed"] = True
    state.save_settings(settings, settings["revision"])


def session_form(response, action="save_details"):
    matches = []
    for form in Controls(response).forms:
        fields = {item["name"]: item.get("value", "") for item in form["controls"] if item.get("name")}
        if fields.get("action") == action and fields.get("session_id", SESSION) == SESSION:
            matches.append((form["attrs"], fields))
    assert len(matches) == 1, matches
    return matches[0]


@pytest.mark.parametrize("change,message,link_text", [
    ("remove_other", "changed in another tab or by another researcher", "Reload saved settings"),
    ("move_edited", "This session was removed or moved", "Review saved session in a new tab"),
    ("remove_edited", "This session was removed or moved", "Review saved session in a new tab"),
])
def test_stale_edit_keeps_fields_and_can_be_reapplied_after_review(app, change, message, link_text):
    configure(app)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    page = client.get(URL)
    assert page.status_code == 200
    attrs, fields = session_form(page)
    fields.update(name=NAME, date="2026-10-12")
    concurrent_change(state, change)
    latest = state.settings()

    rejected = client.post(attrs["action"], data=fields)
    assert rejected.status_code == 400
    attrs, retained = session_form(rejected)
    assert "data-unsaved" in attrs
    assert {key: retained[key] for key in ("name", "date", "revision")} == {
        key: fields[key] for key in ("name", "date", "revision")}
    assert "school_year" not in retained  # The year follows from the date.
    assert message in rejected.text
    assert state.settings() == latest
    assert client.post(attrs["action"], data=retained).status_code == 400
    assert state.settings() == latest  # A second click cannot bypass the revision check.

    review = next(link for link in Controls(rejected).links if link["text"] == link_text)
    saved = client.get(review["href"])
    assert saved.status_code == 200
    if change == "remove_edited":
        assert review["target"] == "_blank" and "noopener" in review["rel"]
        restore_attrs, restore_fields = session_form(saved, "restore_session")
        restored = client.post(restore_attrs["action"], data=restore_fields)
        assert restored.status_code == 302
        saved = client.get(URL)
    fresh_attrs, fresh = session_form(saved)
    assert fresh["revision"] != retained["revision"]
    assert fresh["name"] != NAME
    fresh["name"] = retained["name"]  # Explicitly copy the intended edit after review.
    fresh["date"] = "2027-10-12" if change == "move_edited" else retained["date"]
    accepted = client.post(fresh_attrs["action"], data=fresh)
    assert accepted.status_code == 302
    target = next(item for item in state.settings()["sessions"] if item["id"] == SESSION)
    assert target["name"] == NAME and target["date"] == fresh["date"]
    assert target["school_year"] == (FUTURE if change == "move_edited" else YEAR)
    assert not target.get("removed")


def test_stale_create_keeps_the_new_session_fields(app):
    configure(app)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    page = client.get("/dashboard/sessions/new")
    revision = state.settings()["revision"]
    concurrent_change(state, "remove_other")
    latest = state.settings()
    response = client.post("/dashboard/sessions/new", data={
        "grade": "5", "revision": revision, "csrf": csrf(page), "date": "2026-12-01", "name": NAME,
    })
    assert response.status_code == 400
    form = next(form for form in Controls(response).forms
                if any(item.get("name") == "date" for item in form["controls"]))
    assert "data-unsaved" in form["attrs"]
    values = {item.get("name"): item.get("value") for item in form["controls"]}
    assert values["name"] == NAME and values["date"] == "2026-12-01"
    assert "school_year" not in values and values["revision"] == str(revision)
    assert state.settings() == latest
