"""School-year controls keep session administration and preparation in scope."""
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from .test_dashboard_filters import rendered_context
from .test_enrollment_controls import Controls
from .test_permanent_participants import change
from .test_research_dashboard import app, configure, csrf, login
from research_dashboard.year_controls import school_year_choices

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


@pytest.mark.parametrize("day,expected", [("2026-08-31", "2025/2026"), ("2027-09-01", FUTURE)])
def test_preparation_files_a_session_under_its_dates_school_year(app, day, expected):
    """The year is never typed: a date outside the open year creates the session in its own year."""
    configure(app)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    path = f"/dashboard/prepare?grade=4&year={YEAR}&new=1"
    page = client.get(path)
    control = next(control for form in Controls(page).forms for control in form["controls"]
                   if control.get("id") == "prepare-date")
    assert "min" not in control and "max" not in control
    created = client.post(path, data={"action": "save_details", "date": day, "name": "Other year",
                                      "revision": state.settings()["revision"], "csrf": csrf(page)})
    assert created.status_code == 302
    query = parse_qs(urlsplit(created.location).query)
    assert query["year"] == [expected]
    saved = next(item for item in state.settings()["sessions"] if item["id"] == query["session"][0])
    assert (saved["date"], saved["school_year"]) == (day, expected)
    shown = client.get(created.location)
    assert shown.status_code == 200
    # Nobody is enrolled there yet. Only a later year points to the yearly promotion step.
    assert "No IDs are enrolled in this class and school year yet" in shown.text
    assert ("No children are enrolled in this class for this school year yet" in shown.text) == (expected == FUTURE)


def test_moving_a_session_date_moves_its_year_unless_it_has_records(app):
    configure(app)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    path = f"/dashboard/prepare?grade=4&year={YEAR}&session={SESSION}"
    page = client.get(path)
    moved = client.post(path, data={"action": "save_details", "date": "2027-10-01", "name": "",
                                    "revision": state.settings()["revision"], "csrf": csrf(page)})
    assert moved.status_code == 302 and parse_qs(urlsplit(moved.location).query)["year"] == [FUTURE]
    assert next(item for item in state.settings()["sessions"] if item["id"] == SESSION)["school_year"] == FUTURE
    settings = state.settings()
    next(item for item in settings["sessions"] if item["id"] == SESSION).update(date="2026-10-01", school_year=YEAR)
    state.save_settings(settings, settings["revision"])
    with state.connect() as db:
        db.execute("INSERT INTO study_attempts VALUES ('attempt-1', ?, '1', '{}', 1)", (SESSION,))
    page = client.get(path)
    before = state.settings()
    refused = client.post(path, data={"action": "save_details", "date": "2027-10-01", "name": "",
                                      "revision": before["revision"], "csrf": csrf(page)})
    assert refused.status_code == 400 and state.settings() == before


def test_year_menu_and_session_forms_need_no_typed_year(app):
    configure(app)
    state = app.extensions["research"]["state"]
    add_future(state)
    client = app.test_client()
    login(client)
    page = client.get(f"/dashboard/prepare?grade=4&year={YEAR}&session={SESSION}")
    assert "Open year" not in page.text and 'list="prepare-year-choices"' not in page.text
    years = [control.get("value") for form in Controls(page).forms for control in form["controls"]
             if control.get("name") == "select_year"]
    assert years == [FUTURE, YEAR]
    switched = client.get(f"/dashboard/prepare?grade=4&year={YEAR}&select_year={FUTURE}&context_selection=1")
    assert switched.status_code == 200 and "Future visit" in switched.text
    administration = client.get(URL + f"&year={YEAR}&new=1")
    assert 'name="school_year"' not in administration.text
    created = client.post(URL + f"&year={YEAR}", data={
        "action": "add_session", "grade": "4", "date": "2027-11-02", "name": "Derived", "school_year": YEAR,
        "csrf": csrf(administration), "revision": state.settings()["revision"]})
    assert created.status_code == 302
    derived = next(item for item in state.settings()["sessions"] if item.get("name") == "Derived")
    assert derived["school_year"] == FUTURE


def test_new_future_year_can_be_entered_and_created_session_is_visible(app):
    configure(app)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    path = f"/dashboard/prepare?grade=4&year={FUTURE}&new=1"
    page = client.get(path)
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
    assert 'list="new-year-choices"' not in page.text and 'id="new-date-year"' in page.text
    assert 'list="year_' + session_id + '-choices"' not in page.text and f'id="year_{session_id}"' in page.text


@pytest.mark.parametrize("year", ["2026/2028", "invalid"])
def test_invalid_administration_year_scope_is_rejected(app, year):
    configure(app)
    client = app.test_client()
    login(client)
    assert client.get(URL + "&year=" + year).status_code == 404
