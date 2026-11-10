"""The session's school year follows its date, with touch and without dashboard JavaScript."""
from urllib.parse import parse_qs, urlsplit

import pytest

from .test_editor_browser import app, live  # noqa: F401 - shared synthetic fixture

YEAR = "2026/2027"
FUTURE = "2027/2028"
SESSION = "grade-4-session-1"
PREPARE = f"/dashboard/prepare?grade=4&year={YEAR}&session={SESSION}"


@pytest.mark.parametrize("language,touch", [("en", False), ("it", True)])
def test_preparation_files_a_new_date_under_its_own_school_year(live, language, touch):
    if touch:
        browser = live.context.browser
        live.context.close()
        live.context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
    page = live.login()
    page.goto(live.base + PREPARE + "&lang=" + language)
    state = live.app.extensions["research"]["state"]
    assert page.locator("#prepare-date").get_attribute("min") is None
    page.fill("#prepare-date", "2027-09-01")
    with page.expect_navigation():
        page.locator(".preparation-details button[type=submit]").click()
    saved = next(item for item in state.settings()["sessions"] if item["id"] == SESSION)
    assert (saved["date"], saved["school_year"]) == ("2027-09-01", FUTURE)
    assert parse_qs(urlsplit(page.url).query)["year"] == [FUTURE]
    assert FUTURE in page.inner_text(".preparation-heading")
    # Nobody is enrolled for the later year yet: the page says so and links the yearly step.
    assert page.locator("#prepare-participants .notice.warning a").count() == 1

    page.fill("#prepare-date", "2026-09-01")
    with page.expect_navigation():
        page.locator(".preparation-details button[type=submit]").click()
    saved = next(item for item in state.settings()["sessions"] if item["id"] == SESSION)
    assert (saved["date"], saved["school_year"]) == ("2026-09-01", YEAR)
    assert YEAR in page.inner_text(".preparation-heading")


def test_new_year_and_admin_scope_work_without_javascript(live):
    browser = live.context.browser
    live.context.close()
    live.context = browser.new_context(java_script_enabled=False, viewport={"width": 768, "height": 1024}, has_touch=True)
    page = live.login()
    page.goto(live.base + "/dashboard/sessions/new?grade=4")
    page.fill("#new-name", "Next year's session")
    page.fill("#new-date", "2027-10-01")
    with page.expect_navigation():
        page.locator(".session-create-form button[type=submit]").click()
    query = parse_qs(urlsplit(page.url).query)
    assert query["year"] == [FUTURE]
    session_id = query["session"][0]
    with page.expect_navigation():
        page.locator("a.session-back").click()
    assert page.locator("#sessions-year").input_value() == FUTURE
    assert page.locator(".session-row").count() == 1
    assert page.locator(".session-row").get_attribute("id") == session_id
    page.select_option("#sessions-year", "")
    with page.expect_navigation():
        page.locator(".sessions-year button").click()
    assert page.locator("#sessions-year").input_value() == ""
    assert page.locator(".session-row").count() >= 2
    with page.expect_navigation():
        page.locator(".sessions-filters .dashboard-grades a").nth(2).click()
    assert parse_qs(urlsplit(page.url).query, keep_blank_values=True)["year"] == [""]
    assert page.locator(f"[id='{session_id}']").count() == 1
