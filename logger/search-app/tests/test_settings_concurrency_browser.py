"""Stale session forms remain usable in the actual dashboard templates."""
import pytest

from .test_editor_browser import app, live  # noqa: F401
from .test_research_dashboard import configure
from .test_settings_concurrency import NAME, SESSION, URL, concurrent_change


@pytest.mark.parametrize("change,language,javascript", [
    ("remove_other", "en", True),
    ("move_edited", "it", True),
    ("remove_edited", "en", False),
])
def test_conflict_preserves_form_and_review_opens_without_losing_it(live, change, language, javascript):
    configure(live.app)
    state = live.app.extensions["research"]["state"]
    browser = live.context.browser
    live.context.close()
    live.context = browser.new_context(
        java_script_enabled=javascript, viewport={"width": 768, "height": 1024}, has_touch=True)
    page = live.login()
    page.goto(live.base + URL + "&lang=" + language)
    page.fill("#prepare-name", NAME)
    page.fill("#prepare-date", "2026-10-12")
    concurrent_change(state, change)
    latest = state.settings()

    with page.expect_navigation() as navigation:
        page.locator("#prepare-details form button[type=submit]").click()
    assert navigation.value.status == 400
    assert page.input_value("#prepare-name") == NAME
    assert page.input_value("#prepare-date") == "2026-10-12"
    assert page.locator("#prepare-details form[data-unsaved]").count() == 1
    assert state.settings() == latest

    if change == "remove_other":
        assert page.locator(".preparation-workspace a[target='_blank']").count() == 0
    else:
        with page.expect_popup() as opened:
            page.locator(".preparation-workspace a[target='_blank']").click()
        saved = opened.value
        saved.wait_for_load_state()
        if change == "remove_edited":
            assert "/sessions?" in saved.url
            assert saved.locator("#removed-sessions").get_attribute("open") is not None
            assert saved.locator(f"input[name=session_id][value='{SESSION}']").count() == 1
        else:
            assert "/prepare?" in saved.url
            assert saved.input_value("#prepare-name") != NAME
    assert page.input_value("#prepare-name") == NAME
    assert live.dialogs == []
    assert state.settings() == latest
