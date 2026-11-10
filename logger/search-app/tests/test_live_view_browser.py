"""The live view updates in place, keeps the researcher's place and says when it cannot update."""
import pytest

from .test_editor_browser import app, live, until  # noqa: F401
from .test_live_view import LIVE, log_events, started, task
from .test_research_dashboard import configure
from .test_study_enrollment import question_set

TODAY = "2026-10-01"
CHILD = "details[data-child='1']"


@pytest.fixture
def running(live, monkeypatch):
    monkeypatch.setattr("research_dashboard.live_views.zurich_today", lambda: TODAY)
    settings = configure(live.app)
    state = live.app.extensions["research"]["state"]
    settings["sessions"][0]["question_set"] = question_set()
    state.save_settings(settings, settings["revision"])
    started(live.app, "1")
    log_events(live.app, "1", "run-1", *task(1, "TaskStarted"))
    return live


def test_a_finished_question_appears_without_losing_the_open_child_or_focus(running):
    live = running
    page = live.login()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(live.base + LIVE + "?lang=en")
    page.locator(f"{CHILD} summary").click()
    page.locator(f"{CHILD} summary").focus()
    assert "0 / 3 finished" in page.inner_text(CHILD)
    log_events(live.app, "1", "run-1", *task(1, "TaskEnded"))
    assert until(page, lambda: "1 / 3 finished" in page.inner_text(CHILD), seconds=9)
    assert page.locator(CHILD).evaluate("row => row.open")
    assert page.evaluate("document.activeElement.closest('details')?.dataset.child") == "1"
    assert "Question 1?" in page.inner_text("#live-questions") or page.locator("#live-questions .stats-question").count() == 1
    assert page.inner_text("#live-status-text").startswith("Updated ")
    assert errors == [] and live.dialogs == []


def test_a_failed_check_says_reconnecting_and_recovers(running):
    live = running
    page = live.login()
    page.goto(live.base + LIVE + "?lang=it")
    page.route("**/live.json**", lambda route: route.abort())
    assert until(page, lambda: "Riconnessione" in page.inner_text("#live-status-text"), seconds=9)
    assert page.locator(".live-child").count() == 20  # The last figures stay on screen.
    page.unroute("**/live.json**")
    assert until(page, lambda: page.inner_text("#live-status-text").startswith("Aggiornato "), seconds=9)


def test_a_signed_out_page_stops_and_offers_to_sign_in_again(running):
    live = running
    page = live.login()
    page.goto(live.base + LIVE + "?lang=en")
    assert page.locator("#live-refresh").is_hidden()
    live.expire_logins()
    assert until(page, lambda: "signed out" in page.inner_text("#live-status-text"), seconds=9)
    assert page.locator("#live-refresh").is_visible()
    assert "/login" in page.locator("#live-refresh").get_attribute("href")


def test_a_hidden_tab_stops_asking_and_catches_up_when_shown(running):
    live = running
    page = live.login()
    page.goto(live.base + LIVE + "?lang=en")
    checks = []
    page.on("request", lambda request: checks.append(request.url) if "live.json" in request.url else None)
    page.evaluate("""() => { Object.defineProperty(document, 'visibilityState', {value: 'hidden', configurable: true});
                             document.dispatchEvent(new Event('visibilitychange')); }""")
    page.wait_for_timeout(6500)
    assert checks == []
    log_events(live.app, "1", "run-1", *task(1, "TaskEnded"))
    page.evaluate("""() => { Object.defineProperty(document, 'visibilityState', {value: 'visible', configurable: true});
                             document.dispatchEvent(new Event('visibilitychange')); }""")
    assert until(page, lambda: "1 / 3 finished" in page.inner_text(CHILD), seconds=3)


@pytest.mark.parametrize("width", [1365, 768, 390])
def test_it_fits_every_width_and_works_without_javascript(running, width):
    live = running
    browser = live.context.browser
    live.context.close()
    live.context = browser.new_context(java_script_enabled=False, viewport={"width": width, "height": 900})
    page = live.login()
    page.goto(live.base + LIVE + "?lang=it")
    assert page.locator(".live-child").count() == 20
    assert page.locator("#live-refresh").is_visible()
    live.context.close()
    live.context = browser.new_context(viewport={"width": width, "height": 900})
    page = live.login()
    page.goto(live.base + LIVE + "?lang=it")
    page.locator(f"{CHILD} summary").click()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
