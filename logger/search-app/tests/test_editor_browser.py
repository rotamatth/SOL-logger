"""Researcher edit protection in a real browser (Chromium via Playwright).

These run the actual editor.js against a live dashboard and hold or fail requests
on purpose to reproduce the timing races that unit tests cannot reach. Missing
Playwright/Chromium skips locally; SOL_REQUIRE_BROWSER_TESTS=1 makes it an error.
"""
import os
import threading
import time
from urllib.parse import parse_qs, quote

import pytest
from werkzeug.serving import make_server

from .test_research_dashboard import PASSWORD, app  # noqa: F401 - pytest fixture
from .test_session_question_editor import URL, configured
from research_dashboard.editor_recovery import EditorRecovery

REQUIRE_BROWSER_TESTS = os.environ.get("SOL_REQUIRE_BROWSER_TESTS") == "1"
try:
    from playwright import sync_api as playwright_api
except ImportError:
    if REQUIRE_BROWSER_TESTS:
        pytest.fail("SOL_REQUIRE_BROWSER_TESTS=1 requires Playwright to be installed", pytrace=False)
    pytest.skip("Playwright is not installed", allow_module_level=True)

KEY = "questions:grade-4-session-1:"
RECOVERY = "/dashboard/editor/recovery"
EDITOR = URL + "?lang=en"


@pytest.fixture
def live(app):
    configured(app)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with playwright_api.sync_playwright() as runner:
            try:
                browser = runner.chromium.launch()
            except Exception as error:  # Chromium not installed on this machine.
                if REQUIRE_BROWSER_TESTS:
                    pytest.fail(f"Chromium is required by SOL_REQUIRE_BROWSER_TESTS=1: {error}", pytrace=False)
                pytest.skip(f"Chromium unavailable: {error}")
            context = browser.new_context()
            yield Live(app, context, f"http://127.0.0.1:{server.server_port}")
            browser.close()
    finally:
        server.shutdown()


class Live:
    def __init__(self, app, context, base):
        self.app, self.context, self.base = app, context, base
        self.dialogs = []

    def page(self):
        page = self.context.new_page()
        page.on("dialog", lambda dialog: (self.dialogs.append(dialog.message), dialog.dismiss()))
        return page

    def login(self, page=None):
        page = page or self.page()
        page.goto(self.base + "/dashboard/login?lang=en")
        page.fill("input[type=password]", PASSWORD)
        page.keyboard.press("Enter")
        page.wait_for_url(lambda url: "login" not in url)
        return page

    def server_copy(self):
        response = self.context.request.get(self.base + RECOVERY + "?key=" + quote(KEY))
        record = response.json()["recovery"]
        return (record or {}).get("fields") or {}

    def expire_logins(self):
        with self.app.extensions["research"]["state"].connect() as db:
            db.execute("DELETE FROM auth")


class Gate:
    """Hold matching requests until released (or fail them)."""

    def __init__(self, page, method, pattern="**" + RECOVERY + "**"):
        self.method, self.held, self.mode = method, [], "hold"
        page.route(pattern, self.handle)

    def handle(self, route):
        if route.request.method != self.method or self.mode == "open":
            route.continue_()
        elif self.mode == "fail":
            route.abort()
        else:
            self.held.append(route)

    def release(self):
        self.mode = "open"
        while self.held:
            self.held.pop(0).continue_()


