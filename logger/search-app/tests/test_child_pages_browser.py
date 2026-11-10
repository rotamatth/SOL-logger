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


def reach_review(page, base, first="Laika", final="Una cagnolina russa"):
    open_first(page, base)
    page.fill("#first-answer-text", first)
    page.get_by_role("radio", name="Abbastanza giusta", exact=True).check()
    page.get_by_role("button", name="Conferma", exact=True).click()
    page.locator("a#first-answer-search").wait_for()
    page.click("a#first-answer-search")
    page.wait_for_url("**/search")
    search(page, "api miele")
    page.click("#end-task-btn")
    page.fill("#textarea_feedback", final)
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


def reach_recap(page, base, first="Laika", final="Una cagnolina russa"):
    reach_review(page, base, first, final)
    for number in (2, 3):
        page.click("a.review-button")
        through_intro(page)
        page.fill("#first-answer-text", first)
        page.get_by_role("radio", name="Abbastanza giusta", exact=True).check()
        page.get_by_role("button", name="Conferma", exact=True).click()
        page.locator("a#first-answer-search").wait_for()
        page.click("a#first-answer-search")
        page.wait_for_url("**/search")
        search(page, "api miele")
        page.click("#end-task-btn")
        page.fill("#textarea_feedback", final)
        page.click("#feedback-btn")
        page.click("#yes-end-btn")
        page.wait_for_url(f"**/task-review/{number}")
        page.locator("a.review-button").wait_for()
    page.click("a.review-button")
    page.get_by_role("button", name="Salva l’attività").wait_for()
    page.wait_for_function("!document.querySelector('[data-action=finish]').disabled")


def recap_message(page):
    return page.locator("#recap-status").inner_text()


LONG = ("Il suono entra nell'orecchio e fa vibrare il timpano, poi gli ossicini portano la vibrazione fino alla "
        "coclea, che manda il segnale al cervello attraverso il nervo acustico. ") * 4


