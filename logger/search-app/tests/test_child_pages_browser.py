"""The classroom tablets are shorter than an iPad: each step must fit without scrolling to the button."""
import pytest

from .progress_helpers import through_intro
from .test_background_upload_browser import search, student_site  # noqa: F401
from .test_first_answer_flow_browser import open_first

SIZES = [(1180, 699), (1280, 680), (1024, 520)]


def fits(page, button=None):
    extra = page.evaluate("document.documentElement.scrollHeight - innerHeight")
    assert extra <= 30, f"the page is {extra} px taller than the screen"
    if button:
        box = page.locator(button).bounding_box()
        assert box["y"] + box["height"] <= page.viewport_size["height"], f"{button} is below the screen"


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
@pytest.mark.parametrize("size", SIZES)
def test_every_step_of_a_question_fits_a_short_tablet(student_site, size):
    page, base, _ = student_site
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(base + "/start")
    page.select_option("#id-box", "1")
    page.click("#continue-btn")
    page.locator("#task-intro-continue").wait_for()
    fits(page, "#task-intro-continue")
    through_intro(page)
    fits(page, "#first-answer-confirm")
    assert page.locator("#first-answer-search").count() == 0
    page.fill("#first-answer-text", "Un cane di nome Laika, che è stato il primo animale nello spazio")
    page.get_by_role("radio", name="Abbastanza giusta", exact=True).check()
    fits(page, "#first-answer-confirm")
    assert page.locator(".first-answer-confidence").is_visible()
    page.get_by_role("button", name="Conferma", exact=True).click()
    page.locator("a#first-answer-search").wait_for()
    fits(page, "a#first-answer-search")
    page.click("a#first-answer-search")
    page.wait_for_url("**/search")
    search(page, "api miele")
    page.click("#end-task-btn")
    page.fill("#textarea_feedback", "Laika, una cagnolina russa")
    page.click("#feedback-btn")
    page.click("#yes-end-btn")
    page.wait_for_url("**/task-review/1")
    page.locator(".review-button").wait_for()
    fits(page, ".review-button")
    box = page.locator(".review-animation").bounding_box()
    assert box["height"] >= 0.5 * size[1] and box["y"] >= 0
    assert page.locator(".review-animation").evaluate("video => getComputedStyle(video).filter") == "none"
    for card in (".review-before", ".review-after"):
        assert page.locator(card).is_visible()


def reach_review(page, base):
    open_first(page, base)
    page.fill("#first-answer-text", "Laika")
    page.get_by_role("radio", name="Abbastanza giusta", exact=True).check()
    page.get_by_role("button", name="Conferma", exact=True).click()
    page.locator("a#first-answer-search").wait_for()
    page.click("a#first-answer-search")
    page.wait_for_url("**/search")
    search(page, "api miele")
    page.click("#end-task-btn")
    page.fill("#textarea_feedback", "Una cagnolina russa")
    page.click("#feedback-btn")
    page.click("#yes-end-btn")
    page.wait_for_url("**/task-review/1")
    page.locator("a.review-button").wait_for()


