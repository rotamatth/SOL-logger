"""An adult sets the number, a group goes through the practice in a real browser, and its run starts only then."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import fcntl
import json
import sys

import pytest

from .test_background_upload_browser import student_site  # noqa: F401
from .progress_helpers import through_intro
from .test_editor_browser import until

EARLIER_GROUP = json.dumps([{"session_id": "earlier-group", "logs": [{"type": "synthetic"}]}])


def storage(page):
    return page.evaluate("JSON.stringify(Object.entries(localStorage).sort())")


def files(root):
    return [path for path in Path(root).rglob("*") if path.is_file()]


def events(root, name):
    """The saved events of every log whose file name matches, oldest first."""
    return [json.loads(line) for path in sorted(Path(root).rglob(name)) for line in path.read_text().splitlines()]


@pytest.fixture
def tablet(student_site):
    """A tablet on the welcome page, with the practice on.

    Fullscreen refused: the app stays in the top page, where these tests read storage and requests.
    The fullscreen frame (#38) is covered by test_student_fullscreen_browser.py.
    """
    page, base, root = student_site
    sys.modules["search_backend"].practice_engine_configured = lambda: True
    page.context.add_init_script("Element.prototype.requestFullscreen = () => Promise.reject(new Error('refused'));")
    page.set_viewport_size({"width": 1024, "height": 768})
    page.goto(base + "/welcome")
    return page, base, root


def set_number(page, number):
    page.locator("#set-number-form").wait_for()
    page.select_option("#id-box", number)
    page.click("#continue-btn")
    page.wait_for_url("**/prova")


def finish_practice(page):
    page.click("#practice-intro-continue")
    page.wait_for_url("**/prova/domanda")
    page.fill("#first-answer-text", "Lava e cenere")
    page.get_by_role("radio", name="Giustissima", exact=True).check()
    page.click("#first-answer-confirm")
    page.locator("a#first-answer-search").wait_for()
    page.click("a#first-answer-search")
    page.wait_for_url("**/prova/cerca")
    page.fill("#search-box", "tipi di eruzioni")
    page.click("#submit-box")
    page.wait_for_url("**/prova/risultati")
    page.click("#end-task-btn")
    page.fill("#textarea_feedback", "Effusive ed esplosive")
    page.click("#feedback-btn")
    page.click("#yes-end-btn")
    page.wait_for_url("**/prova/finita")


def test_the_log_begins_after_the_practice_with_the_number_set_before_it(tablet):
    page, _, root = tablet
    page.click(".welcome-start-btn")
    set_number(page, "1")
    page.wait_for_timeout(1200)
    finish_practice(page)
    assert not files(root) and "idSubmitted" not in storage(page)
    ended = datetime.now(ZoneInfo("Europe/Zurich")).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    page.click("#practice-done-continue")
    page.wait_for_url("**/task/intro")
    through_intro(page)
    page.evaluate("window.studyLogger.sendLogs()")
    assert until(page, lambda: any(event["type"] == "idSubmitted" for event in events(root, "1_*_FULL.log")))
    saved = events(root, "1_*_FULL.log")
    chosen = [event for event in saved if event["type"] == "idSubmitted"]
    assert len(chosen) == 1 and chosen[0]["uid"] == "1"
    started = next(event for event in saved if event["type"] == "TaskStarted")
    assert chosen[0]["timestamp"] <= started["timestamp"], "as on the ID page: first the ID, then the question"
    assert min(event["timestamp"] for event in saved) >= ended, "nothing in the log is older than the practice's end"
    assert len({event["sessionID"] for event in saved}) == 1
    assert not list(Path(root).rglob("*INCOMPLETE*"))


def test_a_wrong_number_and_a_reset_leave_nothing_under_the_first_one(tablet):
    page, base, root = tablet
    page.click(".welcome-start-btn")
    set_number(page, "2")
    page.goto(base + "/welcome?reset=1")
    page.click(".welcome-start-btn")
    set_number(page, "1")
    finish_practice(page)
    page.click("#practice-done-continue")
    page.wait_for_url("**/task/intro")
    through_intro(page)
    page.evaluate("window.studyLogger.sendLogs()")
    page.evaluate("window.studyLogger.sendUnsentRuns()")
    assert until(page, lambda: any(event["type"] == "idSubmitted" for event in events(root, "1_*_FULL.log")))
    page.wait_for_timeout(500)
    assert not [path.name for path in files(root) if path.name.startswith("2_") or "INCOMPLETE" in path.name]


def test_a_reload_in_the_practice_goes_on_from_its_step(tablet):
    page, base, _ = tablet
    page.click(".welcome-start-btn")
    set_number(page, "1")
    page.click("#practice-intro-continue")
    page.wait_for_url("**/prova/domanda")
    page.fill("#first-answer-text", "Lava e cenere")
    page.get_by_role("radio", name="Giustissima", exact=True).check()
    page.click("#first-answer-confirm")
    page.locator("a#first-answer-search").wait_for()
    # The fullscreen host reloads on the welcome page.
    page.goto(base + "/welcome")
    page.click(".welcome-start-btn")
    page.wait_for_url("**/prova/cerca")
    assert page.locator("#id-box").count() == 0, "the children never see the list"


def test_a_start_that_fails_shows_riprova_and_then_starts_one_run(tablet):
    page, _, root = tablet
    page.click(".welcome-start-btn")
    set_number(page, "1")
    finish_practice(page)
    progress = next(Path(root).parent.rglob("study-progress.sqlite3"))
    # Another start holds the admission lock for longer than the server waits for it.
    with open(f"{progress}.admission.lock", "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        page.click("#practice-done-continue")
        page.get_by_role("button", name="Riprova", exact=True).wait_for()
        assert "Salvataggio non disponibile" in page.locator(".id-panel [role=alert]").inner_text()
        page.wait_for_timeout(600)
        assert page.get_by_role("button", name="Riprova", exact=True).is_enabled(), "an error is not sent again by itself"
        assert page.locator("select").count() == 0 and not list(Path(root).rglob("*.run.json"))
    page.get_by_role("button", name="Riprova", exact=True).click()
    page.wait_for_url("**/task/intro")
    through_intro(page)
    assert len(list(Path(root).rglob("1_*.run.json"))) == 1
    page.evaluate("window.studyLogger.sendUnsentRuns()")
    page.evaluate("window.studyLogger.sendLogs()")
    assert until(page, lambda: any(event["type"] == "idSubmitted" for event in events(root, "1_*_FULL.log")))
    page.wait_for_timeout(500)
    chosen = [event for event in events(root, "1_*.log") if event["type"] == "idSubmitted"]
    assert len({event["timestamp"] for event in chosen}) == 1, "the retry does not choose the number again"
    assert not list(Path(root).rglob("*INCOMPLETE*"))


def test_a_group_goes_through_the_practice_and_on_to_its_run_without_a_trace(tablet):
    page, base, root = tablet
    # This tablet still holds an earlier group's unsent run: the practice must leave it alone.
    page.evaluate(f"localStorage.setItem('solUnsentRuns', {json.dumps(EARLIER_GROUP)})")
    page.click(".welcome-start-btn")
    set_number(page, "1")
    before = storage(page)
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

    assert not files(root), "the practice wrote a log"
    page.click("#practice-done-continue")
    page.wait_for_url("**/task/intro")
    assert "Cominciamo!" in page.locator("main").inner_text()
    through_intro(page)
    assert page.locator("#first-answer-text").input_value() == "", "the real question starts empty"
