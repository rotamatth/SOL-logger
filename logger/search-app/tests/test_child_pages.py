"""The child's pages as designed in the Figma: the steps before each question, the review and the media."""
from pathlib import Path
import re

import pytest

from .progress_helpers import final_event
from .test_connected_first_answer import begin, first
from .test_study_enrollment import question_set, schedule, student_modules  # noqa: F401

STATIC = Path(__file__).resolve().parents[1] / "static"


@pytest.fixture
def site(student_modules):
    module = student_modules()
    schedule(module, {**question_set(), "theme": "orecchio"})
    return module


def task_started(module, client, number):
    with client.session_transaction() as state:
        attempt_id = state["progress_id"]
    return module.PROGRESS.store.task_started(attempt_id, number)


def finish_question(client, text):
    assert first(client, f"Prima {text}").status_code == 303
    event = final_event(client, text)
    assert client.post("/log_session", json={"session_id": event["sessionID"], "logs": [event]}).status_code == 200


def test_a_new_run_opens_with_cominciamo_then_the_question_then_the_form(site):
    client = site.app.test_client()
    start = client.post("/start", data={"user_id": "1"})
    assert start.location.endswith("/task/intro")
    welcome = client.get(start.location)
    assert "Cominciamo!" in welcome.text and "corpo umano" in welcome.text and "universo" not in welcome.text
    question = client.get(re.search(r'id="task-intro-continue"[^>]*href="([^"]+)"', welcome.text)[1].replace("&amp;", "&"))
    assert "Prova a rispondere alla domanda:" in question.text and "#1" in question.text
    assert "Cominciamo!" not in question.text
    assert re.search(r'id="task-intro-continue"[^>]*href="/task"', question.text)
    assert 'id="first-answer-form"' in client.get("/task").text


@pytest.mark.parametrize(("theme", "expected", "other"), [("spazio", "universo", "corpo umano"), ("Corpo umano (orecchio)", "corpo umano", "universo"),
                                                          ("Another theme", "tante cose da imparare", "universo")])
def test_cominciamo_speaks_of_the_sessions_own_theme(student_modules, theme, expected, other):
    module = student_modules()
    schedule(module, {**question_set(), "theme": theme})
    client = module.app.test_client()
    page = client.post("/start", data={"user_id": "1"}, follow_redirects=True)
    assert expected in page.text and other not in page.text


def test_task_started_is_logged_when_the_form_appears_not_on_the_introductions(site):
    client = begin(site)
    assert client.get("/task/intro").status_code == 200
    assert client.get("/task/intro?step=question").status_code == 200
    assert task_started(site, client, 1) is False
    assert client.get("/task").status_code == 200
    assert task_started(site, client, 1) is True


def test_a_begun_question_never_shows_its_introduction_again(site):
    client = begin(site)
    client.get("/task")
    assert client.get("/task/intro").location.endswith("/task")
    again = site.app.test_client().post("/start", data={"user_id": "1"})
    assert again.location.endswith("/task")


def test_the_next_question_has_its_introduction_but_no_second_cominciamo(site):
    client = begin(site)
    finish_question(client, "uno")
    review = client.get("/task")
    assert review.location.endswith("/task-review/1")
    following = client.get("/next_task?review=1")
    assert following.location.endswith("/task/intro")
    page = client.get(following.location)
    assert "Cominciamo!" not in page.text and "#2" in page.text and "Prova a rispondere" in page.text


def test_back_from_an_introduction_does_not_start_the_question(site):
    client = site.app.test_client()
    client.post("/start", data={"user_id": "1"})
    back = client.get("/start")
    assert back.status_code == 302 and back.location.endswith("/task/intro")
    assert not task_started(site, client, 1)
    client.get("/task")
    assert task_started(site, client, 1)
    assert client.get("/start").location.endswith("/task")


def test_the_introductions_need_a_run_and_expire_like_every_page(site):
    assert site.app.test_client().get("/task/intro").location.endswith("/welcome")


def test_the_search_button_appears_only_after_the_answer_is_confirmed(site):
    client = begin(site)
    form = client.get("/task").text
    assert 'id="first-answer-search"' not in form and "Conferma</button>" in form and "Conferma risposta" not in form
    assert first(client, "Un'idea").status_code == 303
    saved = client.get("/task").text
    assert '<a id="first-answer-search"' in saved and "<textarea" not in saved
    assert "La tua prima risposta è:" in saved and "la seguente" not in saved


