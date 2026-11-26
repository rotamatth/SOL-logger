"""On the end page a tap does nothing; holding the logo for three seconds brings the welcome page back."""
from .test_background_upload_browser import student_site  # noqa: F401


def hold_logo(page, milliseconds):
    box = page.locator("#finished-logo").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.wait_for_timeout(milliseconds)
    page.mouse.up()


def test_a_tap_or_short_press_keeps_the_end_page(student_site):
    page, base, _ = student_site
    page.goto(base + "/fine")
    page.locator("#finished-logo").click()
    hold_logo(page, 1200)
    page.wait_for_timeout(2500)
    assert page.url.endswith("/fine")
    assert page.get_by_text("Alzate la mano per dire che avete finito!").is_visible()


def test_holding_the_logo_for_three_seconds_opens_a_fresh_welcome_page(student_site):
    page, base, _ = student_site
    page.goto(base + "/fine")
    box = page.locator("#finished-logo").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.wait_for_url("**/welcome?reset=1", timeout=6000)
    page.mouse.up()
    assert page.locator(".welcome-start-btn").is_visible()


def test_back_stays_on_the_end_page(student_site):
    page, base, _ = student_site
    page.goto(base + "/welcome")
    page.goto(base + "/fine")
    page.wait_for_timeout(300)
    page.go_back()
    page.wait_for_timeout(500)
    assert page.url.endswith("/fine")
