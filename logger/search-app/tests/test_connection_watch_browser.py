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


def test_a_server_that_stops_answering_shows_the_notice_after_two_signals(student_site):
    page, base, root = student_site
    page.clock.install()
    start(page, base, "1")
    page.route("**/presenza", lambda route: route.abort())
    page.clock.run_for(16000)
    page.wait_for_timeout(200)
    assert page.locator(NOTICE).count() == 0 or page.locator(NOTICE).is_hidden(), "one failed signal is not enough"
    page.clock.run_for(16000)
    page.locator(NOTICE).wait_for(state="visible")
    page.unroute("**/presenza")
    page.clock.run_for(6000)
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
    assert {"page": "/search", "visible": False} in signals
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
