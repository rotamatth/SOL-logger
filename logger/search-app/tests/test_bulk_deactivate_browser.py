"""Selecting several children works by mouse and touch, and without dashboard JavaScript."""
import pytest

from .test_editor_browser import app, live, until  # noqa: F401
from .test_research_dashboard import configure

YEAR = "2026/2027"
REGISTER = f"/dashboard/settings/enrollment?year={YEAR}&grade=4&lang=en"


def test_select_all_counts_and_the_button_waits_for_a_choice(live):
    configure(live.app)
    state = live.app.extensions["research"]["state"]
    page = live.login()
    page.goto(live.base + REGISTER)
    button = page.locator("#bulk-deactivate button[type=submit]")
    assert button.is_disabled()
    page.locator("input[name=ids][value='1']").check()
    assert page.inner_text("[data-selected-count]") == "1"
    assert button.is_enabled()
    assert page.locator("[data-select-all-ids]").evaluate("box => box.indeterminate")
    page.locator("[data-select-all-ids]").check()
    assert page.inner_text("[data-selected-count]") == "20"
    page.locator("[data-select-all-ids]").uncheck()
    assert page.inner_text("[data-selected-count]") == "0" and button.is_disabled()
    page.locator("input[name=ids][value='2']").check()
    page.locator("input[name=ids][value='3']").check()
    with page.expect_navigation():
        button.click()
    assert "2, 3" in page.inner_text("section.panel")
    assert state.settings()["participant_registry"]["2"]["active"]
    with page.expect_navigation():
        page.locator("form[data-unsaved] button.primary").click()
    assert "Participant changes saved" in page.inner_text("main")
    registry = state.settings()["participant_registry"]
    assert not registry["2"]["active"] and not registry["3"]["active"] and registry["1"]["active"]
    assert page.locator("input[name=ids][value='2']").count() == 0


@pytest.mark.parametrize("language", ["en", "it"])
def test_it_fits_a_phone_and_works_without_javascript(live, language):
    configure(live.app)
    state = live.app.extensions["research"]["state"]
    browser = live.context.browser
    live.context.close()
    live.context = browser.new_context(java_script_enabled=False, viewport={"width": 390, "height": 844}, has_touch=True)
    page = live.login()
    page.goto(live.base + REGISTER.replace("lang=en", "lang=" + language))
    assert page.locator("[data-select-all-ids]").is_hidden()
    page.locator("input[name=ids][value='4']").check()
    with page.expect_navigation():
        page.locator("#bulk-deactivate button[type=submit]").click()
    with page.expect_navigation():
        page.locator("form[data-unsaved] button.primary").click()
    assert not state.settings()["participant_registry"]["4"]["active"]
