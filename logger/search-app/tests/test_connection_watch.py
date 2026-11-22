"""The children's side of a dropped connection: the service worker, the offline page and the error page."""
import re
from pathlib import Path

import pytest

from .test_study_enrollment import question_set, schedule, student_modules  # noqa: F401

STATIC = Path(__file__).resolve().parents[1] / "static"


@pytest.fixture
def site(student_modules):
    module = student_modules()
    schedule(module, question_set())
    return module


def test_the_service_worker_is_served_from_the_root_and_never_cached(site):
    response = site.app.test_client().get("/sw.js")
    assert response.status_code == 200 and response.headers["Content-Type"].startswith("text/javascript")
    assert response.headers["Cache-Control"] == "no-cache"
    code = response.get_data(as_text=True)
    assert 'request.mode !== "navigate" || request.method !== "GET"' in code
    assert 'url.pathname.startsWith("/dashboard")' in code and "/static/offline.html" in code


def test_the_offline_page_needs_nothing_from_the_server():
    page = (STATIC / "offline.html").read_text()
    assert "Il collegamento non funziona." in page and "Alza la mano e chiama un adulto." in page
    assert not re.search(r'(src|href)="', page), "it must load without the server"
    assert "/health/ready" not in page, "polling the health check would take database locks"


def test_every_child_page_watches_the_connection():
    templates = Path(__file__).resolve().parents[1] / "templates"
    for name in ("layout.html", "first_answer.html", "task_intro.html", "study_handoff.html", "recap.html",
                 "practice_intro.html", "practice_done.html", "finished.html"):
        assert "connection-watch.js" in (templates / name).read_text(), name


def test_a_server_error_asks_for_an_adult(site):
    @site.app.get("/synthetic-failure")
    def failure():
        raise RuntimeError("synthetic")
    site.app.config["PROPAGATE_EXCEPTIONS"] = False
    site.app.config["TESTING"] = False
    page = site.app.test_client().get("/synthetic-failure")
    assert page.status_code == 500
    assert "Qualcosa non ha funzionato!" in page.text and "Alza la mano e chiama un adulto." in page.text
