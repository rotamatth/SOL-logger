"""Real fullscreen entry and navigation, with synthetic study storage only."""
import pytest

from .test_background_upload_browser import saved, search, student_site  # noqa: F401
from .test_editor_browser import until


def open_fullscreen(page, base, keyboard=False, entry="/welcome"):
    page.goto(base + entry)
    link = page.get_by_role("link", name="Inizia", exact=True)
    assert not page.evaluate("Boolean(document.fullscreenElement)")
    if keyboard:
        link.focus()
        page.keyboard.press("Enter")
    else:
        link.click()
    assert until(page, lambda: page.evaluate("Boolean(document.fullscreenElement)"))
    page.locator("#student-session-frame").wait_for()
    frame = page.frame_locator("#student-session-frame")
    frame.locator("#id-box").wait_for()
    return frame


def test_fullscreen_survives_answer_search_viewer_and_blocked_back(student_site):
    page, base, root = student_site
    frame = open_fullscreen(page, base)
    frame.locator("#id-box").select_option("1")
    frame.locator("#continue-btn").click()
    # Use the real Frame for the existing navigation helpers.
    child = page.frames[1]
    child.locator("#task-intro-continue").wait_for()
    while child.locator("#task-intro-continue").count():
        target = child.locator("#task-intro-continue").get_attribute("href")
        # The Back guard also emits same-document navigations during a tap.
        # Wait for the actual next route, rather than that history entry.
        with child.expect_navigation(url=base + target):
            child.locator("#task-intro-continue").click()
    child.locator("#first-answer-text").wait_for()
    page.evaluate("document.exitFullscreen()")
    child.locator("#first-answer-text").click()
    assert until(page, lambda: page.evaluate("Boolean(document.fullscreenElement)"))
    child.fill("#first-answer-text", "Laika")
    child.get_by_role("radio", name="Abbastanza giusta", exact=True).check()
    child.get_by_role("button", name="Conferma", exact=True).click()
    child.click("a#first-answer-search")
    child.wait_for_url("**/search*")
    page.evaluate("document.exitFullscreen()")
    search(child, "api miele")
    assert until(page, lambda: page.evaluate("Boolean(document.fullscreenElement)"))
    child.click("#abstract-link-1")
    child.wait_for_selector("#viewer-back-btn")
    assert page.evaluate("Boolean(document.fullscreenElement)")
    page.evaluate("document.exitFullscreen()")
    child.locator("#end-task-btn").click()
    assert until(page, lambda: page.evaluate("Boolean(document.fullscreenElement)"))
    child.locator("#continue-search-btn").click()
    viewer = child.url
    page.evaluate("history.back()")
    child.evaluate("window.studyLogger.sendLogs()")
    assert until(child, lambda: any(event["type"] == "browserBackBlocked"
                                   for event in saved(root, "1")))
    assert child.url == viewer
    child.click("#viewer-back-btn")
    child.wait_for_selector("article.content-section")
    assert page.evaluate("Boolean(document.fullscreenElement)")
    child.evaluate("window.studyLogger.sendLogs()")
    assert until(child, lambda: len([event for event in saved(root, "1")
                                   if event["type"] == "idSubmitted"]) == 1)


def test_keyboard_entry_and_exiting_fullscreen_keep_the_app_usable(student_site):
    page, base, _ = student_site
    frame = open_fullscreen(page, base, keyboard=True)
    page.evaluate("document.exitFullscreen()")
    assert not page.evaluate("Boolean(document.fullscreenElement)")
    frame.locator("#id-box").select_option("1")
    frame.locator("#continue-btn").click()
    frame.locator("#task-intro-continue").wait_for()
    assert frame.locator("#task-intro-continue").is_visible()
    assert until(page, lambda: page.evaluate("Boolean(document.fullscreenElement)"))


@pytest.mark.parametrize("interaction", ["click", "touch", "keyboard"])
def test_any_student_interaction_restores_the_outer_fullscreen(student_site, interaction):
    page, base, _ = student_site
    if interaction == "touch":
        context = page.context.browser.new_context(has_touch=True)
        page = context.new_page()
    frame = open_fullscreen(page, base)
    page.evaluate("document.exitFullscreen()")
    # Fullscreen must cover the host,
    # rather than the child document that is replaced on the next navigation.
    panel = frame.locator(".id-panel")
    if interaction == "touch":
        panel.tap(position={"x": 30, "y": 30})
    elif interaction == "keyboard":
        frame.locator("#continue-btn").focus()
        page.keyboard.press("a")
    else:
        panel.click(position={"x": 30, "y": 30})
    assert until(page, lambda: page.evaluate("document.fullscreenElement === document.documentElement"))
    if interaction == "touch":
        context.close()


