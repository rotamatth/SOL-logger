"""Stale session forms remain usable in the actual dashboard templates."""
import pytest

from .test_editor_browser import app, live  # noqa: F401
from .test_settings_concurrency import (
    NAME, SESSION, URL, YEAR, concurrent_change, eleven_sessions,
)


@pytest.mark.parametrize("change,language,javascript", [
    ("remove_other", "en", True),
    ("move_edited", "it", True),
    ("remove_edited", "en", False),
])
def test_conflict_preserves_form_and_review_opens_without_losing_it(live, change, language, javascript):
    state = eleven_sessions(live.app)
    browser = live.context.browser
    live.context.close()
    live.context = browser.new_context(
        java_script_enabled=javascript, viewport={"width": 768, "height": 1024}, has_touch=True)
    page = live.login()
    page.goto(live.base + URL + "&lang=" + language)
    page.locator(f"#{SESSION} > summary").click()
    page.fill(f"#name_{SESSION}", NAME)
    page.fill(f"#date_{SESSION}", "2026-10-12")
    concurrent_change(state, change)
    latest = state.settings()

    with page.expect_navigation() as navigation:
        page.locator(f"#{SESSION} form button[type=submit]").first.click()
    assert navigation.value.status == 400
    assert page.input_value(f"#name_{SESSION}") == NAME
    assert page.input_value(f"#date_{SESSION}") == "2026-10-12"
    assert page.input_value(f"#year_{SESSION}") == YEAR
    assert page.locator(f"#{SESSION}").get_attribute("open") is not None
    assert page.locator(f"#{SESSION} form[data-unsaved]").count() == 1
    assert state.settings() == latest

    with page.expect_popup() as opened:
        page.locator(".settings-workspace a[target='_blank']").click()
    saved = opened.value
    saved.wait_for_load_state()
    assert "/settings?" in saved.url and "page=2" not in saved.url
    if change == "remove_edited":
        assert saved.locator("#removed-sessions").get_attribute("open") is not None
        assert saved.locator(f"input[name=session_id][value='{SESSION}']").count() == 1
    else:
        assert saved.locator(f"#{SESSION}").get_attribute("open") is not None
        assert saved.input_value(f"#name_{SESSION}") != NAME
    assert page.input_value(f"#name_{SESSION}") == NAME
    assert live.dialogs == []
    assert state.settings() == latest
