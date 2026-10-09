"""Settings navigation and grade-scoped edit/review/save workflows."""
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, urlsplit

from .test_research_dashboard import app, csrf, login
from .test_participant_enrollment import ranges_form
from research_dashboard.student_config import task_catalog


class FormFields(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.fields = {}
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "input" and values.get("name") and values.get("type") == "hidden":
            self.fields[values["name"]] = values.get("value", "")


def participant_section(response):
    return response.text.split('id="participant-ids"', 1)[1]


def test_navigation_exposes_one_section_and_retains_selected_grade(app):
    client = app.test_client()
    login(client)
    default = client.get("/dashboard/settings")
    assert 'id="school-year" >' in default.text
    assert 'id="session-history" hidden' in default.text
    assert 'id="participant-ids" hidden' in default.text
    for selected, active_id in (("sessions", "session-history"), ("participants", "participant-ids")):
        response = client.get(f"/dashboard/settings?section={selected}&grade=5&lang=it")
        assert response.status_code == 200
        assert f'id="{active_id}" >' in response.text
        assert 'id="school-year" hidden' in response.text
        assert f'section={selected}&amp;grade=5&amp;lang=it" aria-current="page"' in response.text
    assert client.get("/dashboard/settings?section=unknown").status_code == 404


def test_participant_view_has_no_setup_fields_and_filters_missing_tasks(app):
    client = app.test_client()
    login(client)
    view = participant_section(client.get("/dashboard/settings?section=participants&grade=4"))
    assert "Edit setup" in view and "first number" not in view.lower()
    assert 'name="4_start"' not in view and 'name="4_task_set"' not in view
    filtered = participant_section(client.get("/dashboard/settings?section=participants&grade=4&status=missing"))
    assert re.findall(r'<th scope="row">([^<]+)</th>', filtered) == ["19", "20"]
    assert "No task set assigned" in filtered
    second_page = participant_section(client.get("/dashboard/settings?section=participants&grade=4&roster_page=2"))
    assert re.findall(r'<th scope="row">([^<]+)</th>', second_page) == [str(n) for n in range(11, 21)]
    assert client.get("/dashboard/settings?section=participants&grade=4&roster_page=3").status_code == 404


def test_grade_scoped_review_edit_and_save_keep_other_grades_and_calendars(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    settings = state.settings()
    settings["ranges"].append({"grade": "3", "start": 41, "end": 42, "prefix": "", "width": 0})
    state.save_settings(settings, settings["revision"])
    before = state.settings()
    task_set = task_catalog(app)[0]
    editor = client.get("/dashboard/settings?section=participants&grade=5&edit_participants=1")
    section = participant_section(editor)
    assert 'name="5_start"' in section and 'name="4_start"' not in section
    assert 'value="save_ranges"' not in section
    fields = {"csrf": csrf(editor), "revision": before["revision"], "ranges_editor": "1", "range_grade": "5",
              "action": "preview_ranges", "5_start": "21", "5_end": "39", "5_prefix": "", "5_width": "0",
              "5_task_set": task_set["id"], "5_assignment_mode": "all", "4_end": "2"}
    review = client.post("/dashboard/settings?section=participants&grade=5", data=fields)
    assert review.status_code == 200 and state.settings() == before
    review_body = participant_section(review)
    assert 'type="number"' not in review_body and 'value="save_ranges"' in review_body
    assert "19 / 19 ready to start" in review_body
    draft = FormFields(review_body).fields
    editing = client.post("/dashboard/settings?section=participants&grade=5", data={**draft, "action": "edit_ranges"})
    assert editing.status_code == 200 and state.settings() == before
    assert 'name="5_end" value="39" type="number"' in participant_section(editing)
    saved = client.post("/dashboard/settings?section=participants&grade=5", data={**draft, "action": "save_ranges"})
    assert saved.status_code == 302
    query = parse_qs(urlsplit(saved.location).query)
    assert query["section"] == ["participants"] and query["grade"] == ["5"]
    after = state.settings()
    assert after["ranges"][0] == before["ranges"][0] and after["ranges"][2] == before["ranges"][2]
    assert after["ranges"][1]["end"] == 39 and after["sessions"] == before["sessions"]
    confirmation = client.get(saved.location)
    assert "Participant setup saved" in confirmation.text
    assert 'name="5_start"' not in participant_section(confirmation)


def test_third_grade_enable_preview_cancel_and_save(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    before = state.settings()
    view = client.get("/dashboard/settings?section=participants&grade=3")
    assert "No participant IDs for this grade" in participant_section(view)
    fields = ranges_form(app, client, action="preview_ranges", range_grade="3", **{
        "3_enabled": "1", "3_start": "1", "3_end": "2", "3_prefix": "C-", "3_width": "3",
        "3_task_set": task_catalog(app)[0]["id"], "3_assignment_mode": "all"})
    review = client.post("/dashboard/settings?section=participants&grade=3", data=fields)
    assert review.status_code == 200 and "C-001–C-002" in review.text
    assert state.settings() == before
    draft = FormFields(participant_section(review)).fields
    assert draft["3_enabled"] == "1"
    saved = client.post("/dashboard/settings?section=participants&grade=3", data={**draft, "action": "save_ranges"})
    assert saved.status_code == 302
    assert state.settings()["ranges"][:2] == before["ranges"]


def test_invalid_scoped_range_stays_in_editor_and_keeps_input(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    before = state.settings()
    fields = ranges_form(app, client, action="preview_ranges", range_grade="4", **{"4_end": "25"})
    response = client.post("/dashboard/settings?section=participants&grade=4", data=fields)
    assert response.status_code == 400 and state.settings() == before
    section = participant_section(response)
    assert 'name="4_end" value="25" type="number"' in section
    assert 'value="save_ranges"' not in section
    assert "overlapping participant IDs" in section


def test_stale_session_and_year_forms_preserve_input_and_revision(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    before = state.settings()
    token = csrf(client.get("/dashboard/settings"))
    changed = state.settings()
    changed["current_school_year"] = "2026/2027"
    state.save_settings(changed, changed["revision"])
    latest = state.settings()
    response = client.post("/dashboard/settings?section=sessions&grade=4", data={
        "action": "save_session", "csrf": token, "revision": before["revision"],
        "session_id": "grade-4-session-1", "name": "My classroom", "date": "2026-10-12"})
    assert response.status_code == 400
    assert 'id="grade-4-session-1" open' in response.text
    assert 'value="My classroom"' in response.text and 'value="2026-10-12"' in response.text
    assert "Reload saved settings" in response.text
    assert f'name="revision" value="{before["revision"]}"' in response.text
    year = client.post("/dashboard/settings?section=year", data={
        "action": "save_year", "csrf": token, "revision": before["revision"],
        "current_school_year": "2027/2028"})
    assert year.status_code == 400 and 'value="2027/2028"' in year.text
    assert state.settings() == latest


def test_invalid_year_and_unknown_calendar_grade_return_editable_errors(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    before = state.settings()
    token = csrf(client.get("/dashboard/settings"))
    year = client.post("/dashboard/settings?section=year", data={
        "action": "save_year", "csrf": token, "revision": before["revision"], "current_school_year": "2027/2027"})
    assert year.status_code == 400 and 'value="2027/2027"' in year.text
    invalid_grade = client.post("/dashboard/settings", data={
        "action": "save_dates", "grade": "unknown", "csrf": token, "revision": before["revision"]})
    assert invalid_grade.status_code == 400 and "Invalid study-session configuration" in invalid_grade.text
    assert state.settings() == before


def test_disabling_third_grade_then_editing_retains_saved_assignment(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    task_set = task_catalog(app)[0]
    settings = state.settings()
    settings["ranges"].append({"grade": "3", "start": 41, "end": 42, "prefix": "C-", "width": 3,
                              "assignment": {"id": task_set["id"], "topics": task_set["topics"], "mode": "all"}})
    state.save_settings(settings, settings["revision"])
    before = state.settings()
    fields = ranges_form(app, client, action="preview_ranges", range_grade="3")
    fields.pop("3_enabled")
    review = client.post("/dashboard/settings?section=participants&grade=3", data=fields)
    assert review.status_code == 200
    draft = FormFields(participant_section(review)).fields
    assert "3_enabled" not in draft and draft["3_task_set"] == "saved"
    editing = client.post("/dashboard/settings?section=participants&grade=3", data={**draft, "action": "edit_ranges"})
    section = participant_section(editing)
    assert editing.status_code == 200 and 'value="saved" selected' in section
    assert 'name="3_prefix" value="C-"' in section
    assert state.settings() == before
