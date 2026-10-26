"""School-year controls keep session administration and preparation in scope."""
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from .test_dashboard_filters import rendered_context
from .test_enrollment_controls import Controls
from .test_permanent_participants import change
from .test_research_dashboard import app, configure, csrf, login
from research_dashboard.year_controls import school_year_bounds, school_year_choices

YEAR = "2026/2027"
FUTURE = "2027/2028"
SESSION = "grade-4-session-1"
URL = "/dashboard/settings?section=sessions&grade=4"


def context_for(app, client, url):
    with rendered_context(app) as contexts:
        response = client.get(url)
    assert response.status_code == 200
    return response, contexts[-1]


def add_future(state):
    return state.add_study_session("4", "2027-10-01", state.settings()["revision"],
                                   "Future visit", school_year=FUTURE)


def test_year_choices_keep_removed_sessions_and_old_enrollment_after_promotion(app):
    configure(app)
    state = app.extensions["research"]["state"]
    add_future(state)
    change(state, "promote", source_year=YEAR, target_year=FUTURE)
    settings = state.settings()
    settings["sessions"][0]["removed"] = True
    state.save_settings(settings, settings["revision"])
    assert school_year_choices(state.settings()) == [FUTURE, YEAR]
    assert school_year_bounds(YEAR) == {"min": "2026-09-01", "max": "2027-08-31"}
    assert school_year_bounds("2026/2028") is None


def test_administration_defaults_to_current_year_and_explicit_all_years_survives_navigation(app):
    configure(app)
    state = app.extensions["research"]["state"]
    future = add_future(state)
    client = app.test_client()
    login(client)
    before = state.settings()
    _, current = context_for(app, client, URL)
    assert current["history_year"] == YEAR
    assert future["id"] not in {item["id"] for item in current["history_sessions"]}
    page, all_years = context_for(app, client, URL + "&year=")
    assert all_years["history_year"] == ""
    assert future["id"] in {item["id"] for item in all_years["history_sessions"]}
    select = next(control for form in Controls(page).forms for control in form["controls"]
                  if control.get("id") == "settings-session-year")
    assert {option.get("value") for option in select["options"]} == {"", YEAR, FUTURE}
    for label in ("3rd Grade", "5th Grade", "School year", "Sessions"):
        matches = [link for link in Controls(page).links if link["text"] == label]
        assert matches, label
        for link in matches:
            query = parse_qs(urlsplit(link["href"]).query, keep_blank_values=True)
            assert query.get("year") == [""], link
    assert state.settings() == before


def test_selected_old_session_remains_available_after_promotion(app):
    configure(app)
    state = app.extensions["research"]["state"]
    add_future(state)
    change(state, "promote", source_year=YEAR, target_year=FUTURE)
    client = app.test_client()
    login(client)
    page, context = context_for(app, client, URL + f"&session={SESSION}")
    assert context["history_year"] == YEAR
    assert context["study_context"]["id"] == SESSION
    assert SESSION in {item["id"] for item in context["history_sessions"]}
    assert 'value="2026/2027"' in page.text
    explicit_future, context = context_for(app, client, URL + f"&year={FUTURE}&session={SESSION}")
    assert context["study_context"]["id"] is None
    assert SESSION not in {item["id"] for item in context["history_sessions"]}


