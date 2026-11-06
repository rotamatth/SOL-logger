"""The connected UI works against real routes and durable temporary storage."""
import json

import pytest

from .test_background_upload_browser import student_site, saved, types_of, search  # noqa: F401
from .progress_helpers import through_intro


def open_first(page, base, uid="1"):
    page.goto(base + "/start")
    page.select_option("#id-box", uid)
    page.click("#continue-btn")
    through_intro(page)


def wait_for_draft_ack(page, phase):
    page.wait_for_function("prefix => !Object.keys(sessionStorage).some(key => key.startsWith(prefix))",
                           arg=f"sol{phase.capitalize()}Draft:")
    assert page.locator(f"#{phase}-answer-draft-status").inner_text() == ""


def test_autosaved_first_draft_resumes_in_another_browser_without_search_access(student_site):
    page, base, root = student_site
    open_first(page, base)
    assert page.get_by_role("button", name="Riprova salvataggio").is_hidden()
    page.fill("#first-answer-text", "Un cane di nome Laika")
    wait_for_draft_ack(page, "first")
    assert page.get_by_role("button", name="Riprova salvataggio").is_hidden()
    assert page.locator("#first-answer-search").count() == 0
    other = page.context.browser.new_context()
    try:
        other.route("https://**", lambda route: route.fulfill(status=200, body="Synthetic external page"))
        resumed = other.new_page()
        open_first(resumed, base)
        assert resumed.locator("#first-answer-text").input_value() == "Un cane di nome Laika"
        assert resumed.locator("#first-answer-search").count() == 0
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
    assert page.locator("#first-answer-draft-status").inner_text().strip()
    page.reload()
    page.wait_for_function("document.getElementById('first-answer-text').value === 'Questa bozza deve restare'")
    page.locator("#first-answer-retry-draft:not([hidden])").wait_for()
    page.unroute("**/first-answer/draft")
    page.get_by_role("button", name="Riprova salvataggio").click()
    wait_for_draft_ack(page, "first")
    assert page.locator("#first-answer-search").count() == 0


@pytest.mark.parametrize("student_site, clip_prefix, artwork",
                         [("Spazio", "Spazio", "space-recap.webp"),
                          ("Corpo umano (orecchio)", "Orecchio", "ear-recap.webp")],
                         indirect=["student_site"])