def until(page, check, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return True
        page.wait_for_timeout(100)
    return check()


def tone(page):
    return page.get_attribute("[data-editor-status]", "data-tone")


def leave_by_link(page, href="/dashboard/?lang=en"):
    page.evaluate("""href => { const a = document.createElement('a'); a.id = 'leave'; a.href = href;
                     a.textContent = 'leave'; document.body.appendChild(a); }""", href)
    page.click("#leave")


def test_leaving_during_an_autosave_still_protects_the_latest_text(live):
    page = live.login()
    page.goto(live.base + EDITOR)
    until(page, lambda: tone(page) == "muted")
    gate = Gate(page, "POST")
    page.fill("[name=question_0]", "First words")
    assert until(page, lambda: gate.held), "autosave did not start"
    page.fill("[name=question_0]", "First words and the newest sentence")
    leave_by_link(page)
    page.wait_for_timeout(300)
    gate.release()
    page.wait_for_url("**/dashboard/?lang=en", timeout=8000)
    assert live.dialogs == []
    assert live.server_copy()["question_0"] == "First words and the newest sentence"


def test_typing_while_recovery_loads_is_saved_not_assumed_safe(live):
    page = live.login()
    gate = Gate(page, "GET")
    page.goto(live.base + EDITOR, wait_until="domcontentloaded")
    assert until(page, lambda: gate.held), "recovery check did not start"
    page.fill("[name=question_0]", "Typed while loading")
    gate.release()
    assert until(page, lambda: live.server_copy().get("question_0") == "Typed while loading")
    assert until(page, lambda: tone(page) == "ok")


def test_a_recovered_copy_never_replaces_text_typed_while_loading(live):
    page = live.login()
    page.goto(live.base + EDITOR)
    page.fill("[name=question_0]", "Earlier unsaved text")
    assert until(page, lambda: live.server_copy().get("question_0") == "Earlier unsaved text")
    gate = Gate(page, "GET")
    page.goto(live.base + EDITOR, wait_until="domcontentloaded")
    assert until(page, lambda: gate.held)
    page.fill("[name=question_0]", "New text")
    gate.release()
    page.wait_for_selector(".recovery-banner")
    assert page.input_value("[name=question_0]") == "New text"
    assert "Earlier unsaved text" in page.inner_text(".recovery-banner")
    assert until(page, lambda: live.server_copy().get("question_0") == "New text")
    page.click(".recovery-banner button.primary")  # The researcher can still choose the earlier text.
    assert page.input_value("[name=question_0]") == "Earlier unsaved text"


def test_a_stale_tab_never_overwrites_or_clears_a_newer_recovery_copy(live):
    first = live.login()
    first.goto(live.base + EDITOR)
    until(first, lambda: tone(first) == "muted")

    second = live.page()
    second.goto(live.base + EDITOR)
    second.fill("[name=question_0]", "Newer text from the other tab")
    assert until(second, lambda: live.server_copy().get("question_0") == "Newer text from the other tab")

    first.fill("[name=question_0]", "Old tab text")
    assert until(first, lambda: "Another tab" in first.inner_text("[data-editor-status]"))
    assert live.server_copy()["question_0"] == "Newer text from the other tab"
    # An explicit save from the stale tab is allowed, but the other tab's copy survives it.
    with first.expect_navigation():
        first.click("button[value=save_draft]")
    settings = live.app.extensions["research"]["state"].settings()
    assert settings["sessions"][0]["question_draft"]["questions"][0]["question"] == "Old tab text"
    assert live.server_copy()["question_0"] == "Newer text from the other tab"


def test_an_expired_login_keeps_entered_ids_and_submits_after_signing_in_again(live):
    year = live.app.extensions["research"]["state"].settings()["current_school_year"]
    page = live.login()
    page.goto(f"{live.base}/dashboard/settings/enrollment?lang=en&grade=4&year={year}")
    page.click("details.panel > summary")
    page.fill("#ids", "91, 92")
    before = page.url
    live.expire_logins()
    page.click("details.panel form button.primary")
    page.wait_for_selector(".editor-form-notice")
    assert page.url == before and page.input_value("#ids") == "91, 92"
    assert "sign-in expired" in page.inner_text(".editor-form-notice")

    live.login()  # Another tab, same browser.
    with page.expect_navigation():
        page.click("details.panel form button.primary")
    assert "login" not in page.url and not page.query_selector(".editor-form-notice")
    assert "91" in page.content() and "92" in page.content()


def recovery_choice(live):
    """Keep an earlier-copy banner visible while editing newer text."""
    page = live.context.new_page()
    page.on("dialog", lambda dialog: dialog.accept())
    live.login(page)
    page.goto(live.base + EDITOR)
    saved_question = page.input_value("[name=question_0]")
    page.fill("[name=question_0]", "Earlier recovered text")
    assert until(page, lambda: live.server_copy().get("question_0") == "Earlier recovered text")
    loading = Gate(page, "GET")
    page.goto(live.base + EDITOR, wait_until="domcontentloaded")
    assert until(page, lambda: loading.held)
    page.fill("[name=question_0]", "Newer text to discard")
    return page, loading, saved_question


def action(request):
    return parse_qs(request.post_data or "").get("action", [None])[0]


def test_discard_waits_for_an_autosave_acknowledgement_and_pauses_new_saves(live):
    page, loading, saved_question = recovery_choice(live)
    held = []
    clears = []

    def hold_save_response(route):
        if route.request.method == "POST" and action(route.request) == "save":
            # The server has committed the save; the page still knows the old sequence.
            held.append((route, route.fetch()))
        else:
            route.continue_()

    def clear_response(response):
        if response.request.method == "POST" and RECOVERY in response.url and action(response.request) == "clear":
            clears.append(response.status)

    page.route("**" + RECOVERY + "**", hold_save_response)
    page.on("response", clear_response)
    loading.release()
    page.wait_for_selector(".recovery-banner")
    assert until(page, lambda: held), "autosave did not reach the server"
    assert live.server_copy()["question_0"] == "Newer text to discard"
    page.get_by_role("button", name="Discard recovered edits", exact=True).click()
    page.fill("[name=question_0]", "Typed while discard was pending")
    page.wait_for_timeout(1500)
    assert len(held) == 1 and clears == [], "discard must wait without starting another save"

    route, response = held[0]
    with page.expect_navigation(wait_until="domcontentloaded"):
        route.fulfill(response=response)
    assert until(page, lambda: tone(page) == "muted")
    assert clears == [200]
    assert page.input_value("[name=question_0]") == saved_question
    assert live.server_copy() == {}


@pytest.mark.parametrize("failure", ["conflict", "expired", "storage", "network"])
def test_failed_discard_keeps_the_page_and_reports_why(live, monkeypatch, failure):
    page, loading, _ = recovery_choice(live)
    loading.release()
    page.wait_for_selector(".recovery-banner")
    assert until(page, lambda: tone(page) == "ok")
    assert live.server_copy()["question_0"] == "Newer text to discard"

    if failure == "conflict":
        other = live.page()
        other.goto(live.base + EDITOR)
        assert until(other, lambda: other.input_value("[name=question_0]") == "Newer text to discard")
        other.fill("[name=question_0]", "Other tab's newer recovery")
        assert until(other, lambda: live.server_copy().get("question_0") == "Other tab's newer recovery")
    elif failure == "expired":
        live.expire_logins()
    elif failure == "storage":
        def unavailable(*args, **kwargs):
            raise RuntimeError("Synthetic recovery storage failure")
        monkeypatch.setattr(EditorRecovery, "clear", unavailable)
    else:
        def offline(route):
            if route.request.method == "POST" and action(route.request) == "clear":
                route.abort()
            else:
                route.continue_()
        page.route("**" + RECOVERY + "**", offline)

    navigations = []
    page.on("framenavigated", lambda frame: navigations.append(frame.url) if frame == page.main_frame else None)
    page.get_by_role("button", name="Discard recovered edits", exact=True).click()
    assert until(page, lambda: tone(page) == "error")
    assert navigations == []
    assert page.input_value("[name=question_0]") == "Newer text to discard"
    message = page.inner_text("[data-editor-status]")
    if failure == "conflict":
        assert "Another tab" in message
        assert live.server_copy()["question_0"] == "Other tab's newer recovery"
    elif failure == "expired":
        assert "Sign in in another tab" in message
    else:
        assert "Unable to protect" in message
        assert live.server_copy()["question_0"] == "Newer text to discard"
