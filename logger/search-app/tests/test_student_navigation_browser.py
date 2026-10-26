"""Synthetic replacement coverage for the two external-server Selenium suites.

Use the production templates and logger.js, with fixed local result/viewer routes.
No search provider, collection, account, participant files or external network is
used. Persisted pageshow is explicitly simulated; actual Safari BFCache remains a
device acceptance check.
"""
from pathlib import Path
from types import SimpleNamespace
import threading

from flask import Flask, jsonify, render_template, request, session
from markupsafe import escape
import pytest
from werkzeug.serving import make_server

from .test_editor_browser import REQUIRE_BROWSER_TESTS, playwright_api, until

APP_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def student_browser():
    app = Flask(__name__, template_folder=str(APP_ROOT / "templates"), static_folder=str(APP_ROOT / "static"))
    app.secret_key = "synthetic-navigation-signing-key"
    app.jinja_env.filters["rich_text"] = escape

    def render_student(template, **values):
        session.update(user_id="synthetic-navigation-id", task_number=1)
        return render_template(template, session_id="synthetic-server-session", **values)

    @app.get("/search")
    def search_page():
        return render_student("search.html", form=SimpleNamespace(hidden_tag=lambda: ""), search_results=[],
                    query="", corrected_query="", total_pages=1)

    @app.route("/result", methods=["GET", "POST"])
    def result():
        query = request.values.get("query", "Synthetic query")
        return render_student("search.html", form=SimpleNamespace(hidden_tag=lambda: ""), query=query,
                    corrected_query="Synthetic correction" if request.values.get("correction") else query,
                    raw_query=query, page=1, total_pages=1,
                    search_results=[{"docid": "synthetic-document", "title": "Synthetic result",
                                     "snippet": "A synthetic snippet with enough text to hover.",
                                     "link": "https://synthetic.invalid/article", "displayed_link": "synthetic.invalid"}])

    @app.get("/webpage")
    def webpage():
        return render_student("webpage.html", url=request.args["url"], query=request.args["query"], page=1)

    @app.get("/autocomplete")
    def autocomplete():
        return jsonify(suggestions=[], source="none", query_model=None)

    @app.get("/iframe_check")
    def iframe_check():
        return jsonify(blocked=False, reason="synthetic-preview")

    @app.post("/log_session")
    def log_session():
        return jsonify(status="ok")

    @app.get("/reward")
    def reward():
        return "synthetic reward"

    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with playwright_api.sync_playwright() as runner:
            try:
                browser = runner.chromium.launch()
            except Exception as error:
                if REQUIRE_BROWSER_TESTS:
                    pytest.fail(f"Chromium is required by SOL_REQUIRE_BROWSER_TESTS=1: {error}", pytrace=False)
                pytest.skip(f"Chromium unavailable: {error}")
            context = browser.new_context()
            context.route("https://**", lambda route: route.fulfill(status=200, body="Synthetic external page"))
            page = context.new_page()
            response = page.goto(f"http://127.0.0.1:{server.server_port}/search")
            assert response.status == 200
            page.fill("#search-box", "Synthetic query")
            page.click("#submit-box")
            page.wait_for_selector("article.content-section")
            page.wait_for_load_state("load")
            yield page
            browser.close()
    finally:
        server.shutdown()


def events(page, kind):
    return page.evaluate("kind => JSON.parse(localStorage.getItem('sessionLogs') || '[]').filter(e => e.type === kind)", kind)


def persisted_show(page):
    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")


def test_native_back_stays_in_viewer_and_logs_destination_with_stable_session(student_browser):
    page = student_browser
    original_session = page.evaluate("window.studyLogger.sessionID")
    assert len(events(page, "searchResultGenerated")) == 1
    link = page.locator("#abstract-link-1")
    target = link.get_attribute("href")
    link.click()
    page.wait_for_selector("#viewer-back-btn")
    page.wait_for_load_state("load")
    viewer = page.url
    page.evaluate("history.back()")
    assert until(page, lambda: events(page, "browserBackBlocked"))
    event = events(page, "browserBackBlocked")[-1]
    assert page.url == viewer
    assert event["fromURL"] == event["url"] == viewer
    assert event["toURL"] == event["targetURL"] == viewer
    assert events(page, "clickedResult")[-1]["navigationUrl"].endswith(target)
    assert events(page, "wentBack") == []
    assert page.evaluate("window.studyLogger.sessionID") == original_session


