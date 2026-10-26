"""Native date/year controls work with touch and without dashboard JavaScript."""
from urllib.parse import parse_qs, urlsplit

import pytest

from .test_editor_browser import app, live  # noqa: F401 - shared synthetic fixture

YEAR = "2026/2027"
FUTURE = "2027/2028"
SESSION = "grade-4-session-1"
PREPARE = f"/dashboard/prepare?grade=4&year={YEAR}&session={SESSION}"


@pytest.mark.parametrize("language,touch", [("en", False), ("it", True)])
def test_preparation_native_date_limits_block_wrong_year_and_allow_boundary(live, language, touch):
    if touch:
        browser = live.context.browser
        live.context.close()
        live.context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
    page = live.login()
    page.goto(live.base + PREPARE + "&lang=" + language)
    state = live.app.extensions["research"]["state"]
    before = state.settings()
    requests = []
    page.on("request", lambda request: requests.append(request.method) if "/prepare?" in request.url else None)
    page.fill("#prepare-date", "2027-09-01")
    page.locator(".preparation-details button[type=submit]").click()
    assert page.locator("#prepare-date").evaluate("input => input.validity.rangeOverflow")
    assert "POST" not in requests
    assert state.settings() == before
    page.fill("#prepare-date", "2026-09-01")
    with page.expect_navigation():
        page.locator(".preparation-details button[type=submit]").click()
    assert state.settings()["sessions"][0]["date"] == "2026-09-01"
    assert "saved=1" in page.url


def test_new_year_and_admin_scope_work_without_javascript(live):
    browser = live.context.browser
    live.context.close()
    live.context = browser.new_context(java_script_enabled=False, viewport={"width": 768, "height": 1024}, has_touch=True)
    page = live.login()
    page.goto(live.base + f"/dashboard/prepare?grade=4&year={YEAR}&new=1")
    assert page.locator("#prepare-year-choices option[value='2026/2027']").count() == 1
    page.fill("#prepare-year", FUTURE)
    with page.expect_navigation():
        page.locator(".preparation-picker > button").click()
    assert parse_qs(urlsplit(page.url).query)["year"] == [FUTURE]
    assert page.locator("#prepare-date").get_attribute("min") == "2027-09-01"
    page.fill("#prepare-name", "Next year's session")
    page.fill("#prepare-date", "2027-10-01")
    with page.expect_navigation():
        page.locator(".preparation-details button[type=submit]").click()
    session_id = parse_qs(urlsplit(page.url).query)["session"][0]
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
