"""Failed session setup keeps returned, unsaved text protected from navigation."""
import pytest

from .test_editor_browser import app, live, until  # noqa: F401

PREPARE = "/dashboard/prepare?grade=4&year=2026/2027&session=grade-4-session-1&lang=en"


@pytest.mark.parametrize("destination", ['a[lang="it"]', 'a[data-section="settings"]'])
def test_failed_session_details_stay_guarded_when_leaving(live, destination):
    page = live.login()
    page.goto(live.base + PREPARE)
    page.fill("#prepare-name", "Name kept after validation")
    page.fill("#prepare-date", "2027-10-20")  # Outside this session's school year.
    # Native date bounds now prevent this submission. Bypass those here to keep
    # checking the server validation response and its unsaved-input protection.
    page.locator(".preparation-details").evaluate("form => form.noValidate = true")
    with page.expect_navigation() as navigation:
        page.locator(".preparation-details button[type=submit]").click()
    assert navigation.value.status == 400
    assert page.input_value("#prepare-name") == "Name kept after validation"
    before = page.url

    page.locator(destination).click()
    assert until(page, lambda: bool(live.dialogs), seconds=3)
    assert "unsaved changes" in live.dialogs[-1]
    assert page.url == before  # The fixture dismisses the leave warning.
    assert page.input_value("#prepare-name") == "Name kept after validation"
    assert page.input_value("#prepare-date") == "2027-10-20"

    # Correcting the invalid date still permits an ordinary successful save.
    page.fill("#prepare-date", "2026-10-20")
    with page.expect_navigation():
        page.locator(".preparation-details button[type=submit]").click()
    assert "saved=1" in page.url
    saved = live.app.extensions["research"]["state"].settings()["sessions"][0]
    assert saved["name"] == "Name kept after validation"
    assert saved["date"] == "2026-10-20"
    assert not page.locator(".preparation-details").evaluate("form => form.hasAttribute('data-unsaved')")
