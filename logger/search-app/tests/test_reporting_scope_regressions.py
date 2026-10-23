"""Year views keep absent children visible; empty runs and error messages do not mislead researchers."""
import json
from pathlib import Path

from .test_dashboard_filters import overview_context
from .test_research_dashboard import app, configure, csrf, identity, login, write_run  # noqa: F401

YEAR = "2026/2027"


def logged_in(app, configured=True):
    if configured:
        configure(app)
    client = app.test_client()
    login(client)
    return client


def empty_run(app, uid="1"):
    """The sidecar of a run that was admitted but never saved an event (e.g. a double tap on Start)."""
    root = Path(app.config["RESEARCH_LOG_DIR"])
    (root / f"{uid}_2026-10-01_08-59-00_empty.run.json").write_text(json.dumps({
        "schema_version": 1, "collection": "v2", "participant_id": uid, "technical_session_id": f"empty-{uid}",
        "log_id": "empty", "started_at": "2026-10-01T08:59:00+02:00", "grade_at_collection": "4", "tasks": []}))


def test_year_view_lists_enrolled_children_without_runs_and_opens_their_page(app):
    client = logged_in(app)
    write_run(app)
    query = f"collection=study&grade=4&school_year={YEAR}&session=grade-4-session-1"
    people = overview_context(app, client, query)["people"]
    assert [person["id"] for person in people] == [str(n) for n in range(1, 21)]
    assert people[0]["dashboard_status"] == "completed"
    assert {person["dashboard_status"] for person in people[1:]} == {"no_data"}
    absent = client.get(f"/dashboard/participants/study/{identity('2')}?grade=4&school_year={YEAR}")
    assert absent.status_code == 200
    # A grade-5 child enrolled in the same year stays out of the grade-4 view.
    assert "21" not in [person["id"] for person in people]


def test_run_without_saved_data_does_not_make_a_completed_child_incomplete(app):
    client = logged_in(app)
    write_run(app)
    empty_run(app)
    context = overview_context(app, client, f"collection=study&grade=4&school_year={YEAR}")
    child = next(person for person in context["people"] if person["id"] == "1")
    assert len(child["visible_runs"]) == 2 and child["empty_run_count"] == 1
    assert child["dashboard_status"] == "completed"
    page = client.get(f"/dashboard/?collection=study&grade=4&school_year={YEAR}")
    assert "1/1 completed" in page.text and "Started without saved data: 1" in page.text
    detail = client.get(f"/dashboard/participants/study/{identity('1')}?school_year={YEAR}")
    assert "1/1 completed" in detail.text and "Started without saved data: 1" in detail.text


def test_child_with_only_an_empty_run_has_no_saved_data_status(app):
    client = logged_in(app)
    empty_run(app, uid="3")
    context = overview_context(app, client, f"collection=study&grade=4&school_year={YEAR}")
    child = next(person for person in context["people"] if person["id"] == "3")
    assert child["dashboard_status"] == "no_data" and child["empty_run_count"] == 1


def test_recovered_fragment_is_shown_but_does_not_decide_the_status(app):
    client = logged_in(app)
    write_run(app)
    root = Path(app.config["RESEARCH_LOG_DIR"])
    fragment = [{"uid": "1", "sessionID": "earlier-tab", "type": "queryBoxFocused",
                 "timestamp": "2026-10-01T09:30:00.000", "recovered": True},
                {"type": "incompleteExperiment", "uid": "1", "sessionID": "earlier-tab"}]
    (root / "1_earlier-tab_INCOMPLETE.log").write_text("".join(json.dumps(event) + "\n" for event in fragment))
    context = overview_context(app, client, f"collection=study&grade=4&school_year={YEAR}")
    child = next(person for person in context["people"] if person["id"] == "1")
    assert len(child["visible_runs"]) == 2 and child["fragment_count"] == 1 and child["empty_run_count"] == 0
    assert child["dashboard_status"] == "completed"
    page = client.get(f"/dashboard/?collection=study&grade=4&school_year={YEAR}")
    assert "1/1 completed" in page.text and "Recovered fragments: 1" in page.text
    detail = client.get(f"/dashboard/participants/study/{identity('1')}?school_year={YEAR}")
    assert "1/1 completed" in detail.text and "Recovered fragments: 1" in detail.text


def test_legacy_link_page_accepts_ids_with_non_decimal_digits(app):
    client = logged_in(app)
    event = {"uid": "²", "sessionID": "legacy-s", "type": "TaskStarted", "task_number": 1,
             "timestamp": "2025-10-01T09:00:00.000"}
    legacy = Path(app.config["RESEARCH_LEGACY_LOG_DIR"])
    (legacy / "x_2025-10-01_09-00-00_aaaaaaaa_FULL.log").write_text(json.dumps(event) + "\n")
    response = client.get(f"/dashboard/settings/enrollment?view=links&year={YEAR}")
    assert response.status_code == 200
    assert '<option value="²"' in response.text


def test_promotion_conflict_and_reserved_ids_name_the_children(app):
    client = logged_in(app)
    state = app.extensions["research"]["state"]
    state.change_participants("enroll", {"ids": ["1", "7"], "year": "2027/2028", "grade": "4"},
                              state.settings()["revision"])
    url = f"/dashboard/settings/enrollment?view=promotion&year={YEAR}"
    page = client.get(url)
    promotion = client.post(url, data={"csrf": csrf(page), "revision": state.settings()["revision"],
                                       "operation": "promote", "source_year": YEAR, "target_year": "2027/2028"})
    assert promotion.status_code == 400 and "<strong>ID: 1, 7</strong>" in promotion.text
    registry = f"/dashboard/settings/enrollment?year={YEAR}"
    added = client.post(registry, data={"csrf": csrf(page), "revision": state.settings()["revision"],
                                        "operation": "add", "ids": "1, 2, 99", "year": YEAR, "grade": "4"})
    assert added.status_code == 400 and "<strong>ID: 1, 2</strong>" in added.text
    assert "99" not in state.settings()["participant_registry"]


def test_missing_school_year_is_translated_instead_of_showing_a_key(app):
    client = logged_in(app, configured=False)
    for lang, text in (("en", "School year not set"), ("it", "Anno scolastico non impostato")):
        response = client.get(f"/dashboard/settings/enrollment?lang={lang}")
        assert response.status_code == 200
        assert text in response.text and "school_year_unknown" not in response.text


def test_year_change_of_a_session_with_records_explains_the_year_not_removal(app):
    client = logged_in(app)
    state = app.extensions["research"]["state"]
    with state.connect() as db:
        db.execute("INSERT INTO study_attempts VALUES (?,?,?,?,1)", ("tech-1", "grade-4-session-1", "1", "{}"))
    url = f"/dashboard/settings?section=sessions&grade=4&year={YEAR}"
    page = client.get(url)
    response = client.post(url, data={"csrf": csrf(page), "revision": state.settings()["revision"],
                                      "action": "save_session", "session_id": "grade-4-session-1",
                                      "school_year": "2027/2028", "date": "2027-10-01", "name": ""})
    assert response.status_code == 400
    assert "its school year cannot change" in response.text and "cannot be removed" not in response.text