def test_the_review_page_is_the_figmas_with_the_right_clip_and_still(site):
    client = begin(site)
    finish_question(client, "Dopo")
    with client.session_transaction() as state:
        slot = state["task_number"]
    page = client.get("/task-review/1").text
    assert f"/static/videos/review/Orecchio_0{slot}.mp4" in page and f"/static/images/review/ear-{slot}.webp" in page
    assert f"unlock--ear-{slot}" in page and "Avete sbloccato il primo riassunto delle vostre risposte!" in page
    assert "Prima Dopo" in page and "Dopo" in page
    assert "Rivedi la tua risposta" not in page and "controls" not in page


@pytest.mark.parametrize(("theme", "clip"), [("space", "Spazio"), ("ear", "Orecchio")])
@pytest.mark.parametrize("slot", ["1", "2", "3"])
def test_every_clip_and_still_is_there_and_nothing_needs_the_black_filter(theme, clip, slot):
    assert (STATIC / "videos" / "review" / f"{clip}_0{slot}.mp4").stat().st_size > 10_000
    assert (STATIC / "images" / "review" / f"{theme}-{slot}.webp").stat().st_size > 5_000
    assert f".unlock--{theme}-{slot} .review-animation" in (STATIC / "study-review.css").read_text()
    assert "remove-black" not in (STATIC / "study-review.css").read_text()
    assert not (STATIC / "review-animation-key.svg").exists()


def test_the_fonts_are_served_from_here(site):
    client = site.app.test_client()
    css = client.get("/static/main.css").text
    for name in re.findall(r'url\("(fonts/[^"]+)"\)', css):
        response = client.get(f"/static/{name}")
        assert response.status_code == 200 and len(response.data) > 1000
        response.close()
    assert "fonts.googleapis" not in css


def test_the_answer_page_does_not_repeat_the_introductions_question_or_show_small_hints(site):
    client = begin(site)
    form = client.get("/task").text
    # The introduction before it already asks "Pensi di sapere la risposta?".
    assert "Pensi di sapere la risposta a questa domanda?" not in form
    assert "Conferma la tua risposta per iniziare la ricerca." not in form and 'aria-describedby="first-answer-hint' not in form
    assert first(client, "Prima risposta").status_code == 303
    page = client.get("/task").text
    assert "La tua prima risposta è:" in page and "Prima risposta confermata." not in page


def test_the_error_pages_speak_italian(site):
    client = site.app.test_client()
    page = client.get("/non-esiste")
    assert page.status_code == 404
    assert "Pagina non trovata" in page.text and "Page Not Found" not in page.text


def test_the_search_results_page_has_no_english_labels(student_modules):
    from .test_student_security import searching_client
    client = searching_client(student_modules(), results=[{
        "docid": "1", "title": "Luna", "snippet": "Fasi", "link": "https://example.org/a", "displayed_link": "example.org"}])
    page = client.post("/result", data={"query": "luna"}).get_data(as_text=True)
    assert "<title>Cerca - Risultati</title>" in page
    assert "Search Results" not in page and "Page navigation" not in page and "Result thumbnail" not in page


def recap_page(module):
    from .test_editable_recap import complete_today
    client = begin(module)
    complete_today(client)
    return client, client.get("/thank_you").text


def test_the_recap_shows_todays_three_questions_on_the_whole_picture(site):
    client, page = recap_page(site)
    pieces = re.findall(r'class="recap-piece recap-piece--ear-(\d)" aria-labelledby="recap-question-(\d)"', page)
    assert sorted(slot for slot, _ in pieces) == ["1", "2", "3"] and sorted(number for _, number in pieces) == ["1", "2", "3"]
    for slot, number in pieces:
        # Each question sits on its own part of the picture, the part its review page showed, labelled by the order seen.
        assert f"unlock--ear-{slot}" in client.get(f"/task-review/{number}").text
        assert f'id="recap-question-{number}" title="Today question' in page and f">Domanda {number}</h2>" in page
    assert page.count('class="recap-arrow"') == 3 and "/static/images/review/ear-recap.webp" in page
    assert page.count('class="recap-confidence"') == 3 and page.count("Today original") == 3
    assert "Sessione" not in page and "<textarea" not in page and "Vedi l’originale" not in page
    assert 'data-action="finish"' in page and 'data-action="save"' not in page and "Scarica PDF" not in page


def test_a_theme_without_its_picture_shows_the_three_questions_side_by_side(student_modules):
    module = student_modules()
    schedule(module)
    _, page = recap_page(module)
    assert "recap-stage--plain" in page and 'class="recap-arrow"' not in page
    assert page.count('<section class="recap-piece"') == 3
