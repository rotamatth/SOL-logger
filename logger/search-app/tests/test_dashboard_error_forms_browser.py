"""Rejected settings/enrollment edits remain protected until explicitly saved.

All fixtures use isolated synthetic settings, people and log files. Browser cases
exercise the returned page, cancellation and a corrected retry through the real
guard and server validation.
"""
import pytest

from .test_editor_browser import app, live, until  # noqa: F401 - pytest fixtures
from .test_enrollment_controls import Controls
from .test_permanent_participants import change
from .test_research_dashboard import configure, csrf, login, write_run

YEAR = "2026/2027"
SESSION = "grade-4-session-1"
REGISTRY = f"/dashboard/settings/enrollment?year={YEAR}&grade=4&lang=en"


def marked_forms(response):
    return [form for form in Controls(response).forms if "data-unsaved" in form["attrs"]]


def values(form):
    return {item.get("name"): item.get("value") for item in form["controls"]}


@pytest.mark.parametrize("action, fields", [
    ("save_year", {"current_school_year": "2026/2026"}),
    ("add_session", {"grade": "4", "school_year": YEAR, "date": "2027-10-20", "name": "New input"}),
    ("save_session", {"session_id": SESSION, "school_year": YEAR, "date": "2027-10-20", "name": "Edited input"}),
    ("restore_session", {"session_id": "grade-4-session-2", "date": "2027-10-20"}),
    ("preview_ranges", {"range_grade": "4", "ranges_editor": "1", "4_start": "1", "4_end": "25", "4_width": "0"}),
])
def test_settings_error_marks_only_the_submitted_form(app, action, fields):
    configure(app)
    state = app.extensions["research"]["state"]
    if action == "restore_session":
        settings = state.settings()
        settings["sessions"][1]["removed"] = True
        state.save_settings(settings, settings["revision"])
    client = app.test_client()
    login(client)
    before = state.settings()
    response = client.post("/dashboard/settings?grade=4", data={
        "csrf": csrf(client.get("/dashboard/settings")), "revision": before["revision"],
        "action": action, **fields})
    assert response.status_code == 400
    assert state.settings() == before
    forms = marked_forms(response)
    assert len(forms) == 1
    assert "data-guard" in forms[0]["attrs"]
    if action == "preview_ranges":
        assert values(forms[0])["4_end"] == "25"
    else:
        assert values(forms[0])["action"] == action
        for field, value in fields.items():
            if field != "grade":
                assert values(forms[0])[field] == value


@pytest.mark.parametrize("operation, view, fields", [
    ("add", "registry", {"ids": "1", "year": YEAR, "grade": "4"}),
    ("enroll", "registry", {"ids": "missing-id", "year": YEAR, "grade": "4"}),
    ("update", "registry", {"uid": "1", "year": "2026/2026", "grade": "4", "active": "no"}),
    ("promote", "promotion", {"source_year": YEAR, "target_year": YEAR}),
    ("link", "links", {"source_id": "1", "uid": "2", "date_from": "2025-01-01", "date_to": "2025-12-31", "note": "Retain this note"}),
])
def test_enrollment_error_marks_only_the_submitted_form(app, operation, view, fields):
    configure(app)
    write_run(app, collection="legacy", suffix="legacy-error")
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    before = state.settings()
    url = REGISTRY + "&view=" + view
    response = client.post(url, data={"csrf": csrf(client.get(url)), "revision": before["revision"],
                                      "operation": operation, **fields})
    assert response.status_code == 400
    assert state.settings() == before
    forms = marked_forms(response)
    assert len(forms) == 1 and "data-guard" in forms[0]["attrs"]
    controls = values(forms[0])
    operation_field = next(item for item in forms[0]["controls"] if item.get("name") == "operation")
    if operation_field["tag"] == "select":
        assert any(option.get("value") == operation and "selected" in option
                   for option in operation_field["options"])
    else:
        assert controls["operation"] == operation
    if "note" in fields:
        assert controls["note"] == fields["note"]


def test_stale_update_retains_editor_when_person_moves_outside_the_filter(app):
    configure(app)
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    original = state.settings()
    token = csrf(client.get(REGISTRY + "&edit=1&status=active"))
    change(state, "update", uid="1", year=YEAR, grade="5", active=False)
    latest = state.settings()
    response = client.post(REGISTRY + "&edit=1&status=active", data={
        "csrf": token, "revision": original["revision"], "operation": "update",
        "uid": "1", "year": YEAR, "grade": "4", "active": "no"})
    assert response.status_code == 400  # Previously turned the rejection into a 404.
    assert "Reload saved settings" in response.text
    forms = marked_forms(response)
    assert len(forms) == 1 and values(forms[0])["uid"] == "1"
    assert state.settings() == latest
    corrected = client.post(REGISTRY + "&edit=1&status=active", data={
        "csrf": csrf(response), "revision": latest["revision"], "operation": "update",
        "uid": "1", "year": YEAR, "grade": "4", "active": "no"})
    assert corrected.status_code == 200
    review = values(marked_forms(corrected)[0])
    saved = client.post(REGISTRY + "&edit=1&status=active", data={
        "csrf": csrf(corrected), "action": "confirm", "review_token": review["review_token"]})
    assert saved.status_code == 302
    assert state.settings()["enrollments"][YEAR]["1"]["grade"] == "4"


