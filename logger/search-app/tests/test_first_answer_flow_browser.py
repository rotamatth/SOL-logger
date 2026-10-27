"""The connected UI works against real routes and durable temporary storage."""
import json

from .test_background_upload_browser import student_site, saved, types_of, search  # noqa: F401


def open_first(page, base, uid="1"):
    page.goto(base + "/start")
    page.select_option("#id-box", uid)
    page.click("#continue-btn")
    page.locator("#first-answer-text").wait_for()


def test_autosaved_first_draft_resumes_in_another_browser_without_search_access(student_site):
    page, base, root = student_site
    open_first(page, base)
    assert page.get_by_role("button", name="Riprova salvataggio").is_hidden()
    page.fill("#first-answer-text", "Un cane di nome Laika")
    page.get_by_text("Bozza salvata.", exact=True).wait_for()
    assert page.get_by_role("button", name="Riprova salvataggio").is_hidden()
    assert page.locator("button#first-answer-search").is_disabled()
    other = page.context.browser.new_context()
    try:
        other.route("https://**", lambda route: route.fulfill(status=200, body="Synthetic external page"))
        resumed = other.new_page()
        open_first(resumed, base)
        assert resumed.locator("#first-answer-text").input_value() == "Un cane di nome Laika"
        assert resumed.locator("button#first-answer-search").is_disabled()
        resumed.get_by_role("button", name="Non lo so", exact=True).click()
        resumed.get_by_role("button", name="Torna alla risposta").click()
        assert resumed.locator("#first-answer-text").input_value() == "Un cane di nome Laika"
        resumed.get_by_role("button", name="Non lo so", exact=True).click()
        resumed.get_by_role("button", name="Confermo: non lo so").click()
        resumed.locator("a#first-answer-search").wait_for()
        resumed.click("a#first-answer-search")
        resumed.wait_for_url("**/search")
        first = types_of(saved(root, "1"), "OwnKnowledgeAnswerSubmitted")
        assert len(first) == 1 and first[0]["outcome"] == "unknown"
        assert len(types_of(saved(root, "1"), "TaskStarted")) == 1
    finally:
        other.close()


def test_failed_draft_save_survives_reload_and_can_retry(student_site):
    page, base, _ = student_site
    open_first(page, base)
    page.route("**/first-answer/draft", lambda route: route.abort())
    page.fill("#first-answer-text", "Questa bozza deve restare")
    page.locator("#first-answer-retry-draft:not([hidden])").wait_for()
    page.reload()
    page.wait_for_function("document.getElementById('first-answer-text').value === 'Questa bozza deve restare'")
    page.locator("#first-answer-retry-draft:not([hidden])").wait_for()
    page.unroute("**/first-answer/draft")
    page.get_by_role("button", name="Riprova salvataggio").click()
    page.get_by_text("Bozza salvata.", exact=True).wait_for()
    assert page.locator("button#first-answer-search").is_disabled()


def test_three_questions_and_lost_final_ack_preserve_one_original_per_question(student_site):
    page, base, root = student_site
    open_first(page, base)
    lost = []

    def upload(route):
        data = route.request.post_data_json
        if not lost and any(event["type"] == "TaskEnded" for event in data.get("logs", [])):
            lost.append(True)
            route.fetch()
            route.abort()
        else:
            route.continue_()

    page.route("**/log_session", upload)
    for number in range(1, 4):
        page.locator("#first-answer-text").wait_for()
        page.fill("#first-answer-text", f"Prima risposta {number}")
        page.get_by_role("button", name="Conferma risposta", exact=True).click()
        page.locator("a#first-answer-search").wait_for()
        page.click("a#first-answer-search")
        search(page, "api miele")
        page.evaluate("sessionStorage.setItem('solFirstDraft:another-attempt:1', 'An unrelated draft')")
        page.click("#end-task-btn")
        page.fill("#textarea_feedback", f"Risposta finale {number}")
        page.click("#feedback-btn")
        page.click("#yes-end-btn")
        if number == 1:
            page.locator("#task-save-error:not([hidden])").wait_for()
            page.click("#yes-end-btn")
        if number < 3:
            page.wait_for_function(f"document.querySelector('.first-answer-number')?.textContent === '#{number + 1}'")
        else:
            page.get_by_role("heading", name="Hai risposto alle tre domande").wait_for()
        assert page.evaluate("sessionStorage.getItem('solFirstDraft:another-attempt:1')") == "An unrelated draft"
        assert not page.evaluate("JSON.parse(localStorage.getItem('browserHistory') || '[]').some(url => url.includes('/result'))")
    events = saved(root, "1")
    assert len(types_of(events, "TaskStarted")) == 3
    assert [event["answer"] for event in types_of(events, "OwnKnowledgeAnswerSubmitted")] == [
        f"Prima risposta {n}" for n in range(1, 4)]
    assert [event["answer"] for event in types_of(events, "TaskEnded")] == [
        f"Risposta finale {n}" for n in range(1, 4)]
    assert not types_of(events, "rewardShown")
    assert len(events) == len({json.dumps(event, sort_keys=True) for event in events})
