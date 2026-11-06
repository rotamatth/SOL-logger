"""The guide opens on the first sign-in, its pictures load, and the button brings it back."""
import pytest

from .test_editor_browser import PASSWORD, app, live  # noqa: F401
from research_dashboard.guide_views import GUIDE_STEPS


def sign_in(live, language="en"):
    page = live.page()
    page.goto(f"{live.base}/dashboard/login?lang={language}")
    page.fill("input[type=password]", PASSWORD)
    with page.expect_navigation():
        page.keyboard.press("Enter")
    return page


@pytest.mark.parametrize("language,width", [("en", 1365), ("it", 768), ("it", 390), ("en", 320)])
def test_every_picture_loads_and_nothing_overflows(live, language, width):
    browser = live.context.browser
    live.context.close()
    live.context = browser.new_context(viewport={"width": width, "height": 900})
    page = sign_in(live, language)
    assert "/dashboard/guide" in page.url
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    images = page.locator(".guide-step img")
    assert images.count() == len(GUIDE_STEPS)
    for position in range(images.count()):
        image = images.nth(position)
        image.scroll_into_view_if_needed()
        assert page.wait_for_function("image => image.complete && image.naturalWidth > 0", arg=image.element_handle())
    assert page.locator(".guide-bar a").is_visible()  # Go to Sessions stays on screen while scrolling.


def test_the_way_out_and_the_way_back(live):
    page = sign_in(live)
    with page.expect_navigation():
        page.locator(".guide-bar a").click()
    assert "/dashboard/sessions" in page.url
    with page.expect_navigation():
        page.locator("a.header-guide").click()
    assert "/dashboard/guide" in page.url
    assert page.locator("a.header-guide").get_attribute("aria-current") == "page"
    # Signing in again in the same browser goes straight to work.
    page.locator('form[action*="logout"] button').click()
    with page.expect_navigation():
        page.locator('#logout-dialog button[value="yes"]').click()
    page.fill("input[type=password]", PASSWORD)
    with page.expect_navigation():
        page.keyboard.press("Enter")
    assert "/dashboard/sessions" in page.url