def overlap(page, first, second):
    a, b = page.locator(first).bounding_box(), page.locator(second).bounding_box()
    return not (a["x"] + a["width"] <= b["x"] or b["x"] + b["width"] <= a["x"]
                or a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"])


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
def test_a_tablet_that_blocks_autoplay_offers_a_button_clear_of_the_answers(student_site):
    page, base, _ = student_site
    page.add_init_script("HTMLMediaElement.prototype.play = () => Promise.reject(new DOMException('', 'NotAllowedError'))")
    reach_review(page, base)
    start = page.get_by_role("button", name="Avvia animazione")
    start.wait_for()
    assert page.locator(".review-actions .review-animation-start").count() == 1
    assert not overlap(page, ".review-animation-start", ".review-after")
    assert not overlap(page, ".review-animation-start", ".review-before")
    assert page.locator(".review-animation").get_attribute("poster")


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
def test_a_clip_that_cannot_load_leaves_its_still_and_no_dead_button(student_site):
    page, base, _ = student_site
    page.route("**/*.mp4*", lambda route: route.abort())
    reach_review(page, base)
    page.wait_for_function("document.querySelector('.review-animation').error !== null")
    page.wait_for_timeout(200)
    assert page.get_by_role("button", name="Avvia animazione").count() == 0
    assert page.locator("a.review-button").is_visible()


def test_a_mistaken_non_lo_so_has_two_equal_buttons(student_site):
    page, base, _ = student_site
    open_first(page, base)
    outline = page.locator("#first-answer-unknown").bounding_box()
    confirm = page.locator("#first-answer-confirm").bounding_box()
    assert outline["width"] == confirm["width"]
    page.locator("#first-answer-unknown").click()
    back = page.get_by_role("button", name="Torna alla risposta").bounding_box()
    sure = page.get_by_role("button", name="Confermo: non lo so").bounding_box()
    assert back["width"] == sure["width"] and back["height"] == sure["height"] and back["y"] == sure["y"]


def warning(page, field):
    return page.locator(field).first.evaluate("element => element.validationMessage")


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
def test_an_english_tablet_still_warns_in_italian(student_site):
    page, base, _ = student_site
    page.goto(base + "/start")
    page.click("#continue-btn")
    assert page.locator("#error-message").inner_text() == "Seleziona un numero"
    open_first(page, base)
    confirm = page.get_by_role("button", name="Conferma", exact=True)
    confirm.click()
    assert warning(page, "#first-answer-text") == "Scrivi una risposta oppure scegli “Non lo so”."
    page.fill("#first-answer-text", "Laika")
    assert warning(page, "#first-answer-text") == ""
    confirm.click()
    assert warning(page, "input[name=confidence]") == "Scegli quanto è giusta la tua risposta."
    assert page.locator("#first-answer-form").count() == 1
    page.get_by_role("radio", name="Abbastanza giusta", exact=True).check()
    assert warning(page, "input[name=confidence]") == ""
    confirm.click()
    page.locator("a#first-answer-search").wait_for()


def reach_recap(page, base):
    reach_review(page, base)
    for number in (2, 3):
        page.click("a.review-button")
        through_intro(page)
        page.fill("#first-answer-text", "Laika")
        page.get_by_role("radio", name="Abbastanza giusta", exact=True).check()
        page.get_by_role("button", name="Conferma", exact=True).click()
        page.locator("a#first-answer-search").wait_for()
        page.click("a#first-answer-search")
        page.wait_for_url("**/search")
        search(page, "api miele")
        page.click("#end-task-btn")
        page.fill("#textarea_feedback", "Una cagnolina russa")
        page.click("#feedback-btn")
        page.click("#yes-end-btn")
        page.wait_for_url(f"**/task-review/{number}")
        page.locator("a.review-button").wait_for()
    page.click("a.review-button")
    page.get_by_role("button", name="Salva l’attività").wait_for()


def editor_message(page):
    return page.locator("textarea[data-target]").first.evaluate("field => field.nextElementSibling.textContent")


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
def test_a_dropped_connection_on_the_recap_is_repeated_without_troubling_the_child(student_site):
    page, base, _ = student_site
    reach_recap(page, base)
    drops = []

    def drop_once(route):
        if not drops:
            drops.append(route.request.url)
            route.abort("connectionreset")
        else:
            route.continue_()

    page.route("**/recap/draft", drop_once)
    with page.expect_response("**/recap/draft") as saved:
        page.locator("textarea[data-target]").first.fill("Una cagnetta di nome Laika")
    assert saved.value.ok and drops
    page.wait_for_timeout(100)
    assert editor_message(page) == ""


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
def test_a_connection_that_stays_down_is_explained_in_italian_and_keeps_the_text(student_site):
    page, base, _ = student_site
    reach_recap(page, base)
    page.route("**/recap/draft", lambda route: route.abort("connectionreset"))
    field = page.locator("textarea[data-target]").first
    field.fill("Una cagnetta di nome Laika")
    page.wait_for_function("document.querySelector('textarea[data-target]').nextElementSibling.textContent !== ''", timeout=15000)
    assert editor_message(page) == "Connessione non disponibile. Il testo resta qui: riprova."
    assert field.input_value() == "Una cagnetta di nome Laika"
    page.unroute("**/recap/draft")
    with page.expect_response("**/recap/draft") as saved:
        page.get_by_role("button", name="Salva modifiche").click()
    assert saved.value.ok


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
def test_a_recap_the_server_no_longer_recognises_is_reopened(student_site):
    page, base, _ = student_site
    reach_recap(page, base)
    page.route("**/recap/draft", lambda route: route.fulfill(status=404, content_type="text/html", body="<p>Pagina non trovata</p>"))
    with page.expect_navigation():
        page.locator("textarea[data-target]").first.fill("Una cagnetta di nome Laika")
    assert page.url.endswith("/thank_you")
    assert page.locator("textarea[data-target]").first.input_value() == "Una cagnetta di nome Laika"
    # The text is sent again as the page opens. Refused again, the page stays and says so.
    reloads = []
    page.on("framenavigated", lambda frame: reloads.append(frame.url))
    page.wait_for_function("document.querySelector('textarea[data-target]').nextElementSibling.textContent !== ''", timeout=15000)
    page.wait_for_timeout(1000)
    assert editor_message(page) == "Salvataggio non disponibile. Riprova."
    assert reloads == []
    assert page.locator("textarea[data-target]").first.input_value() == "Una cagnetta di nome Laika"
