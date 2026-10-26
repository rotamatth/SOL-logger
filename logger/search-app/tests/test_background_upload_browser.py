"""Uploads during a task, in a real browser against the real student app.

The search provider is a synthetic stub and every external page is fulfilled
locally; storage lives in a temporary directory. No collection is touched.
"""
from datetime import datetime
from pathlib import Path
import importlib.util
import json
import sys
import threading
import types

import pytest
from werkzeug.serving import make_server

from .test_editor_browser import REQUIRE_BROWSER_TESTS, playwright_api, until
from .test_study_enrollment import schedule

APP_ROOT = Path(__file__).resolve().parents[1]
RESULTS = [{"docid": f"doc-{n}", "title": f"Synthetic result {n}", "snippet": f"Synthetic snippet {n}.",
            "link": f"https://synthetic.invalid/article-{n}", "displayed_link": "synthetic.invalid"}
           for n in (1, 2)]


@pytest.fixture
def student_site(tmp_path, monkeypatch):
    monkeypatch.chdir(APP_ROOT)
    for name, value in (("SOL_LOG_DIR", "v2"), ("RESEARCH_LEGACY_LOG_DIR", "legacy"),
                        ("RESEARCH_STATE_DIR", "state")):
        monkeypatch.setenv(name, str(tmp_path / value))
    backend = types.ModuleType("search_backend")
    backend.search = lambda query, page, rpp: (query, [dict(result) for result in RESULTS], len(RESULTS), "none")
    backend.autocomplete = lambda query: ([], "none")
    backend.autocomplete_query_model = lambda: None
    monkeypatch.setitem(sys.modules, "search_backend", backend)
    import flask_session
    original = flask_session.Session

    def isolated_session(app):
        app.config["SESSION_FILE_DIR"] = str(tmp_path / "student-sessions")
        return original(app)

    monkeypatch.setattr(flask_session, "Session", isolated_session)
    spec = importlib.util.spec_from_file_location("background_upload_student_app", APP_ROOT / "search_app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    schedule(module)
    server = make_server("127.0.0.1", 0, module.app, threaded=True)
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
            yield context.new_page(), f"http://127.0.0.1:{server.server_port}", tmp_path / "v2"
            browser.close()
    finally:
        server.shutdown()


def start(page, base, uid):
    page.goto(base + "/start")
    page.select_option("#id-box", uid)
    page.click("#continue-btn")
    page.wait_for_url("**/task")
    page.click("#task-btn")
    page.wait_for_url("**/search*")
    page.wait_for_load_state("load")


def saved(root, uid):
    events = []
    for path in root.glob(f"{uid}_*_FULL.log"):
        events.extend(json.loads(line) for line in path.read_text().splitlines())
    return events


def types_of(events, kind):
    return [event for event in events if event["type"] == kind]


def search(page, query):
    page.fill("#search-box", query)
    page.click("#submit-box")
    page.wait_for_selector("article.content-section")
    page.wait_for_load_state("load")


def test_events_are_saved_before_the_task_ends_and_survive_the_next_child(student_site):
    page, base, root = student_site
    start(page, base, "1")
    # Loading the search page already uploaded the start of the task.
    assert until(page, lambda: types_of(saved(root, "1"), "TaskStarted"))
    page.focus("#search-box")
    # The lesson ends: the iPad screen turns off while the child is still searching.
    page.evaluate("""() => {
        Object.defineProperty(document, 'visibilityState', {value: 'hidden', configurable: true});
        document.dispatchEvent(new Event('visibilitychange'));
    }""")
    assert until(page, lambda: types_of(saved(root, "1"), "queryBoxFocused"))
    # Later the iPad is reset and another child starts; the first child's events stay saved.
    page.goto(base + "/welcome?reset=1")
    start(page, base, "2")
    child = saved(root, "1")
    assert len(types_of(child, "TaskStarted")) == 1 and len(types_of(child, "queryBoxFocused")) == 1
    assert {event["uid"] for event in child} == {"1"}


def test_a_revisited_results_page_is_not_logged_as_new_results(student_site):
    page, base, root = student_site
    start(page, base, "1")
    search(page, "api miele")
    page.click("#abstract-link-1")
    page.wait_for_selector("#viewer-back-btn")
    page.wait_for_load_state("load")
    page.click("#viewer-back-btn")
    page.wait_for_selector("article.content-section")
    page.wait_for_load_state("load")
    page.evaluate("() => window.studyLogger.sendLogs()")
    events = saved(root, "1")
    # Two results were generated once; returning from the viewer is a revisit.
    assert len(types_of(events, "searchResultGenerated")) == len(RESULTS)
    assert len(types_of(events, "clickedResult")) == 1


def test_the_answer_is_saved_once_with_background_uploads(student_site):
    page, base, root = student_site
    start(page, base, "1")
    search(page, "api miele")
    page.click("#end-task-btn")
    page.fill("#textarea_feedback", "Le api producono il miele dal nettare.")
    page.click("#feedback-btn")
    page.click("#yes-end-btn")
    page.wait_for_url("**/reward")
    events = saved(root, "1")
    answers = types_of(events, "TaskEnded")
    assert [event["answer"] for event in answers] == ["Le api producono il miele dal nettare."]
    assert len(types_of(events, "searchResultGenerated")) == len(RESULTS)
    assert len(events) == len({json.dumps(event, sort_keys=True) for event in events})  # no duplicate events
    assert all(event["task_number"] == 1 for event in events)
    assert datetime.fromisoformat(answers[0]["timestamp"])
