"""Final-draft durability and recovery, with the existing final confirmation."""
import sqlite3

import pytest

from .test_background_upload_browser import student_site, start, search, saved, types_of, until  # noqa: F401


def open_box(page):
    page.click("#end-task-btn")
    page.locator("#textarea_feedback").wait_for()


def enter(page, base):
    start(page, base, "1")
    search(page, "api miele")
    open_box(page)
    assert page.locator("#final-answer-draft-status").count() == 1


def wait_saved(page):
    page.get_by_text("Bozza salvata.", exact=True).wait_for()


def persisted(root, number=1):
    with sqlite3.connect(root.parent / "state" / "study-progress.sqlite3") as db:
        return db.execute("""SELECT text,revision FROM progress_drafts d JOIN progress_attempts a
            ON a.attempt_id=d.attempt_id WHERE a.participant_id='1'
            AND d.question_number=? AND d.phase='final-answer'""", (number,)).fetchone()


def resume(page, base):
    page.goto(base + "/start")
    page.select_option("#id-box", "1")
    page.click("#continue-btn")
    page.click("a#first-answer-search")
    search(page, "api miele")
    open_box(page)


def test_final_draft_resumes_across_pages_and_a_fresh_browser_without_confirmation(student_site):
    page, base, root = student_site
    enter(page, base)
    text = "  Una bozza finale\n<da verificare>"
    page.fill("#textarea_feedback", text)
    wait_saved(page)
    assert persisted(root) == (text, 1)
    page.click("#continue-search-btn")
    page.click("#abstract-link-1")
    open_box(page)
    assert page.locator("#textarea_feedback").input_value() == text
    other = page.context.browser.new_context()
    try:
        other.route("https://**", lambda route: route.fulfill(status=200, body="Synthetic external page"))
        resumed = other.new_page()
        resume(resumed, base)
        assert resumed.locator("#textarea_feedback").input_value() == text
        assert not types_of(saved(root, "1"), "TaskEnded")
        assert len(types_of(saved(root, "1"), "OwnKnowledgeAnswerSubmitted")) == 1
    finally:
        other.close()


def test_failed_save_keeps_text_after_reload_and_retries_durably(student_site):
    page, base, root = student_site
    enter(page, base)
    page.route("**/final-answer/draft", lambda route: route.abort())
    page.fill("#textarea_feedback", "Questa bozza deve restare")
    page.locator("#final-answer-draft-retry:not([hidden])").wait_for()
    assert persisted(root) is None
    page.reload()
    open_box(page)
    assert page.locator("#textarea_feedback").input_value() == "Questa bozza deve restare"
    page.locator("#final-answer-draft-retry:not([hidden])").wait_for()
    page.unroute("**/final-answer/draft")
    page.click("#final-answer-draft-retry")
    wait_saved(page)
    assert persisted(root) == ("Questa bozza deve restare", 1)
    assert page.locator("#final-answer-draft-retry").is_hidden()


def test_stale_browser_keeps_local_text_and_requires_explicit_recovery(student_site):
    page, base, root = student_site
    enter(page, base)
    page.fill("#textarea_feedback", "Prima bozza")
    wait_saved(page)
    other = page.context.browser.new_context()
    try:
        other.route("https://**", lambda route: route.fulfill(status=200, body="Synthetic external page"))
        newer = other.new_page()
        resume(newer, base)
        newer.fill("#textarea_feedback", "Bozza più recente")
        wait_saved(newer)
        page.fill("#textarea_feedback", "Testo locale non salvato")
        page.locator("#final-answer-draft-retry:not([hidden])").wait_for()
        assert persisted(root) == ("Bozza più recente", 2)
        page.reload()
        open_box(page)
        assert page.locator("#textarea_feedback").input_value() == "Bozza più recente"
        page.get_by_text("Testo non salvato sul dispositivo", exact=True).click()
        assert page.get_by_label("Testo finale recuperato dal dispositivo").input_value() == "Testo locale non salvato"
        page.get_by_role("button", name="Usa questo testo", exact=True).click()
        wait_saved(page)
        assert persisted(root) == ("Testo locale non salvato", 3)
    finally:
        other.close()


@pytest.mark.parametrize("newer_server", [False, True])
def test_old_browser_draft_migrates_without_overwriting_newer_sqlite_text(student_site, newer_server):
    page, base, root = student_site
    enter(page, base)
    if newer_server:
        page.fill("#textarea_feedback", "Già nel database")
        wait_saved(page)
    page.evaluate("sessionStorage.setItem(`answer_${window.SESSION_ID}_${window.TASK_NUMBER}`, 'Dal vecchio browser')")
    page.reload()
    open_box(page)
    if newer_server:
        assert page.locator("#textarea_feedback").input_value() == "Già nel database"
        assert persisted(root) == ("Già nel database", 1)
        page.get_by_text("Testo non salvato sul dispositivo", exact=True).click()
        assert page.get_by_label("Testo finale recuperato dal dispositivo").input_value() == "Dal vecchio browser"
    else:
        assert page.locator("#textarea_feedback").input_value() == "Dal vecchio browser"
        wait_saved(page)
        assert persisted(root) == ("Dal vecchio browser", 1)


