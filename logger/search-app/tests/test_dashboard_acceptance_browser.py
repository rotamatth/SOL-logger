"""Synthetic PC/touch layout and three-question workflow acceptance.

Chromium runs by default. Set SOL_ACCEPTANCE_WEBKIT=1 to repeat with WebKit;
this exercises the engine and touch viewport, not a physical iPad. Set
SOL_DASHBOARD_SCREENSHOTS to a temporary directory to retain full-page images.
"""
from copy import deepcopy
import os
from pathlib import Path
import threading

import pytest
from werkzeug.serving import make_server

from .enrollment_helpers import enroll_initial_roster
from .test_editor_browser import Live, REQUIRE_BROWSER_TESTS, app, playwright_api  # noqa: F401
from .test_research_dashboard import write_run
from .test_study_enrollment import question_set

YEAR = "2026/2027"
SESSION = "grade-4-session-1"
EDITOR = f"/dashboard/settings/questions/{SESSION}?prepare_session={SESSION}"
LONG_QUESTION = (
    "Imagine that your class is preparing an exhibition about how people can protect "
    "local rivers and lakes. You need to explain where the water comes from, how it is "
    "used in everyday life, and which changes could keep it clean for plants, animals "
    "and people. Compare information from different reliable sources and describe "
    "what you would recommend to another class. Explain why each recommendation "
    "would help, give a concrete example, and identify any information that you would "
    "still want to check before reaching a conclusion. "
) * 3


def acceptance_configuration(app):
    """Forty visible IDs, mixed log availability and realistically long questions."""
    state = app.extensions["research"]["state"]
    settings = state.settings()
    settings["ranges"] = [{"grade": "4", "start": 1, "end": 40, "prefix": "", "width": 0},
                          {"grade": "5", "start": 41, "end": 60, "prefix": "", "width": 0}]
    published = question_set("Water and the environment")
    for number, question in enumerate(published["questions"], 1):
        question.update(topic=f"Water, evidence and a practical recommendation {number}",
                        question=f"Question {number}. " + LONG_QUESTION)
    settings["sessions"][0].update(date="2026-10-15", name="Class research visit: water and the environment",
                                    question_set=published)
    enroll_initial_roster(settings, YEAR)
    state.save_settings(settings, settings["revision"])
    write_run(app, uid="1", suffix="acceptance-complete", date="2026-10-15", finish=True)
    write_run(app, uid="40", suffix="acceptance-incomplete", date="2026-10-15", answers=1)
    return deepcopy(published)


@pytest.fixture
def acceptance_live(app):
    acceptance_configuration(app)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    engine = "webkit" if os.environ.get("SOL_ACCEPTANCE_WEBKIT") == "1" else "chromium"
    try:
        with playwright_api.sync_playwright() as runner:
            try:
                browser = getattr(runner, engine).launch()
            except Exception as error:
                if REQUIRE_BROWSER_TESTS or engine == "webkit":
                    pytest.fail(f"{engine} acceptance browser is required: {error}", pytrace=False)
                pytest.skip(f"{engine} unavailable: {error}")
            context = browser.new_context()
            instance = Live(app, context, f"http://127.0.0.1:{server.server_port}")
            instance.engine = engine
            yield instance
            browser.close()
    finally:
        server.shutdown()


def assert_page_layout(page, label, errors):
    """Check page overflow and real accessible names on visible form controls."""
    page.evaluate("document.fonts.ready")
    result = page.evaluate("""() => {
      const visible = element => element.getClientRects().length > 0
        && getComputedStyle(element).visibility !== 'hidden';
      const named = element => {
        if ((element.getAttribute('aria-label') || '').trim()) return true;
        const ids = (element.getAttribute('aria-labelledby') || '').trim().split(/\\s+/);
        if (ids.some(id => (document.getElementById(id)?.textContent || '').trim())) return true;
        return Array.from(element.labels || []).some(label => label.textContent.trim());
      };
      return {
        width: innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        unlabeled: Array.from(document.querySelectorAll('input, select, textarea'))
          .filter(element => !['hidden','submit','button','reset'].includes(element.type)
            && visible(element) && !named(element))
          .map(element => element.id || element.name || element.tagName)
      };
    }""")
    assert result["scrollWidth"] <= result["width"] + 1, (label, result)
    assert result["unlabeled"] == [], (label, result["unlabeled"])
    assert errors == [], (label, errors)


