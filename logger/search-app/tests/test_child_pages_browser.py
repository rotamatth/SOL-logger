"""The classroom tablets are shorter than an iPad: each step must fit without scrolling to the button."""
import pytest

from .progress_helpers import through_intro
from .test_background_upload_browser import search, student_site  # noqa: F401
from .test_first_answer_flow_browser import open_first

SIZES = [(1180, 699), (1280, 680), (1024, 520)]


def fits(page, button=None):
    extra = page.evaluate("document.documentElement.scrollHeight - innerHeight")
    assert extra <= 30, f"the page is {extra} px taller than the screen"
    if button:
        box = page.locator(button).bounding_box()
        assert box["y"] + box["height"] <= page.viewport_size["height"], f"{button} is below the screen"


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
@pytest.mark.parametrize("size", SIZES)
def test_every_step_of_a_question_fits_a_short_tablet(student_site, size):
    page, base, _ = student_site
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(base + "/start")
    page.select_option("#id-box", "1")
    page.click("#continue-btn")
    page.locator("#task-intro-continue").wait_for()
    fits(page, "#task-intro-continue")
    through_intro(page)
    fits(page, "#first-answer-confirm")
    assert page.locator("#first-answer-search").count() == 0
    page.fill("#first-answer-text", "Un cane di nome Laika, che è stato il primo animale nello spazio")
    page.get_by_role("radio", name="Abbastanza giusta", exact=True).check()
    fits(page, "#first-answer-confirm")
    assert page.locator(".first-answer-confidence").is_visible()
    page.get_by_role("button", name="Conferma", exact=True).click()
    page.locator("a#first-answer-search").wait_for()
    fits(page, "a#first-answer-search")
    page.click("a#first-answer-search")
    page.wait_for_url("**/search")
    search(page, "api miele")
    page.click("#end-task-btn")
    page.fill("#textarea_feedback", "Laika, una cagnolina russa")
    page.click("#feedback-btn")
    page.click("#yes-end-btn")
    page.wait_for_url("**/task-review/1")
    page.locator(".review-button").wait_for()
    fits(page, ".review-button")
    box = page.locator(".review-animation").bounding_box()
    assert box["height"] >= 0.5 * size[1] and box["y"] >= 0
    assert page.locator(".review-animation").evaluate("video => getComputedStyle(video).filter") == "none"
    for card in (".review-before", ".review-after"):
        assert page.locator(card).is_visible()


def test_a_mistaken_non_lo_so_has_two_equal_buttons(student_site):
    page, base, _ = student_site
    open_first(page, base)
    outline = page.locator("#first-answer-unknown").bounding_box()
    confirm = page.locator("#first-answer-confirm").bounding_box()
    assert outline["width"] == confirm["width"]
    page.locator("#first-answer-unknown").click()
    back = page.get_by_role("button", name="Torna alla risposta").bounding_box()
    sure = page.get_by_role("button", name="Confermo: non lo so").bounding_box()
    assert back["width"] == sure["width"] and back["height"] == sure["height"] and back["y"] == sure["y"]
