"""The session list: status groups, what a draft still needs, and creating a session."""
from urllib.parse import parse_qs, urlsplit

import pytest

from .test_dashboard_filters import rendered_context
from .test_enrollment_controls import Controls
from .test_research_dashboard import app, configure, create_session, csrf, login  # noqa: F401
from .test_study_enrollment import question_set
from research_dashboard.preparation_views import is_placeholder, session_group, session_needs
from research_dashboard.study_config import session_readiness

YEAR = "2026/2027"
TODAY = "2026-11-05"
READY = {"count": 20, "ready": 20, "complete": True}
PARTLY = {"count": 20, "ready": 5, "complete": False}
NONE = {"count": 20, "ready": 0, "complete": False}


@pytest.mark.parametrize("study_date,school_year,readiness,expected", [
    ("", "", NONE, "draft"),
    ("2026-11-20", "", READY, "draft"),  # No valid school year: nobody can start it.
    ("2026-11-20", YEAR, READY, "published"),
    ("2026-11-20", YEAR, PARTLY, "draft"),  # Published means every child can start.
    ("2026-11-20", YEAR, NONE, "draft"),
    (TODAY, YEAR, READY, "today"),
    (TODAY, YEAR, PARTLY, "today"),  # Some children can start today, so it is running.
    (TODAY, YEAR, NONE, "draft"),
    ("2026-10-01", YEAR, READY, "past"),
    ("2026-10-01", YEAR, NONE, "past"),
])
def test_status_group_follows_the_date_and_readiness(study_date, school_year, readiness, expected):
    assert session_group({"date": study_date, "school_year": school_year}, readiness, TODAY) == expected


def needs_for(app, **values):
    configure(app)
    state = app.extensions["research"]["state"]
    settings = state.settings()
    session = settings["sessions"][0]
    session.update(values)
    return session_needs(session, session_readiness(settings, session))


def test_needs_name_only_what_is_missing(app):
    assert needs_for(app) == ["questions"]


def test_needs_is_empty_when_the_shared_questions_are_approved(app):
    assert needs_for(app, question_set=question_set()) == []


def test_unapproved_questions_are_still_needed(app):
    assert needs_for(app, question_set=question_set(approved=False)) == ["questions"]


def test_an_unready_individual_set_needs_questions_even_with_shared_ones(app):
    assert needs_for(app, question_set=question_set(),
                     participant_questions={"1": question_set(approved=False)}) == ["questions"]


def test_missing_date_and_ids_are_reported_with_their_steps(app):
    state = app.extensions["research"]["state"]
    session = {"id": "s", "grade": "3", "number": 1, "date": "", "school_year": ""}
    settings = state.settings()
    assert session_needs(session, session_readiness(settings, session)) == ["date", "ids", "questions"]


def test_placeholder_means_nothing_has_been_filled_in():
    assert is_placeholder({"id": "s", "grade": "4", "number": 1, "date": "", "name": "", "school_year": ""})
    for filled in ({"date": "2026-11-20"}, {"name": "Visit"}, {"removed": True},
                   {"question_draft": {"questions": []}}, {"question_set": question_set()}):
        assert not is_placeholder({"id": "s", "grade": "4", "number": 1, "date": "", "name": "", **filled})


def groups_for(app, client, url="/dashboard/sessions?year="):
    with rendered_context(app) as contexts:
        response = client.get(url)
    assert response.status_code == 200
    return response, {group: [row["session"]["id"] for row in rows]
                      for group, rows in contexts[-1]["groups"].items()}


def test_list_shows_each_status_with_its_label_and_links_needs_to_the_step(app, monkeypatch):
    monkeypatch.setattr("research_dashboard.session_views.zurich_today", lambda: TODAY)
    configure(app)
    state = app.extensions["research"]["state"]
    settings = state.settings()
    by_id = {item["id"]: item for item in settings["sessions"]}
    by_id["grade-4-session-1"].update(date=TODAY, question_set=question_set())
    by_id["grade-4-session-2"].update(date="2026-11-20", question_set=question_set())
    by_id["grade-4-session-3"].update(date="2026-11-27")
    by_id["grade-5-session-1"].update(date="2026-10-01", question_set=question_set())
    state.save_settings(settings, settings["revision"])
    client = app.test_client()
    login(client)
    response, groups = groups_for(app, client)
    assert groups["today"] == ["grade-4-session-1"]
    assert groups["published"] == ["grade-4-session-2"]
    assert "grade-4-session-3" in groups["draft"]
    assert "grade-5-session-1" in groups["past"]
    assert '<span class="badge completed">Published</span>' in response.text
    assert ">Approved<" not in response.text
    needs = next(link for link in Controls(response).links
                 if link["text"] == "approved questions" and "grade-4-session-3" in link["href"])
    assert urlsplit(needs["href"]).fragment == "prepare-questions"
    assert client.get(needs["href"]).status_code == 200