def test_repeated_viewer_returns_keep_one_result_log_and_one_hover_listener(student_browser):
    page = student_browser
    for _ in range(3):
        page.click("#abstract-link-1")
        page.wait_for_selector("#viewer-back-btn")
        page.wait_for_load_state("load")
        source = page.url
        target = page.locator("#viewer-back-btn").get_attribute("href")
        page.click("#viewer-back-btn")
        page.wait_for_selector("article.content-section")
        page.wait_for_load_state("load")
        event = events(page, "customBackButtonClicked")[-1]
        assert event["fromURL"] == source and event["toURL"].endswith(target)
    assert len(events(page, "searchResultGenerated")) == 1
    page.mouse.move(0, 0)
    before = len(events(page, "cursorEnteredSnippet"))
    page.locator("article.content-section").hover()
    assert until(page, lambda: len(events(page, "cursorEnteredSnippet")) > before)
    assert len(events(page, "cursorEnteredSnippet")) - before == 1
    assert len(events(page, "customBackButtonClicked")) == 3


def test_persisted_restore_recovers_last_allowed_url_and_logs_why(student_browser):
    page = student_browser
    source = page.url
    page.evaluate("sessionStorage.setItem('solLastAllowedAppUrl', location.origin + '/search')")
    persisted_show(page)
    page.wait_for_url("**/search")
    page.wait_for_load_state("load")
    event = events(page, "browserBackBlocked")[-1]
    assert event["fromURL"] == source
    assert event["toURL"].endswith("/search")
    assert event["reason"] == "pageshow"
    assert events(page, "wentBack") == []


def test_persisted_restore_resyncs_logs_and_keeps_authoritative_server_identity(student_browser):
    page = student_browser
    page.evaluate("""() => {
        localStorage.setItem('sessionID', 'stale-other-session');
        localStorage.setItem('sessionLogs', JSON.stringify([
          {type: 'idSubmitted', uid: 'synthetic-navigation-id'},
          {type: 'synthetic-stale-event', uid: 'other-participant'}
        ]));
    }""")
    persisted_show(page)
    assert page.evaluate("window.studyLogger.sessionID") == "synthetic-server-session"
    assert events(page, "synthetic-stale-event") == []
    assert len(events(page, "idSubmitted")) == 1
    # Stale events from the other session stay removed; this existing DOM does
    # not manufacture another result receipt during the state resynchronization.
    assert events(page, "searchResultGenerated") == []


def test_repeated_persisted_restores_do_not_duplicate_results_or_listeners(student_browser):
    page = student_browser
    page.goto(page.url + "?query=Synthetic+query&correction=1")
    page.wait_for_load_state("load")
    result_count = len(events(page, "searchResultGenerated"))
    correction_count = len(events(page, "generatedDidYouMean"))
    for _ in range(5):
        persisted_show(page)
    assert len(events(page, "searchResultGenerated")) == result_count
    assert len(events(page, "generatedDidYouMean")) == correction_count
    page.mouse.move(0, 0)
    before = len(events(page, "cursorEnteredSnippet"))
    page.locator("article.content-section").hover()
    assert until(page, lambda: len(events(page, "cursorEnteredSnippet")) > before)
    assert len(events(page, "cursorEnteredSnippet")) - before == 1
    page.mouse.move(0, 0)
    before = len(events(page, "hoverOverDidYouMean"))
    page.locator("#did-you-mean").hover()
    assert until(page, lambda: len(events(page, "hoverOverDidYouMean")) > before)
    assert len(events(page, "hoverOverDidYouMean")) - before == 1
    page.goto(page.url.split("/result")[0] + "/result?query=Different+synthetic+query")
    page.wait_for_load_state("load")
    assert len(events(page, "searchResultGenerated")) == result_count + 1
    assert events(page, "searchResultGenerated")[-1]["query"] == "Different synthetic query"