def screenshot_if_requested(page, filename):
    destination = os.environ.get("SOL_DASHBOARD_SCREENSHOTS")
    if destination:
        output = Path(destination)
        output.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(output / (filename + ".png")), full_page=True)


@pytest.mark.parametrize("device,width,height,touch", [("pc", 1365, 1000, False),
                                                        ("tablet", 768, 1024, True),
                                                        ("phone", 390, 844, True)])
@pytest.mark.parametrize("language", ["en", "it"])
def test_dashboard_layout_and_three_question_edit_flow(acceptance_live, device, width, height, touch, language):
    live = acceptance_live
    browser = live.context.browser
    live.context.close()
    live.context = browser.new_context(viewport={"width": width, "height": height}, has_touch=touch)
    page = live.login()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    paths = {
        # Complete roster view is the explicit all-years scope. A year-scoped
        # history view intentionally contains only IDs with recorded runs.
        "overview": f"/dashboard?collection=study&grade=4&session={SESSION}",
        "prepare": f"/dashboard/prepare?grade=4&year={YEAR}&session={SESSION}",
        "sessions": f"/dashboard/settings?section=sessions&grade=4&year={YEAR}&session={SESSION}",
        "enrollment": f"/dashboard/settings/enrollment?grade=4&year={YEAR}&prepare_session={SESSION}",
        "editor": EDITOR,
    }
    for name, path in paths.items():
        response = page.goto(live.base + path + "&lang=" + language)
        assert response.status == 200, (device, language, name, response.status)
        assert_page_layout(page, (device, language, name), errors)
        screenshot_if_requested(page, f"{live.engine}-{language}-{device}-{name}")
        if name == "overview":
            assert page.locator("tbody tr").count() == 40

    # Save all three long questions, reopen the saved draft, then inspect each
    # researcher preview. The approved version stays intact throughout.
    state = live.app.extensions["research"]["state"]
    before = deepcopy(state.settings()["sessions"][0]["question_set"])
    edited = [item["question"] + f"\n\nAcceptance edit {number}: explain your reasoning."
              for number, item in enumerate(before["questions"], 1)]
    for slot, text in enumerate(edited):
        page.fill(f"[name=question_{slot}]", text)
    with page.expect_navigation() as saved:
        page.locator("button[value=save_draft]").click()
    assert saved.value.status == 200, page.locator(".notice.warning").all_text_contents()
    persisted = state.settings()["sessions"][0]
    assert [item["question"] for item in persisted["question_draft"]["questions"]] == edited
    assert persisted["question_set"] == before
    response = page.goto(live.base + EDITOR + "&lang=" + language)
    assert response.status == 200
    for slot, text in enumerate(edited):
        assert page.input_value(f"[name=question_{slot}]") == text
    assert_page_layout(page, (device, language, "saved editor"), errors)
    for number, text in enumerate(edited, 1):
        response = page.goto(live.base + f"/dashboard/prepare/{SESSION}/preview?mode=working&question={number}&lang={language}")
        assert response.status == 200
        assert page.locator(".preview-task-question").text_content() == text
        assert_page_layout(page, (device, language, f"preview {number}"), errors)
        screenshot_if_requested(page, f"{live.engine}-{language}-{device}-preview-{number}")
    response = page.goto(live.base + f"/dashboard/prepare/{SESSION}/preview?mode=published&question=1&lang={language}")
    assert response.status == 200
    assert page.locator(".preview-task-question").text_content() == before["questions"][0]["question"]
    assert live.dialogs == []