def test_class_filter_and_removed_sessions_stay_apart(app):
    configure(app)
    state = app.extensions["research"]["state"]
    settings = state.settings()
    settings["sessions"][0]["removed"] = True
    state.save_settings(settings, settings["revision"])
    client = app.test_client()
    login(client)
    response, groups = groups_for(app, client, f"/dashboard/sessions?grade=5&year={YEAR}")
    listed = [session for rows in groups.values() for session in rows]
    assert listed and all(session.startswith("grade-5-") for session in listed)
    assert "Removed sessions" not in response.text
    response, groups = groups_for(app, client, f"/dashboard/sessions?grade=4&year={YEAR}")
    assert "grade-4-session-1" not in [session for rows in groups.values() for session in rows]
    assert "Removed sessions (1)" in response.text
    assert client.get("/dashboard/sessions?grade=7").status_code == 404


def test_session_page_says_published_and_never_approved_for_the_session(app, monkeypatch):
    monkeypatch.setattr("research_dashboard.preparation_views.zurich_today", lambda: TODAY)
    configure(app)
    state = app.extensions["research"]["state"]
    settings = state.settings()
    settings["sessions"][0].update(date="2026-11-20", question_set=question_set())
    settings["sessions"][1].update(date="2026-11-27")
    state.save_settings(settings, settings["revision"])
    client = app.test_client()
    login(client)
    published = client.get(f"/dashboard/prepare?grade=4&year={YEAR}&session=grade-4-session-1")
    assert "Published for 2026-11-20" in published.text
    assert 'class="session-needs"' not in published.text
    draft = client.get(f"/dashboard/prepare?grade=4&year={YEAR}&session=grade-4-session-2")
    assert "<strong>Draft</strong>" in draft.text and 'class="session-needs"' in draft.text
    italian = client.get(f"/dashboard/prepare?grade=4&year={YEAR}&session=grade-4-session-1&lang=it")
    assert "Pubblicata per 2026-11-20" in italian.text


def test_create_fills_the_next_empty_slot_of_that_class_and_opens_step_two(app):
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    created = create_session(client, state, "5", "2026-11-20", "First visit")
    assert created.status_code == 302 and urlsplit(created.location).fragment == "prepare-participants"
    query = parse_qs(urlsplit(created.location).query)
    assert query["session"] == ["grade-5-session-1"] and query["grade"] == ["5"] and query["year"] == [YEAR]
    saved = state.settings()
    session = next(item for item in saved["sessions"] if item["id"] == "grade-5-session-1")
    assert (session["name"], session["date"], session["school_year"]) == ("First visit", "2026-11-20", YEAR)
    assert saved["current_school_year"] == YEAR  # The first session confirms the first school year.
    assert len(saved["sessions"]) == 6
    assert create_session(client, state, "5", "2026-11-27").status_code == 302
    assert any(item["id"] == "grade-5-session-2" and item["date"] == "2026-11-27"
               for item in state.settings()["sessions"])


def test_create_keeps_numbering_once_the_slots_are_used(app):
    configure(app)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    assert create_session(client, state, "4", "2026-11-20").status_code == 302
    assert state.settings()["sessions"][-1]["id"] == "grade-4-session-4"


def test_removing_from_the_session_page_returns_to_the_list(app):
    configure(app)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    page = client.get(f"/dashboard/prepare?grade=4&year={YEAR}&session=grade-4-session-1")
    form = next(form for form in Controls(page).forms
                if any(item.get("value") == "remove_session" for item in form["controls"]))
    fields = {item["name"]: item.get("value", "") for item in form["controls"] if item.get("name")}
    removed = client.post(form["attrs"]["action"], data=fields)
    assert removed.status_code == 302 and urlsplit(removed.location).path == "/dashboard/sessions"
    assert urlsplit(removed.location).fragment == "removed-sessions"
    assert "Session removed" in client.get(removed.location).text
    assert next(item for item in state.settings()["sessions"] if item["id"] == "grade-4-session-1")["removed"]


def test_session_views_require_sign_in_and_csrf(app):
    configure(app)
    guest = app.test_client()
    assert guest.get("/dashboard/sessions").status_code == 302
    assert guest.get("/dashboard/sessions/new").status_code == 302
    client = app.test_client()
    login(client)
    token = csrf(client.get("/dashboard/sessions"))
    assert client.post("/dashboard/sessions", data={"action": "remove_session"}).status_code == 400
    assert client.post("/dashboard/sessions", data={"csrf": token, "action": "remove_session"}).status_code == 400