def boxes_overlap(a, b):
    return not (a["x"] + a["width"] <= b["x"] or b["x"] + b["width"] <= a["x"]
                or a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"])


def all_boxes(page, selector):
    found = page.locator(selector)
    return [found.nth(index).bounding_box() for index in range(found.count())]


@pytest.mark.parametrize("student_site", ["Spazio", "Orecchio"], indirect=True)
@pytest.mark.parametrize("size", SIZES)
def test_the_recap_fits_a_short_tablet_even_with_long_answers(student_site, size):
    page, base, _ = student_site
    page.set_viewport_size({"width": size[0], "height": size[1]})
    reach_recap(page, base, LONG[:160], LONG)
    for button in ("finish", "restart"):
        page.wait_for_function(f"!document.querySelector('[data-action={button}]')?.disabled")
        page.wait_for_function("[...document.images].every(image => image.complete)")
        fits(page, f"[data-action={button}]")
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
        boxes = all_boxes(page, ".recap-piece .review-card")
        assert len(boxes) == 6
        picture = page.locator(".recap-picture").bounding_box()
        for index, box in enumerate(boxes):
            # Every card stays inside the picture.
            assert (picture["x"] <= box["x"] and box["x"] + box["width"] <= picture["x"] + picture["width"]
                    and picture["y"] <= box["y"] and box["y"] + box["height"] <= picture["y"] + picture["height"] + 1), \
                f"card {index} leaves the picture"
            for other in boxes[index + 1:]:
                assert not boxes_overlap(box, other), "cards overlap"
        # The first answers form one row under the labels and the final answers one row along the bottom.
        before, after = all_boxes(page, ".recap-piece .review-before"), all_boxes(page, ".recap-piece .review-after")
        assert max(box["y"] for box in before) - min(box["y"] for box in before) <= 1
        assert (max(box["y"] + box["height"] for box in after) - min(box["y"] + box["height"] for box in after)) <= 1
        assert max(box["y"] + box["height"] for box in before) < min(box["y"] for box in after)
        # Even with long answers no card hides a magnifier, and the stars stay clear of the labels.
        magnifiers = all_boxes(page, ".recap-arrow circle[r='17']")
        assert len(magnifiers) == 3
        assert not any(boxes_overlap(card, glass) for card in boxes for glass in magnifiers), "a card hides a magnifier"
        labels = all_boxes(page, ".recap-piece .review-number")
        assert not any(boxes_overlap(stars, label) for stars in all_boxes(page, ".recap-confidence") for label in labels)
        assert all(label["y"] + label["height"] < card["y"] for label in labels for card in before)
        # A long answer scrolls inside its card, which keeps its place on the picture.
        answer = page.locator(".recap-piece .review-after p").first
        assert answer.evaluate("p => p.scrollHeight > p.clientHeight && getComputedStyle(p).overflowY === 'auto'")
        if button == "finish":
            page.get_by_role("button", name="Salva l’attività").click()
            page.get_by_text("La sessione è salvata.").wait_for()


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

    page.route("**/recap/finish", drop_once)
    with page.expect_response("**/recap/finish") as saved:
        page.get_by_role("button", name="Salva l’attività").click()
    assert saved.value.ok and drops
    page.get_by_text("La sessione è salvata.").wait_for()
    assert recap_message(page) == ""


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
def test_a_connection_that_stays_down_is_explained_in_italian(student_site):
    page, base, _ = student_site
    reach_recap(page, base)
    page.route("**/recap/finish", lambda route: route.abort("connectionreset"))
    finish = page.get_by_role("button", name="Salva l’attività")
    finish.click()
    page.wait_for_function("document.querySelector('#recap-status[data-error]')", timeout=15000)
    assert recap_message(page) == "Connessione non disponibile. Riprova."
    assert finish.is_enabled() and page.get_by_text("Una cagnolina russa").first.is_visible()
    page.unroute("**/recap/finish")
    with page.expect_response("**/recap/finish") as saved:
        finish.click()
    assert saved.value.ok
    page.get_by_text("La sessione è salvata.").wait_for()


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
def test_a_recap_the_server_no_longer_recognises_is_reopened(student_site):
    page, base, _ = student_site
    reach_recap(page, base)
    page.route("**/recap/finish", lambda route: route.fulfill(status=404, content_type="text/html", body="<p>Pagina non trovata</p>"))
    with page.expect_navigation():
        page.get_by_role("button", name="Salva l’attività").click()
    assert page.url.endswith("/thank_you")
    page.wait_for_function("!document.querySelector('[data-action=finish]').disabled")
    # Refused again within the minute, the page stays and says so instead of reloading for ever. Counted by
    # loads, since the back guard adds a history entry on the tap without leaving the page.
    reloads = []
    page.on("load", lambda loaded: reloads.append(loaded.url))
    page.get_by_role("button", name="Salva l’attività").click()
    page.wait_for_function("document.querySelector('#recap-status[data-error]')", timeout=15000)
    page.wait_for_timeout(1000)
    assert recap_message(page) == "Salvataggio non disponibile. Riprova."
    assert reloads == []


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
def test_the_recap_buttons_wait_for_their_script(student_site):
    page, base, _ = student_site
    reach_recap(page, base)
    held = []
    page.route("**/recap.js*", lambda route: held.append(route))
    page.reload(wait_until="commit")
    button = page.get_by_role("button", name="Salva l’attività")
    button.wait_for()
    assert button.is_disabled()
    page.wait_for_timeout(200)
    held[0].continue_()
    page.wait_for_function("!document.querySelector('[data-action=finish]').disabled")
    page.unroute("**/recap.js*")
    with page.expect_response("**/recap/finish") as saved:
        button.click()
    assert saved.value.ok


@pytest.mark.parametrize("student_site", ["Spazio"], indirect=True)
def test_a_lost_reply_to_a_draft_is_no_conflict(student_site):
    page, base, _ = student_site
    open_first(page, base)
    url = page.locator("#first-answer-draft-status").get_attribute("data-url")
    lost = []

    def lose_the_first_reply(route):
        if lost:
            route.continue_()
        else:
            lost.append(route.fetch().status)
            route.abort("connectionreset")

    page.route(f"**{url}", lose_the_first_reply)
    with page.expect_response(f"**{url}", timeout=15000) as repeated:
        page.fill("#first-answer-text", "Laika")
    assert lost == [200] and repeated.value.ok
    page.wait_for_timeout(200)
    assert page.locator("#first-answer-draft-status").inner_text() == ""
    assert page.locator("#first-answer-retry-draft").is_hidden()