def test_pending_final_intent_wins_over_older_sqlite_draft_and_retries_once(student_site):
    page, base, root = student_site
    enter(page, base)
    page.fill("#textarea_feedback", "Bozza precedente")
    wait_saved(page)
    draft_requests = []

    def unavailable(route):
        draft_requests.append(route.request.post_data_json)
        route.fulfill(status=503, content_type="application/json", body='{"error":"synthetic"}')

    page.route("**/final-answer/draft", unavailable)
    page.fill("#textarea_feedback", "Finale confermata da conservare")
    page.locator("#final-answer-draft-retry:not([hidden])").wait_for()
    buffer_key = page.evaluate("`solFinalDraft:${window.STUDY_PROGRESS_CONTEXT.attempt_id}:${window.STUDY_PROGRESS_CONTEXT.task_number}`")
    page.evaluate("sessionStorage.setItem('solFinalDraft:another-attempt:1', 'Keep another draft')")

    def block_final(route):
        if any(event["type"] == "TaskEnded" for event in route.request.post_data_json.get("logs", [])):
            route.abort()
        else:
            route.continue_()

    page.route("**/log_session", block_final)
    page.click("#feedback-btn")
    page.click("#yes-end-btn")
    page.locator("#task-save-error:not([hidden])").wait_for()
    count = len(draft_requests)
    page.reload()
    page.locator("#task-save-error:not([hidden])").wait_for()
    assert page.locator("#textarea_feedback").input_value() == "Finale confermata da conservare"
    # Exceed the debounce to verify that a frozen pending confirmation does not autosave.
    page.wait_for_timeout(800)
    assert len(draft_requests) == count and persisted(root) == ("Bozza precedente", 1)
    page.unroute("**/log_session")
    page.click("#yes-end-btn")
    page.wait_for_function("document.querySelector('.first-answer-number')?.textContent === '#2'")
    assert [event["answer"] for event in types_of(saved(root, "1"), "TaskEnded")] == ["Finale confermata da conservare"]
    assert persisted(root) == ("Bozza precedente", 1) and persisted(root, 2) is None
    assert page.evaluate("key => sessionStorage.getItem(key)", buffer_key) is None
    assert page.evaluate("sessionStorage.getItem('solFinalDraft:another-attempt:1')") == "Keep another draft"


def hold_first_save(page):
    held = []

    def hold(route):
        if not held:
            held.append((route, route.fetch()))
        else:
            route.continue_()

    page.route("**/final-answer/draft", hold)
    return held


def test_newer_typing_survives_an_older_in_flight_save_ack(student_site):
    page, base, root = student_site
    enter(page, base)
    held = hold_first_save(page)
    page.fill("#textarea_feedback", "Prima versione")
    assert until(page, lambda: held)
    assert persisted(root) == ("Prima versione", 1)
    page.fill("#textarea_feedback", "Ultima versione digitata")
    assert "Bozza salvata." not in page.locator("#final-answer-draft-status").inner_text()
    held[0][0].fulfill(response=held[0][1])
    wait_saved(page)
    assert page.locator("#textarea_feedback").input_value() == "Ultima versione digitata"
    assert persisted(root) == ("Ultima versione digitata", 2)


def test_lost_draft_ack_recovers_the_durable_text_without_replacing_it(student_site):
    page, base, root = student_site
    enter(page, base)
    lost = []

    def lose(route):
        if not lost:
            lost.append(True)
            route.fetch()
            route.abort()
        else:
            route.continue_()

    page.route("**/final-answer/draft", lose)
    page.fill("#textarea_feedback", "Salvata senza conferma di rete")
    page.locator("#final-answer-draft-retry:not([hidden])").wait_for()
    assert persisted(root) == ("Salvata senza conferma di rete", 1)
    page.click("#final-answer-draft-retry")
    page.locator("#final-answer-draft-status").filter(has_text="ricarica").wait_for()
    page.reload()
    open_box(page)
    wait_saved(page)
    assert page.locator("#textarea_feedback").input_value() == "Salvata senza conferma di rete"
    assert persisted(root) == ("Salvata senza conferma di rete", 1)


@pytest.mark.parametrize("success", [True, False])
def test_late_draft_reply_cannot_recreate_a_buffer_after_final_confirmation(student_site, success):
    page, base, root = student_site
    enter(page, base)
    held = hold_first_save(page)
    page.fill("#textarea_feedback", "Bozza in attesa")
    assert until(page, lambda: held)
    page.fill("#textarea_feedback", "Finale definitiva")
    key = page.evaluate("`solFinalDraft:${window.STUDY_PROGRESS_CONTEXT.attempt_id}:${window.STUDY_PROGRESS_CONTEXT.task_number}`")
    # A204 navigation leaves the old document alive so its delayed fetch
    # callback can run after successful final confirmation and buffer cleanup.
    page.route("**/task", lambda route: route.fulfill(status=204, body=""))
    page.click("#feedback-btn")
    page.click("#yes-end-btn")
    page.wait_for_function("key => sessionStorage.getItem(key) === null", arg=key)
    with page.expect_event("requestfinished" if success else "requestfailed",
                           predicate=lambda req: req.url.endswith("/final-answer/draft")):
        if success:
            held[0][0].fulfill(response=held[0][1])
        else:
            held[0][0].abort()
    # Flush promise callbacks after the terminal network event.
    page.evaluate("() => new Promise(resolve => setTimeout(resolve, 50))")
    assert page.evaluate("key => sessionStorage.getItem(key)", key) is None
    assert persisted(root) == ("Bozza in attesa", 1)
    assert [event["answer"] for event in types_of(saved(root, "1"), "TaskEnded")] == ["Finale definitiva"]
