"""The end of the experiment: "Alzate la mano", and the tablet stays there until a researcher resets it."""
import re

import pytest

from .test_study_enrollment import question_set, schedule, student_modules  # noqa: F401


@pytest.fixture
def site(student_modules):
    module = student_modules()
    schedule(module, question_set())
    return module


def test_the_end_page_asks_the_group_to_raise_its_hand(site):
    page = site.app.test_client().get("/fine").text
    assert "Complimenti!<br>Siete arrivati alla fine!" in page
    assert "Alzate la mano per dire che avete finito!" in page
    assert re.search(r'id="finished-logo"[^>]*data-reset-url="/welcome\?reset=1"', page)
    assert "back-guard.js" in page and "finished.js" in page and "/static/logger.js" not in page


def test_the_end_page_clears_a_session_only_when_asked(site):
    client = site.app.test_client()
    client.post("/start", data={"user_id": "1"})
    client.get("/fine")
    with client.session_transaction() as saved:
        assert saved.get("user_id") == "1", "the recap's Chiudi clears the session itself"
    client.get("/fine?reset=1")
    with client.session_transaction() as saved:
        assert "user_id" not in saved


def test_the_older_ending_also_leads_to_the_end_page():
    from pathlib import Path
    handoff = (Path(__file__).resolve().parents[1] / "templates" / "study_handoff.html").read_text()
    assert "url_for('finished_page', reset=1)" in handoff and "url_for('welcome', reset=1" not in handoff


def test_the_question_introduction_no_longer_says_prova(site):
    client = site.app.test_client()
    client.post("/start", data={"user_id": "1"})
    page = client.get("/task/intro?step=question").text
    assert "#1" in page and "Pensi di sapere la risposta?" in page and "Prova a rispondere" not in page