def test_year_scope_preserves_pagination_save_and_restored_session_visibility(app):
    configure(app)
    state = app.extensions["research"]["state"]
    settings = state.settings()
    for number in range(4, 16):
        settings["sessions"].append({"id": f"grade-4-session-{number}", "grade": "4", "number": number,
                                     "date": (date(2026, 11, 1) + timedelta(days=number)).isoformat(),
                                     "school_year": YEAR, "removed": number == 4})
    state.save_settings(settings, settings["revision"])
    add_future(state)
    client = app.test_client()
    login(client)
    page, context = context_for(app, client, URL + f"&year={YEAR}&page=2")
    assert len(context["history_sessions"]) == 4
    assert all(item["school_year"] == YEAR for item in context["history_sessions"])
    pagination = [link for link in Controls(page).links if "#session-history" in link["href"]]
    assert pagination and all(parse_qs(urlsplit(link["href"]).query)["year"] == [YEAR]
                              for link in pagination)
    saved = client.post(URL + f"&year={YEAR}&page=2", data={"action": "save_session", "session_id": SESSION,
                        "school_year": YEAR, "date": "2026-10-01", "name": "First visit",
                        "csrf": csrf(page), "revision": state.settings()["revision"]})
    assert saved.status_code == 302
    assert parse_qs(urlsplit(saved.location).query)["year"] == [YEAR]
    assert parse_qs(urlsplit(saved.location).query)["page"] == ["2"]
    restored = client.post(URL + f"&year={YEAR}", data={"action": "restore_session",
                           "session_id": "grade-4-session-4", "csrf": csrf(page),
                           "revision": state.settings()["revision"]})
    assert restored.status_code == 302
    restored_page, restored_context = context_for(app, client, restored.location)
    assert restored_context["history_page"] == 2
    assert 'id="grade-4-session-4" open' in restored_page.text


def test_saving_a_session_into_another_year_opens_its_new_scope(app):
    configure(app)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    page = client.get(URL + f"&year={YEAR}")
    response = client.post(URL + f"&year={YEAR}", data={"action": "save_session", "session_id": SESSION,
                           "school_year": FUTURE, "date": "2027-10-01", "name": "Next year",
                           "csrf": csrf(page), "revision": state.settings()["revision"]})
    assert response.status_code == 302
    assert parse_qs(urlsplit(response.location).query)["year"] == [FUTURE]
    shown, context = context_for(app, client, response.location)
    assert 'id="grade-4-session-1" open' in shown.text
    assert [item["id"] for item in context["history_sessions"]] == [SESSION]


@pytest.mark.parametrize("day", ["2026-08-31", "2027-09-01"])
def test_preparation_date_limits_match_server_validation(app, day):
    configure(app)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    path = f"/dashboard/prepare?grade=4&year={YEAR}&new=1"
    page = client.get(path)
    control = next(control for form in Controls(page).forms for control in form["controls"]
                   if control.get("id") == "prepare-date")
    assert (control["min"], control["max"]) == ("2026-09-01", "2027-08-31")
    before = state.settings()
    rejected = client.post(path, data={"action": "save_details", "date": day, "name": "Wrong year",
                                      "revision": before["revision"], "csrf": csrf(page)})
    assert rejected.status_code == 400 and "between September and August" in rejected.text
    assert state.settings() == before


def test_new_future_year_can_be_entered_and_created_session_is_visible(app):
    configure(app)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    path = f"/dashboard/prepare?grade=4&year={FUTURE}&new=1"
    page = client.get(path)
    assert 'list="prepare-year-choices"' in page.text
    created = client.post(path, data={"action": "save_details", "date": "2027-10-01", "name": "Next year",
                                     "revision": state.settings()["revision"], "csrf": csrf(page)})
    assert created.status_code == 302
    session_id = parse_qs(urlsplit(created.location).query)["session"][0]
    page = client.get(created.location)
    administration = next(link for link in Controls(page).links if link["text"] == "All sessions and session administration")
    assert parse_qs(urlsplit(administration["href"]).query)["year"] == [FUTURE]
    page, context = context_for(app, client, administration["href"])
    assert context["history_year"] == FUTURE
    assert [item["id"] for item in context["history_sessions"]] == [session_id]
    assert 'list="new-year-choices"' in page.text
    assert 'list="year_' + session_id + '-choices"' in page.text


@pytest.mark.parametrize("year", ["2026/2028", "invalid"])
def test_invalid_administration_year_scope_is_rejected(app, year):
    configure(app)
    client = app.test_client()
    login(client)
    assert client.get(URL + "&year=" + year).status_code == 404
