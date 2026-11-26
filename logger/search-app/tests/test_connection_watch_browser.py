"""In a real browser: the "chiama un adulto" notice, the page-left events and the offline page."""
import json

import pytest

from .test_background_upload_browser import saved, start, student_site, types_of  # noqa: F401
from .test_editor_browser import playwright_api

NOTICE = "#connection-lost-notice"


def uploaded(page, root):
    page.evaluate("() => window.studyLogger.sendLogs()")
    return saved(root, "1")


def test_offline_shows_the_notice_and_coming_back_hides_it(student_site):
    page, base, root = student_site
    start(page, base, "1")
    assert page.locator(NOTICE).count() == 0
    page.context.set_offline(True)
    page.locator(NOTICE).wait_for(state="visible")
    assert "Alza la mano e chiama un adulto." in page.locator(NOTICE).inner_text()
    page.context.set_offline(False)
    page.locator(NOTICE).wait_for(state="hidden", timeout=10000)
    events = uploaded(page, root)
    assert [event["reason"] for event in types_of(events, "connectionLost")] == ["offline"]
    assert len(types_of(events, "connectionBack")) == 1 and types_of(events, "connectionBack")[0]["page"] == "/search"


def test_a_server_that_stops_answering_shows_the_notice_after_ten_seconds(student_site):
    page, base, root = student_site
    page.clock.install()
    start(page, base, "1")
    page.route("**/presenza", lambda route: route.abort())
    page.clock.run_for(4000)
    page.wait_for_timeout(200)
    assert page.locator(NOTICE).count() == 0 or page.locator(NOTICE).is_hidden(), "a few failed signals are not enough"
    page.clock.run_for(12000)
    page.locator(NOTICE).wait_for(state="visible")
    page.unroute("**/presenza")
    page.clock.run_for(4000)
    page.locator(NOTICE).wait_for(state="hidden")
    events = uploaded(page, root)
    assert [event["reason"] for event in types_of(events, "connectionLost")] == ["no-answer"]
    assert len(types_of(events, "connectionBack")) == 1


def test_leaving_the_app_is_logged_and_signalled_but_changing_page_is_not(student_site):
    page, base, root = student_site
    start(page, base, "1")
    signals = []
    page.on("request", lambda request: signals.append(json.loads(request.post_data or "{}"))
            if request.url.endswith("/presenza") else None)
    hide = """visible => {
        Object.defineProperty(document, 'visibilityState', {value: visible ? 'visible' : 'hidden', configurable: true});
        document.dispatchEvent(new Event('visibilitychange'));
    }"""
    page.evaluate(hide, False)
    page.wait_for_timeout(500)
    page.evaluate(hide, True)
    page.wait_for_timeout(300)
    assert not types_of(uploaded(page, root), "pageHidden"), "an instant away is a page change, not leaving"
    page.evaluate(hide, False)
    page.wait_for_timeout(2000)
    assert any(signal.get("page") == "/search" and signal.get("visible") is False for signal in signals)
    page.evaluate(hide, True)
    page.wait_for_timeout(300)
    events = uploaded(page, root)
    assert len(types_of(events, "pageHidden")) == 1 and types_of(events, "pageHidden")[0]["page"] == "/search"
    assert len(types_of(events, "pageVisible")) == 1 and types_of(events, "pageVisible")[0]["hiddenSeconds"] >= 1


def wait_for_service_worker(page):
    page.evaluate("() => navigator.serviceWorker.ready.then(() => true)")
    page.reload()
    page.wait_for_function("() => Boolean(navigator.serviceWorker.controller)")


def test_a_page_that_cannot_load_shows_the_offline_page_then_comes_back(student_site):
    page, base, _ = student_site
    start(page, base, "1")
    wait_for_service_worker(page)
    page.context.set_offline(True)
    page.goto(base + "/search")
    assert "Il collegamento non funziona." in page.locator("h1").inner_text()
    page.context.set_offline(False)
    page.wait_for_selector("#search-box", timeout=12000)


def test_the_dashboard_is_left_to_the_browser(student_site):
    page, base, _ = student_site
    start(page, base, "1")
    wait_for_service_worker(page)
    page.context.set_offline(True)
    with pytest.raises(playwright_api.Error):
        page.goto(base + "/dashboard/login")
    page.context.set_offline(False)


def reports(page):
    """Every report this page sends from now on, in order."""
    sent = []
    page.on("request", lambda request: sent.append(json.loads(request.post_data or "{}"))
            if request.url.endswith("/presenza") else None)
    return sent


def test_every_two_seconds_a_report_says_what_the_classroom_map_needs(student_site):
    page, base, _ = student_site
    start(page, base, "1")
    sent = reports(page)
    page.wait_for_timeout(4500)
    assert len(sent) >= 2, "about one report every two seconds"
    latest = sent[-1]
    assert latest["page"] == "/search" and latest["visible"] is True and latest["incidents"] == []
    assert set(latest["fullscreen"]) == {"capable", "active"}
    assert all(later["order"] > earlier["order"] for earlier, later in zip(sent, sent[1:], strict=False)), "a newer report never goes back"
    assert not any(key in json.dumps(latest) for key in ("query", "answer", "text")), "nothing of what the group writes"


def test_a_refused_draft_is_reported_until_a_save_goes_through(student_site):
    from .progress_helpers import through_intro
    page, base, _ = student_site
    page.goto(base + "/start")
    page.select_option("#id-box", "1")
    page.click("#continue-btn")
    through_intro(page)
    page.route("**/first-answer/draft", lambda route: route.fulfill(status=503, content_type="application/json",
                                                                  body='{"error": "x"}'))
    sent = reports(page)
    page.fill("#first-answer-text", "Un cane")
    page.locator("#first-answer-retry-draft").wait_for(state="visible", timeout=15000)
    page.wait_for_timeout(500)
    refused = [item for item in sent if item.get("incidents")]
    assert refused and refused[-1]["incidents"][0]["code"] == "save_unconfirmed"
    assert refused[-1]["incidents"][0]["reason"] == "server"
    page.unroute("**/first-answer/draft")
    page.click("#first-answer-retry-draft")
    page.locator("#first-answer-retry-draft").wait_for(state="hidden")
    page.wait_for_timeout(500)
    assert sent[-1]["incidents"] == [] and sent[-1]["lastSaveFor"] is not None and sent[-1]["lastSaveFor"] < 5


def test_a_draft_refused_as_stale_is_not_reported_to_the_map(student_site):
    """The autosave that lands after the answer moved on is refused (409): nothing is lost, so no incident."""
    from .progress_helpers import through_intro
    page, base, _ = student_site
    page.goto(base + "/start")
    page.select_option("#id-box", "1")
    page.click("#continue-btn")
    through_intro(page)
    page.route("**/first-answer/draft", lambda route: route.fulfill(status=409, content_type="application/json",
                                                                  body='{"error": "stale"}'))
    sent = reports(page)
    page.fill("#first-answer-text", "Un cane")
    page.locator("#first-answer-retry-draft").wait_for(state="visible", timeout=15000)
    page.wait_for_timeout(2500)
    assert sent and not any(item.get("incidents") for item in sent)
