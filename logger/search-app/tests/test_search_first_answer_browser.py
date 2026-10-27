"""The read-only original and its view events use real routes and durable logs."""
import json

from .test_background_upload_browser import student_site, saved, search, types_of  # noqa: F401
from .test_first_answer_flow_browser import open_first

ORIGINAL = '  Un cane\n<Laika> & la sua storia'


def enter(page, base, unknown=False):
    open_first(page, base)
    assert page.locator("#search-first-answer-btn").count() == 0
    if unknown:
        page.get_by_role("button", name="Non lo so", exact=True).click()
        page.get_by_role("button", name="Confermo: non lo so").click()
    else:
        page.fill("#first-answer-text", ORIGINAL)
        page.get_by_role("button", name="Conferma risposta", exact=True).click()
    page.click("a#first-answer-search")
    page.wait_for_url("**/search")


def show(page):
    assert page.locator("#search-first-answer-btn").count() == 1
    page.get_by_role("button", name="La mia prima risposta", exact=True).click()
    page.locator("#search-first-answer-dialog[open]").wait_for()


def test_original_is_read_only_across_search_results_viewer_and_navigation(student_site):
    page, base, root = student_site
    enter(page, base)
    show(page)
    original = page.locator("#search-first-answer-text")
    assert original.input_value() == ORIGINAL and original.get_attribute("readonly") is not None
    page.get_by_role("button", name="Chiudi prima risposta").click()
    assert page.evaluate("document.activeElement.id") == "search-first-answer-btn"

    search(page, "api miele")
    page.click("#end-task-btn")
    page.fill("#textarea_feedback", "Una bozza finale separata")
    page.click("#continue-search-btn")
    show(page)
    assert page.locator("#search-first-answer-text").input_value() == ORIGINAL
    page.keyboard.press("Escape")
    page.locator("#search-first-answer-dialog:not([open])").wait_for(state="attached")
    assert page.evaluate("document.activeElement.id") == "search-first-answer-btn"
    page.click("#end-task-btn")
    assert page.locator("#textarea_feedback").input_value() == "Una bozza finale separata"
    page.click("#continue-search-btn")

    page.click("#abstract-link-1")
    page.locator("#viewer-back-btn").wait_for()
    show(page)
    page.mouse.click(1, 1)
    page.locator("#search-first-answer-dialog:not([open])").wait_for(state="attached")
    show(page)
    page.goto(base + "/search")
    assert page.locator("#search-first-answer-text").input_value() == ORIGINAL
    page.evaluate("() => window.studyLogger.sendLogs()")

    records = saved(root, "1")
    opens, closes = types_of(records, "firstAnswerOpened"), types_of(records, "firstAnswerClosed")
    assert len(opens) == len(closes) == 4
    assert [event["reason"] for event in closes] == ["button", "escape", "backdrop", "pagehide"]
    assert all(event["task_number"] == 1 and event["attempt_id"] and event["uid"] == "1"
               and event["outcome"] == "answered" and "answer" not in event for event in opens + closes)
    assert len({event["sessionID"] for event in opens + closes}) == 1
    task_records = [json.loads(line) for path in root.glob("*_task1_*.log") for line in path.read_text().splitlines()]
    assert len(types_of(task_records, "firstAnswerOpened")) == len(types_of(task_records, "firstAnswerClosed")) == 4
    assert len(types_of(records, "OwnKnowledgeAnswerSubmitted")) == 1 and not types_of(records, "TaskEnded")


def test_confirmed_unknown_resumes_as_unknown_in_a_fresh_browser(student_site):
    page, base, root = student_site
    enter(page, base, unknown=True)
    other = page.context.browser.new_context()
    try:
        other.route("https://**", lambda route: route.fulfill(status=200, body="Synthetic external page"))
        resumed = other.new_page()
        resumed.goto(base + "/start")
        resumed.select_option("#id-box", "1")
        resumed.click("#continue-btn")
        resumed.click("a#first-answer-search")
        show(resumed)
        dialog = resumed.locator("#search-first-answer-dialog")
        assert "Non lo so" in dialog.inner_text() and dialog.locator("textarea,input").count() == 0
        resumed.get_by_role("button", name="Chiudi prima risposta").click()
        resumed.evaluate("() => window.studyLogger.sendLogs()")
        records = saved(root, "1")
        assert types_of(records, "firstAnswerOpened")[-1]["outcome"] == "unknown"
        assert len(types_of(records, "OwnKnowledgeAnswerSubmitted")) == 1
    finally:
        other.close()


def test_existing_question_help_keeps_valid_context_and_does_not_block_the_original(student_site):
    page, base, root = student_site
    enter(page, base)
    page.click("#task-help-btn")
    page.click("#task-help-close-btn")
    page.evaluate("() => window.studyLogger.sendLogs()")
    show(page)
    page.get_by_role("button", name="Chiudi prima risposta").click()
    page.evaluate("() => window.studyLogger.sendLogs()")
    records = saved(root, "1")
    assert len(types_of(records, "taskQuestionHelpClicked")) == len(types_of(records, "taskQuestionHelpClosed")) == 1
    assert all(event["task_number"] == 1 for event in records)
    assert len(types_of(records, "firstAnswerOpened")) == len(types_of(records, "firstAnswerClosed")) == 1


def test_persisted_page_restore_can_reopen_before_the_old_native_close_event(student_site):
    page, base, root = student_site
    enter(page, base)
    show(page)
    # Chromium automation disables BFCache: explicitly exercise the persisted
    # lifecycle, including a reopen before the queued native close callback.
    page.evaluate("""() => {
        window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}));
        window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
        document.getElementById('search-first-answer-btn').click();
    }""")
    page.locator("#search-first-answer-dialog[open]").wait_for()
    page.get_by_role("button", name="Chiudi prima risposta").click()
    page.evaluate("() => window.studyLogger.sendLogs()")
    records = saved(root, "1")
    assert len(types_of(records, "firstAnswerOpened")) == 2
    assert [event["reason"] for event in types_of(records, "firstAnswerClosed")] == ["pagehide", "button"]
    assert page.evaluate("document.activeElement.id") == "search-first-answer-btn"
    per_task = [json.loads(line) for path in root.glob("*_task1_*.log") for line in path.read_text().splitlines()]
    assert len(types_of(per_task, "firstAnswerOpened")) == len(types_of(per_task, "firstAnswerClosed")) == 2
