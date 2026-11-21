"""A group goes through the practice question in a real browser, then on to its ID, and leaves no trace."""
from pathlib import Path
import json
import sys

from .test_background_upload_browser import student_site  # noqa: F401
from .progress_helpers import through_intro

EARLIER_GROUP = json.dumps([{"session_id": "earlier-group", "logs": [{"type": "synthetic"}]}])


def storage(page):
    return page.evaluate("JSON.stringify(Object.entries(localStorage).sort())")


def test_a_group_goes_through_the_practice_and_on_to_its_id_without_a_trace(student_site):
    page, base, root = student_site
    sys.modules["search_backend"].practice_engine_configured = lambda: True
    page.set_viewport_size({"width": 1024, "height": 768})
    page.goto(base + "/welcome")
    # This tablet still holds an earlier group's unsent run: the practice must leave it alone.
    page.evaluate(f"localStorage.setItem('solUnsentRuns', {json.dumps(EARLIER_GROUP)})")
    before = storage(page)
    page.click(".welcome-start-btn")
    page.wait_for_url("**/prova")
    sent = []
    page.on("request", lambda request: sent.append(request.url) if "/log_session" in request.url else None)

    page.click("#practice-intro-continue")
    page.wait_for_url("**/prova/domanda")
    assert page.locator("h1").inner_text().endswith("Sapete elencarne 3?")
    page.fill("#first-answer-text", "Lava e cenere")
    page.get_by_role("radio", name="Giustissima", exact=True).check()
    page.click("#first-answer-confirm")
    page.locator("a#first-answer-search").wait_for()
    page.click("a#first-answer-search")
    page.wait_for_url("**/prova/cerca")

    page.click("#task-help-btn")
    assert page.locator("#task-help-modal").is_visible()
    assert "Sapete elencarne 3?" in page.locator("#task-help-question").inner_text()
    page.click("#task-help-close-btn")
    assert page.locator("#task-help-modal").is_hidden()
    page.click("#search-first-answer-btn")
    assert page.locator("#search-first-answer-dialog").is_visible()
    assert "Lava e cenere" in page.locator("#search-first-answer-dialog").inner_text()
    page.click("#search-first-answer-close")
    assert page.locator("#search-first-answer-dialog").is_hidden()

    page.fill("#search-box", "tipi di eruzioni")
    page.click("#submit-box")
    page.wait_for_url("**/prova/risultati")
    page.click("#abstract-link-1")
    page.wait_for_url("**/prova/pagina**")
    page.click("#end-task-btn")
    page.fill("#textarea_feedback", "Effusive ed esplosive")
    page.click("#feedback-btn")
    page.click("#yes-end-btn")
    page.wait_for_url("**/prova/finita")
    assert "Avete finito la prova!" in page.locator("main").inner_text()
    assert "Lava e cenere" in page.locator(".review-before").inner_text()
    assert "Effusive ed esplosive" in page.locator(".review-after").inner_text()
    assert page.evaluate("document.querySelector('.review-animation').naturalWidth") > 0
    assert sent == [], "the practice sent events"
    assert storage(page) == before, "the practice changed the tablet's stored data"

    page.click("#practice-done-continue")
    page.wait_for_url("**/start")
    assert not [path for path in Path(root).rglob("*") if path.is_file()], "the practice wrote a log"
    page.select_option("#id-box", "1")
    page.click("#continue-btn")
    through_intro(page)
    assert page.locator("#first-answer-text").input_value() == "", "the real question starts empty"