def test_concurrent_roster_shrink_keeps_the_rejected_form_and_corrected_review(app):
    configure(app)
    state = app.extensions["research"]["state"]
    change(state, "add", ids=[f"SYNTH-{number:02}" for number in range(31)], year=YEAR, grade="4")
    client = app.test_client()
    login(client)
    url = REGISTRY + "&status=active&page=2&edit=SYNTH-30"
    opened = client.get(url)
    assert opened.status_code == 200
    original = state.settings()
    change(state, "update", uid="SYNTH-30", year=YEAR, grade="4", active=False)
    fields = {"csrf": csrf(opened), "revision": original["revision"], "operation": "update",
              "uid": "SYNTH-30", "year": YEAR, "grade": "4", "active": "yes"}
    rejected = client.post(url, data=fields)
    assert rejected.status_code == 400 and "Reload saved settings" in rejected.text
    assert values(marked_forms(rejected)[0])["uid"] == "SYNTH-30"
    fields["revision"] = state.settings()["revision"]
    review = client.post(url, data=fields)
    assert review.status_code == 200 and values(marked_forms(review)[0])["review_token"]
    assert client.get(url).status_code == 404  # Out-of-range GET pages remain invalid.


def assert_cancelled_leave(live, page, selector='a[lang="it"]'):
    before, dialogs = page.url, len(live.dialogs)
    page.locator(selector).first.click()
    assert until(page, lambda: len(live.dialogs) > dialogs, seconds=3)
    assert "unsaved changes" in live.dialogs[-1]
    assert page.url == before


@pytest.mark.parametrize("operation", ["year", "range", "add_session", "edit_session", "restore_session"])
def test_settings_validation_retry_preserves_values_and_leave_protection(live, operation):
    state = live.app.extensions["research"]["state"]
    if operation == "restore_session":
        settings = state.settings()
        settings["sessions"][1]["removed"] = True
        state.save_settings(settings, settings["revision"])
    page = live.login()
    if operation == "year":
        path, selector, invalid, corrected = "?section=year&grade=4", "#current-school-year", "2026/2026", "2027/2028"
    elif operation == "range":
        path, selector, invalid, corrected = "?section=participants&grade=4&edit_participants=1", '[name="4_end"]', "25", "19"
    elif operation == "add_session":
        path, selector, invalid, corrected = "?section=sessions&grade=4&new=1", "#new-date", "2027-10-20", "2026-10-20"
    elif operation == "edit_session":
        path, selector, invalid, corrected = f"?section=sessions&grade=4&edit={SESSION}", f"#date_{SESSION}", "2027-10-20", "2026-10-20"
    else:
        path, selector, invalid, corrected = "?section=sessions&grade=4&removed=1", "#restore-date-grade-4-session-2", "2027-10-20", "2026-10-20"
    page.goto(live.base + "/dashboard/settings" + path + "&lang=en")
    field = page.locator(selector)
    form = field.locator("xpath=ancestor::form")
    if operation == "add_session":
        page.fill("#new-name", "Created after correcting validation")
    elif operation == "edit_session":
        page.fill(f"#name_{SESSION}", "Edited after correcting validation")
    field.fill(invalid)
    # The browser's min/max constraints complement the server checks. Disable
    # those locally to exercise the actual server-error re-render as well.
    form.evaluate("form => form.noValidate = true")
    with page.expect_navigation() as navigation:
        form.locator("button[type=submit]").click()
    assert navigation.value.status == 400
    assert page.input_value(selector) == invalid
    assert page.locator("form[data-unsaved]").count() == 1
    assert_cancelled_leave(live, page)
    assert_cancelled_leave(live, page, 'a[data-section="history"]')
    assert page.input_value(selector) == invalid

    if operation in ("add_session", "edit_session", "restore_session"):
        # A clean sibling submission must warn about the failed form too.
        before, dialogs = page.url, len(live.dialogs)
        page.locator('form:has(input[name="action"][value="save_year"])').evaluate("form => form.requestSubmit()")
        assert until(page, lambda: len(live.dialogs) > dialogs, seconds=3)
        assert page.url == before
    field = page.locator(selector)
    form = field.locator("xpath=ancestor::form")
    field.fill(corrected)
    with page.expect_navigation() as navigation:
        form.locator("button[type=submit]").click()
    assert navigation.value.status < 400
    if operation == "range":
        # Preview is still a proposal; returning to edit must keep that status.
        assert page.locator("form[data-unsaved]").count() == 1
        assert_cancelled_leave(live, page)
        with page.expect_navigation():
            page.locator('button[value="edit_ranges"]').click()
        assert page.input_value('[name="4_end"]') == corrected
        assert page.locator("form[data-unsaved]").count() == 1
        assert_cancelled_leave(live, page)
        with page.expect_navigation():
            page.locator('button[value="preview_ranges"]').click()
        with page.expect_navigation():
            page.locator('button[value="save_ranges"]').click()
        assert state.settings()["ranges"][0]["end"] == 19
    elif operation == "year":
        assert state.settings()["current_school_year"] == corrected
    elif operation == "add_session":
        assert any(item.get("name") == "Created after correcting validation" for item in state.settings()["sessions"])
    elif operation == "edit_session":
        assert state.settings()["sessions"][0]["name"] == "Edited after correcting validation"
    else:
        assert state.settings()["sessions"][1]["date"] == corrected
        assert not state.settings()["sessions"][1]["removed"]
    assert page.locator("form[data-unsaved]").count() == 0


