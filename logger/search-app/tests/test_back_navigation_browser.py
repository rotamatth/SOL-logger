"""The browser's back button does nothing on any of a child's pages: a question only moves forward.

Chromium cannot reproduce Safari's own cache, so a page restored from it is simulated with a persisted
pageshow event, as in test_student_navigation_browser.py; the real iPad remains the acceptance check.
"""
import pytest

from .test_background_upload_browser import saved, search, student_site  # noqa: F401
from .test_child_pages_browser import reach_review


def back_does_nothing(page, ready):
    """Press back twice; the same page stays, without loading again, and the guard is armed again."""
    page.locator(ready).first.wait_for()
    page.wait_for_load_state("load")
    url = page.url
    page.evaluate("window.__samePage = true")
    for _ in range(2):
        page.evaluate("history.back()")
        page.wait_for_timeout(300)
    assert page.url == url
    assert page.evaluate("window.__samePage === true"), "the page loaded again"
    assert page.locator(ready).first.is_visible()
    assert page.evaluate("history.state && history.state.__solBrowserBackBlockerGuard === true")


def persisted_show(page):
    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
def test_back_does_nothing_on_every_page_of_a_question(student_site):
    page, base, root = student_site
    page.goto(base + "/start")
    page.select_option("#id-box", "1")
    page.click("#continue-btn")
    while True:  # "Cominciamo!" and the question's introduction
        page.locator("#task-intro-continue, #first-answer-text").first.wait_for()
        if not page.locator("#task-intro-continue").count():
            break
        back_does_nothing(page, "#task-intro-continue")
        with page.expect_navigation():
            page.locator("#task-intro-continue").click()
    back_does_nothing(page, "#first-answer-text")
    page.fill("#first-answer-text", "Laika")
    page.get_by_role("radio", name="Abbastanza giusta", exact=True).check()
    page.get_by_role("button", name="Conferma", exact=True).click()
    back_does_nothing(page, "a#first-answer-search")
    page.click("a#first-answer-search")
    page.wait_for_url("**/search*")
    back_does_nothing(page, "#search-box")
    search(page, "api miele")
    back_does_nothing(page, "article.content-section")
    page.click("#end-task-btn")
    page.fill("#textarea_feedback", "Una cagnolina russa")
    page.click("#feedback-btn")
    page.click("#yes-end-btn")
    page.wait_for_url("**/task-review/1")
    back_does_nothing(page, "a.review-button")
    page.click("a.review-button")
    back_does_nothing(page, "#task-intro-continue")
    # Recorded in the saved log where the page has the logger (answer form, confirmed answer, search, results),
    # always as blocked on the same page, never as a step back.
    blocked = [event for event in saved(root, "1") if event["type"] == "browserBackBlocked"]
    assert len(blocked) >= 8
    assert {event["reason"] for event in blocked} == {"popstate"}
    assert all(event["fromURL"] == event["toURL"] for event in blocked)


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
def test_an_answer_form_back_from_the_cache_shows_the_answer_already_confirmed(student_site):
    page, base, root = student_site
    page.goto(base + "/start")
    page.select_option("#id-box", "1")
    page.click("#continue-btn")
    page.locator("#task-intro-continue, #first-answer-text").first.wait_for()
    while page.locator("#task-intro-continue").count():
        with page.expect_navigation():
            page.locator("#task-intro-continue").click()
    page.locator("#first-answer-text").wait_for()
    # The same browser confirms the answer in another tab, so this tab still shows the old form, as Safari
    # shows it when it brings the page back from its cache at the same address.
    other = page.context.new_page()
    other.goto(page.url)
    other.fill("#first-answer-text", "Laika")
    other.get_by_role("radio", name="Abbastanza giusta", exact=True).check()
    other.get_by_role("button", name="Conferma", exact=True).click()
    other.locator("a#first-answer-search").wait_for()
    with page.expect_navigation():
        persisted_show(page)
    page.locator("a#first-answer-search").wait_for()
    assert page.locator("#first-answer-form").count() == 0
    page.wait_for_load_state("load")
    page.evaluate("window.studyLogger.sendLogs()")
    blocked = [event for event in saved(root, "1") if event["type"] == "browserBackBlocked"]
    assert [event["reason"] for event in blocked] == ["pageshow"]


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
def test_a_review_back_from_the_cache_returns_to_the_page_reached(student_site):
    page, base, _ = student_site
    reach_review(page, base)
    page.click("a.review-button")
    page.locator("#task-intro-continue").wait_for()
    reached = page.url
    # Question 1's review, as Safari would bring it back from its cache while the tab had reached the next
    # question: the review page sends the child on to the page reached instead of staying.
    page.goto(base + "/task-review/1")
    page.locator("a.review-button").wait_for()
    page.evaluate("url => sessionStorage.setItem('solLastAllowedAppUrl', url)", reached)
    with page.expect_navigation():
        persisted_show(page)
    page.locator("#task-intro-continue").wait_for()
    assert page.url == reached
