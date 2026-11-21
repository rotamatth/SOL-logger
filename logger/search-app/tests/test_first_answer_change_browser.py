"""In a real browser: "Non lo so", then "Cambia la mia risposta", a written answer, and the search."""
from .test_background_upload_browser import saved, student_site, types_of  # noqa: F401
from .progress_helpers import through_intro


def test_a_group_replaces_non_lo_so_before_searching(student_site):
    page, base, root = student_site
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base + "/start")
    page.select_option("#id-box", "1")
    page.click("#continue-btn")
    through_intro(page)
    page.get_by_role("button", name="Non lo so", exact=True).click()
    page.get_by_role("button", name="Confermo: non lo so").click()
    page.locator("a#first-answer-change").wait_for()

    page.click("a#first-answer-change")
    page.wait_for_url("**/task?change=1")
    assert page.locator("#first-answer-unknown").count() == 0
    page.get_by_role("button", name="Conferma", exact=True).click()
    assert page.url.endswith("/task?change=1"), "an empty answer is asked for again, not sent"
    page.fill("#first-answer-text", "Un cane di nome Laika")
    page.get_by_role("radio", name="Abbastanza giusta", exact=True).check()
    page.get_by_role("button", name="Conferma", exact=True).click()
    page.locator("a#first-answer-search").wait_for()
    assert "Un cane di nome Laika" in page.locator(".first-answer-saved-text").inner_text()
    assert page.locator("a#first-answer-change").count() == 0

    page.click("a#first-answer-search")
    page.wait_for_url("**/search")
    page.click("#search-first-answer-btn")
    assert "Un cane di nome Laika" in page.locator("#search-first-answer-dialog").inner_text()
    assert page.locator("#search-first-answer-change").count() == 0
    assert errors == []
    events = saved(root, "1")
    assert [event["outcome"] for event in types_of(events, "OwnKnowledgeAnswerSubmitted")] == ["unknown"]
    assert [event["answer"] for event in types_of(events, "OwnKnowledgeAnswerChanged")] == ["Un cane di nome Laika"]


def test_annulla_keeps_non_lo_so(student_site):
    page, base, root = student_site
    page.goto(base + "/start")
    page.select_option("#id-box", "1")
    page.click("#continue-btn")
    through_intro(page)
    page.get_by_role("button", name="Non lo so", exact=True).click()
    page.get_by_role("button", name="Confermo: non lo so").click()
    page.click("a#first-answer-change")
    page.wait_for_url("**/task?change=1")
    page.click("#first-answer-change-cancel")
    page.locator("a#first-answer-search").wait_for()
    assert page.locator(".first-answer-saved-text").inner_text() == "Non lo so"
    assert not types_of(saved(root, "1"), "OwnKnowledgeAnswerChanged")