def test_direct_student_page_can_enter_fullscreen_without_returning_to_welcome(student_site):
    page, base, _ = student_site
    page.goto(base + "/start")
    page.locator(".id-panel").click(position={"x": 30, "y": 30})
    assert until(page, lambda: page.evaluate("Boolean(document.fullscreenElement)"))


def test_native_select_retries_without_blocking_number_selection(student_site):
    page, base, _ = student_site
    frame = open_fullscreen(page, base)
    page.evaluate("document.exitFullscreen()")
    page.evaluate("""() => {
        window.fullscreenAttempts = 0;
        const original = document.documentElement.requestFullscreen;
        document.documentElement.requestFullscreen = function () {
            window.fullscreenAttempts++;
            return original.call(this);
        };
    }""")
    frame.locator("#id-box").click()
    # Chromium can refuse fullscreen while its native select menu is open.
    assert page.evaluate("window.fullscreenAttempts") >= 1
    page.keyboard.press("Escape")
    frame.locator("#id-box").select_option("1")
    frame.locator("#continue-btn").click()
    frame.locator("#task-intro-continue").wait_for()
    assert until(page, lambda: page.evaluate("Boolean(document.fullscreenElement)"))


def test_refused_retry_does_not_block_the_control_or_future_retries(student_site):
    page, base, _ = student_site
    frame = open_fullscreen(page, base)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.evaluate("""() => {
        window.realFullscreen = Element.prototype.requestFullscreen;
        Element.prototype.requestFullscreen = () => Promise.reject(new TypeError('Synthetic refusal'));
        return document.exitFullscreen();
    }""")
    frame.locator("#id-box").select_option("1")
    frame.locator("#continue-btn").click()
    frame.locator("#task-intro-continue").wait_for()
    assert not page.evaluate("Boolean(document.fullscreenElement)")
    page.evaluate("() => { Element.prototype.requestFullscreen = window.realFullscreen; }")
    frame.locator("h1").click()
    assert until(page, lambda: page.evaluate("Boolean(document.fullscreenElement)"))
    assert errors == []


@pytest.mark.parametrize("failure", ["unsupported", "disabled", "rejected", "throws", "legacy-only"])
def test_fullscreen_failure_still_opens_the_id_page(student_site, failure):
    page, base, _ = student_site
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_init_script("(() => { const failure = '" + failure + "';" + """
        Object.defineProperty(Element.prototype, 'webkitRequestFullscreen', {
            value: failure === 'legacy-only' ? () => {
                document.dispatchEvent(new Event('webkitfullscreenerror'));
            } : undefined
        });
        if (failure === 'unsupported' || failure === 'legacy-only') {
            Object.defineProperty(Element.prototype, 'requestFullscreen', {value: undefined});
        } else if (failure === 'disabled') {
            Object.defineProperty(document, 'fullscreenEnabled', {value: false});
        } else {
            Element.prototype.requestFullscreen = () => {
                if (failure === 'throws') throw new TypeError('Synthetic fullscreen rejection');
                return Promise.reject(new TypeError('Synthetic fullscreen rejection'));
            };
        }
    })();""")
    page.goto(base + "/welcome")
    assert errors == []
    page.get_by_role("link", name="Inizia", exact=True).click()
    page.wait_for_url("**/start")
    page.locator("#id-box").wait_for()
    assert not page.evaluate("Boolean(document.fullscreenElement)")
    assert errors == []


def test_embedded_welcome_reuses_the_same_host(student_site):
    page, base, _ = student_site
    frame = open_fullscreen(page, base)
    frame.get_by_role("link", name="Indietro", exact=False).click()
    frame.get_by_role("link", name="Inizia", exact=True).click()
    frame.locator("#id-box").wait_for()
    assert len(page.frames) == 2
    assert page.evaluate("Boolean(document.fullscreenElement)")


def test_reloading_a_host_opened_with_reset_preserves_the_new_attempt(student_site):
    page, base, _ = student_site
    frame = open_fullscreen(page, base, entry="/welcome?reset=1")
    frame.locator("#id-box").select_option("1")
    frame.locator("#continue-btn").click()
    frame.locator("#task-intro-continue").wait_for()
    page.reload()
    assert until(page, lambda: page.url == base + "/task/intro")
    assert page.locator("#task-intro-continue").is_visible()
