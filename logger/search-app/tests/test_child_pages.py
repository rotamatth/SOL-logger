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
    assert "La tua prima risposta è la seguente:" in saved


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


def test_the_confirmed_answer_no_longer_asks_whether_the_child_knows_it(site):
    client = begin(site)
    prompt = "Pensi di sapere la risposta a questa domanda?"
    assert prompt in client.get("/task").text
    assert first(client, "Prima risposta").status_code == 303
    page = client.get("/task").text
    assert prompt not in page and "La tua prima risposta è la seguente:" in page

