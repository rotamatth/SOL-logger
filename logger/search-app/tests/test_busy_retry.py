"""When the server is busy recording the next step: "Un momento…", a page that tries again by itself.

Found in the rehearsal of 26 November: with 20 groups at once, opening the recap could not record the end of the
session for a moment, and the child got "Salvataggio non disponibile" with a "Torna alla ricerca" button although
every answer was saved. Now the same page load is tried again, by itself or with Riprova.
"""
import re

from .progress_helpers import confirm_first, final_event
from .test_connected_first_answer import events
from .test_study_enrollment import schedule, student_modules  # noqa: F401


def finished_questions(module):
    client = module.app.test_client()
    client.post("/start", data={"user_id": "1"})
    for number in (1, 2, 3):
        confirm_first(client)
        with client.session_transaction() as state:
            sid = state["session_id"]
        assert client.post("/log_session", json={"session_id": sid, "logs": [final_event(client, f"Final {number}")]}).status_code == 200
        client.get("/next_task")
    return client


def retry_box(page):
    box = re.search(r'id="busy-retry" data-retry-url="([^"]*)" data-auto="(\d)"', page.text)
    return box.group(1), box.group(2)


def test_a_busy_moment_at_the_recap_says_the_answers_are_saved_and_tries_the_recap_again(student_modules, monkeypatch):
    module = student_modules()
    schedule(module)
    client = finished_questions(module)
    with monkeypatch.context() as patch:
        patch.setattr(module.PROGRESS, "publish", lambda _: False)
        busy = client.get("/thank_you")
    assert busy.status_code == 503
    assert "Un momento" in busy.text and "Le tue risposte sono salvate" in busy.text
    assert "Torna alla ricerca" not in busy.text and "Riprova" in busy.text
    assert retry_box(busy) == ("/thank_you", "1"), "the same page, tried again by itself"
    assert "busy-retry.js" in busy.text
    again = client.get("/thank_you")
    assert again.status_code == 200 and 'data-action="finish"' in again.text, "the recap opens"
    assert len([e for e in events(module) if e["type"] == "sessionCompleted"]) == 1


def test_a_busy_moment_after_a_review_tries_the_same_step_again(student_modules, monkeypatch):
    module = student_modules()
    schedule(module)
    client = module.app.test_client()
    client.post("/start", data={"user_id": "1"})
    confirm_first(client)
    with client.session_transaction() as state:
        sid = state["session_id"]
    client.post("/log_session", json={"session_id": sid, "logs": [final_event(client, "Final 1")]})
    store = module.PROGRESS.store

    def busy(*_args, **_kwargs):
        raise OSError("database is locked")
    with monkeypatch.context() as patch:
        patch.setattr(store, "finish_review", busy)
        page = client.get("/next_task?review=1")
    assert page.status_code == 503 and retry_box(page) == ("/next_task?review=1", "1")
    assert client.get("/next_task?review=1").status_code == 302, "the review is finished on the next try"


def test_a_start_that_could_not_be_admitted_goes_back_to_the_id_page_without_reloading_itself(student_modules, monkeypatch):
    module = student_modules()
    schedule(module)
    client = module.app.test_client()

    def locked():
        raise TimeoutError("Admission busy")
    monkeypatch.setattr(module.PROGRESS, "admission_lock", locked)
    page = client.post("/start", data={"user_id": "1"})
    assert page.status_code == 503 and "Non si può ancora iniziare" in page.text
    assert "Le tue risposte sono salvate" not in page.text, "nothing is saved before a start"
    assert retry_box(page) == ("/start", "0"), "a form is never sent again by itself"