def test_three_questions_and_lost_final_ack_preserve_one_original_per_question(student_site, clip_prefix, artwork):
    page, base, root = student_site
    page.set_viewport_size({"width": 768, "height": 1024})
    reduced_motion = clip_prefix == "Orecchio"
    if reduced_motion:
        page.emulate_media(reduced_motion="reduce")
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
        page.get_by_role("radio", name="Abbastanza giusta", exact=True).check()
        page.get_by_role("button", name="Conferma", exact=True).click()
        page.locator("a#first-answer-search").wait_for()
        page.click("a#first-answer-search")
        page.wait_for_url("**/search")
        search(page, "api miele")
        topic = page.evaluate("Number(window.TASK_NUMBER)")
        page.evaluate("sessionStorage.setItem('solFirstDraft:another-attempt:1', 'An unrelated draft')")
        page.click("#end-task-btn")
        page.fill("#textarea_feedback", f"Risposta finale {number}")
        page.click("#feedback-btn")
        page.click("#yes-end-btn")
        if number == 1:
            page.locator("#task-save-error:not([hidden])").wait_for()
            page.click("#yes-end-btn")
        page.get_by_text(f"Prima risposta {number}", exact=True).wait_for()
        page.get_by_text(f"Risposta finale {number}", exact=True).wait_for()
        video = page.locator(".review-task video")
        assert video.count() == 1
        assert video.get_attribute("src").split("?")[0] == f"/static/videos/review/{clip_prefix}_{topic:02d}.mp4"
        video.wait_for(state="visible")
        page.wait_for_function("document.querySelector('.review-task video')?.videoWidth > 0")
        assert video.evaluate("video => !video.controls && video.muted && video.playsInline")
        if reduced_motion:
            assert video.evaluate("video => video.paused && video.currentTime === 0")
            page.get_by_role("button", name="Avvia animazione").click()
        page.get_by_role("button", name="Avvia animazione").wait_for(state="detached")
        page.wait_for_function("document.querySelector('.review-task video')?.currentTime > 0")
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
        if number == 1:
            page.set_viewport_size({"width": 320, "height": 700})
            before = page.get_by_role("heading", name="Cosa sapevi prima").bounding_box()
            after = page.get_by_role("heading", name="Cosa sai adesso").bounding_box()
            assert before["x"] == after["x"] and before["y"] < after["y"]
            assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
            page.set_viewport_size({"width": 768, "height": 1024})
        if number < 3:
            page.get_by_role("link", name="Prossima domanda").click()
            through_intro(page)
            page.wait_for_function(f"document.querySelector('.first-answer-number')?.textContent === '#{number + 1}'")
        else:
            page.get_by_role("link", name="Continua", exact=True).click()
            page.get_by_role("heading", name="Le tue risposte").wait_for()
            page.wait_for_function("document.querySelector('.recap-artwork')?.naturalWidth > 0")
            assert page.locator(".recap-artwork").get_attribute("src").endswith(artwork)
            assert page.get_by_role("button", name="Chiudi", exact=True).count() == 0
            first_editor = page.locator("#answer-2-1")
            page.route("**/recap/draft", lambda route: route.fulfill(json={"revision": "invalid"}))
            first_editor.fill("Bozza con conferma non valida")
            page.get_by_text("Conferma della bozza non valida. Riprova.").wait_for()
            assert first_editor.get_attribute("data-revision") == "0"
            assert first_editor.input_value() == "Bozza con conferma non valida"
            page.unroute("**/recap/draft")
            first_editor.fill("Risposta finale 1")
            next_card = page.get_by_role("button", name="Domanda successiva, sessione 2")
            for index in range(1, 4):
                assert page.get_by_text(f"Prima risposta {index}", exact=True).is_visible()
                field = page.locator(f"#answer-2-{index}")
                assert field.input_value() == f"Risposta finale {index}"
                field.fill(f"Risposta aggiornata {index}")
                if index < 3:
                    next_card.click()
            page.set_viewport_size({"width": 1024, "height": 768})
            positions = [page.get_by_role("heading", name=f"Sessione {index}").bounding_box() for index in range(1, 4)]
            assert positions[0]["y"] == positions[1]["y"] == positions[2]["y"]
            assert positions[0]["x"] < positions[1]["x"] < positions[2]["x"]
            assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
            finish = page.get_by_role("button", name="Salva l’attività")
            page.route("**/recap/finish", lambda route: route.fulfill(status=503, json={"error": "Riprova."}))
            finish.click()
            page.locator("#recap-status[data-error]").wait_for()
            assert page.locator("#answer-2-3").input_value() == "Risposta aggiornata 3"
            assert page.get_by_role("link", name="Scarica PDF").count() == 0
            page.unroute("**/recap/finish")
            finish.click()
            with page.expect_download() as result:
                page.get_by_role("link", name="Scarica PDF").click()
            assert result.value.path().read_bytes().startswith(b"%PDF-")
            page.get_by_role("button", name="Chiudi", exact=True).click()
            page.wait_for_url("**/welcome")
        assert page.evaluate("sessionStorage.getItem('solFirstDraft:another-attempt:1')") == "An unrelated draft"
        assert not page.evaluate("JSON.parse(localStorage.getItem('browserHistory') || '[]').some(url => url.includes('/result'))")
    events = saved(root, "1")
    assert len(types_of(events, "TaskStarted")) == 3
    assert [event["answer"] for event in types_of(events, "OwnKnowledgeAnswerSubmitted")] == [
        f"Prima risposta {n}" for n in range(1, 4)]
    assert [event["answer"] for event in types_of(events, "TaskEnded")] == [
        f"Risposta finale {n}" for n in range(1, 4)]
    assert len(types_of(events, "RecapAnswerEdited")) == 3
    assert len(types_of(events, "studySessionFinished")) == 1
    assert not types_of(events, "experimentFinished")
    assert not types_of(events, "rewardShown")
    assert len(events) == len({json.dumps(event, sort_keys=True) for event in events})
