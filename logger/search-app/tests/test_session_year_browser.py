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
    assert page.inner_text("#prepare-year-value") == FUTURE
    # Nobody is enrolled for the later year yet: the page says so and links the yearly step.
    assert page.locator("#prepare-participants .notice.warning a").count() == 1

    page.fill("#prepare-date", "2026-09-01")
    with page.expect_navigation():
        page.locator(".preparation-details button[type=submit]").click()
    saved = next(item for item in state.settings()["sessions"] if item["id"] == SESSION)
    assert (saved["date"], saved["school_year"]) == ("2026-09-01", YEAR)
    assert page.inner_text("#prepare-year-value") == YEAR


def test_new_year_and_admin_scope_work_without_javascript(live):
    browser = live.context.browser
    live.context.close()
    live.context = browser.new_context(java_script_enabled=False, viewport={"width": 768, "height": 1024}, has_touch=True)
    page = live.login()
    page.goto(live.base + f"/dashboard/prepare?grade=4&year={YEAR}&new=1")
    page.fill("#prepare-name", "Next year's session")
    page.fill("#prepare-date", "2027-10-01")
    with page.expect_navigation():
        page.locator(".preparation-details button[type=submit]").click()
    query = parse_qs(urlsplit(page.url).query)
    assert query["year"] == [FUTURE]
    session_id = query["session"][0]
    # The year menu works without JavaScript and lists the new year.
    page.locator("#prepare-year > summary").click()
    with page.expect_navigation():
        page.locator(f"#prepare-year button[value='{YEAR}']").click()
    assert page.inner_text("#prepare-year-value") == YEAR
    page.goto(live.base + f"/dashboard/prepare?grade=4&year={FUTURE}&session={session_id}")
    with page.expect_navigation():
        page.locator(".preparation-administration a").first.click()
    assert page.locator("#settings-session-year").input_value() == FUTURE
    assert page.locator(".settings-session-item").count() == 1
    assert page.locator(".settings-session-item").get_attribute("id") == session_id
    page.select_option("#settings-session-year", "")
    with page.expect_navigation():
        page.locator(".settings-year-scope button").click()
    assert page.locator("#settings-session-year").input_value() == ""
    assert page.locator(".settings-session-item").count() == 4
    with page.expect_navigation():
        page.locator(".settings-grade-nav a").first.click()
    assert parse_qs(urlsplit(page.url).query, keep_blank_values=True)["year"] == [""]
