"""Rejected session edits survive concurrent pagination, year and removal changes."""
from datetime import date, timedelta

import pytest

from .test_enrollment_controls import Controls
from .test_research_dashboard import app, configure, csrf, login  # noqa: F401

YEAR = "2026/2027"
FUTURE = "2027/2028"
SESSION = "grade-4-session-1"
URL = f"/dashboard/settings?section=sessions&grade=4&year={YEAR}&page=2"
NAME = 'Unsaved <class> & "visit"'


def eleven_sessions(app):
    configure(app)
    state = app.extensions["research"]["state"]
    settings = state.settings()
    for number in range(4, 12):
        settings["sessions"].append({
            "id": f"grade-4-session-{number}", "grade": "4", "number": number,
            "school_year": YEAR, "date": (date(2026, 11, 1) + timedelta(days=number)).isoformat(),
        })
    state.save_settings(settings, settings["revision"])
    return state


def concurrent_change(state, change):
    settings = state.settings()
    if change == "remove_other":
        settings["sessions"][-1]["removed"] = True
    else:
        target = next(item for item in settings["sessions"] if item["id"] == SESSION)
        if change == "move_edited":
            target.update(school_year=FUTURE, date="2027-10-01", name="Other tab's saved visit")
        else:
            target["removed"] = True
    state.save_settings(settings, settings["revision"])


def session_form(response, action="save_session"):
    matches = []
    for form in Controls(response).forms:
        fields = {item["name"]: item.get("value", "") for item in form["controls"] if item.get("name")}
        if fields.get("session_id") == SESSION and fields.get("action") == action:
            matches.append((form["attrs"], fields))
    assert len(matches) == 1, matches
    return matches[0]


@pytest.mark.parametrize("change", ["remove_other", "move_edited", "remove_edited"])
def test_stale_edit_keeps_fields_and_can_be_reapplied_after_review(app, change):
    state = eleven_sessions(app)
    client = app.test_client()
    login(client)
    page = client.get(URL)
    assert page.status_code == 200
    _, fields = session_form(page)
    fields.update(name=NAME, date="2026-10-12", school_year=YEAR)
    concurrent_change(state, change)
    latest = state.settings()

    rejected = client.post(URL, data=fields)
    assert rejected.status_code == 400
    attrs, retained = session_form(rejected)
    assert "data-unsaved" in attrs
    assert {key: retained[key] for key in ("name", "date", "school_year", "revision")} == {
        key: fields[key] for key in ("name", "date", "school_year", "revision")}
    assert "Another researcher updated the settings" in rejected.text
    assert state.settings() == latest
    assert client.get(URL).status_code == 404  # Invalid GET pages still fail.
    assert client.post(attrs["action"], data=retained).status_code == 400
    assert state.settings() == latest  # A second click cannot bypass the revision check.

    review = next(link for link in Controls(rejected).links
                  if link["text"] == "Review saved session in a new tab")
    assert review["target"] == "_blank" and "noopener" in review["rel"]
    saved = client.get(review["href"])
    assert saved.status_code == 200
    if change == "remove_edited":
        restore_attrs, restore_fields = session_form(saved, "restore_session")
        restored = client.post(restore_attrs["action"], data=restore_fields)
        assert restored.status_code == 302
        saved = client.get(restored.location)
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


def test_stale_add_on_disappearing_page_keeps_new_session_fields(app):
    state = eleven_sessions(app)
    client = app.test_client()
    login(client)
    page = client.get(URL)
    revision = state.settings()["revision"]
    concurrent_change(state, "remove_other")
    latest = state.settings()
    response = client.post(URL, data={
        "action": "add_session", "grade": "4", "revision": revision, "csrf": csrf(page),
        "school_year": YEAR, "date": "2026-12-01", "name": NAME,
    })
    assert response.status_code == 400
    fields = next(form for form in Controls(response).forms
                  if any(item.get("value") == "add_session" for item in form["controls"]))
    assert "data-unsaved" in fields["attrs"]
    values = {item.get("name"): item.get("value") for item in fields["controls"]}
    assert values["name"] == NAME and values["date"] == "2026-12-01"
    assert values["school_year"] == YEAR and values["revision"] == str(revision)
    assert state.settings() == latest