@pytest.mark.parametrize("operation", ["add", "enroll", "update", "promote", "link"])
def test_enrollment_validation_retry_and_review_stay_protected(live, operation):
    state = live.app.extensions["research"]["state"]
    if operation == "link":
        write_run(live.app, collection="legacy", suffix="legacy-link-error")
    page = live.login()
    view = "promotion" if operation == "promote" else "links" if operation == "link" else "registry"
    page.goto(live.base + REGISTRY + "&view=" + view + ("&edit=1" if operation == "update" else ""))
    if operation in ("add", "enroll"):
        page.locator("details.panel:has(#ids) > summary").click()
        page.select_option("#id-operation", operation)
        selector, invalid, corrected = "#ids", "1" if operation == "add" else "missing-id", "SYNTH-NEW" if operation == "add" else "1"
    elif operation == "update":
        page.select_option("#active", "no")
        selector, invalid, corrected = "#year", "2026/2026", YEAR
    elif operation == "promote":
        selector, invalid, corrected = "#target_year", YEAR, "2027/2028"
    else:
        page.select_option("#source_id", "1")
        page.select_option("#uid", "2")
        page.fill("#date_from", "2025-01-01")
        page.fill("#note", "Researcher note retained after rejection")
        selector, invalid, corrected = "#date_to", "2025-12-31", "2026-12-31"
    page.fill(selector, invalid)
    with page.expect_navigation() as navigation:
        page.locator(selector).locator("xpath=ancestor::form").locator('button[type="submit"]').click()
    assert navigation.value.status == 400
    assert page.input_value(selector) == invalid
    assert page.locator("form[data-unsaved]").count() == 1
    assert_cancelled_leave(live, page)
    assert_cancelled_leave(live, page, 'a[data-section="history"]')
    if view == "registry":
        before, dialogs = page.url, len(live.dialogs)
        page.locator(".enrollment-filters").evaluate("form => form.requestSubmit()")
        assert until(page, lambda: len(live.dialogs) > dialogs, seconds=3)
        assert page.url == before and page.input_value(selector) == invalid
    if operation == "link":
        assert page.input_value("#note") == "Researcher note retained after rejection"
    page.fill(selector, corrected)
    with page.expect_navigation() as navigation:
        page.locator(selector).locator("xpath=ancestor::form").locator('button[type="submit"]').click()
    assert navigation.value.status == 200
    assert page.locator("form[data-unsaved]").count() == 1
    assert_cancelled_leave(live, page)

    # Confirm is a guarded submission as well: an expired login keeps the signed
    # proposal in place and allows the same exact review after signing in again.
    live.expire_logins()
    before = page.url
    page.locator("form:has(input[name=review_token]) button").click()
    page.wait_for_selector(".editor-form-notice")
    assert page.url == before
    live.login()
    with page.expect_navigation():
        page.locator("form:has(input[name=review_token]) button").click()
    assert "saved=1" in page.url and page.locator("form[data-unsaved]").count() == 0
    saved = state.settings()
    if operation == "add":
        assert "SYNTH-NEW" in saved["participant_registry"]
    elif operation == "enroll":
        assert saved["enrollments"][YEAR]["1"]["grade"] == "4"
    elif operation == "update":
        assert not saved["participant_registry"]["1"]["active"]
    elif operation == "promote":
        assert saved["current_school_year"] == "2027/2028"
    else:
        assert saved["participant_links"][0]["note"] == "Researcher note retained after rejection"
