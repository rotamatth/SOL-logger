"""A confirmed "Non lo so" can become a written answer once, before the question's first search, and nothing is overwritten."""
import sqlite3

import pytest

from .progress_helpers import HiddenFields
from .test_connected_first_answer import begin, events, first
from .test_study_enrollment import question_set, schedule, student_modules  # noqa: F401

RESULT = {"title": "Laika", "snippet": "Il primo animale", "link": "https://synthetic.invalid/laika", "docid": "1"}


@pytest.fixture
def site(student_modules):
    module = student_modules()
    schedule(module, question_set())
    module.search_backend.search = lambda query, page, rpp, theme=None: (query, [dict(RESULT)], 1, "none")
    return module


@pytest.fixture
def unknown(site):
    client = begin(site)
    assert first(client, outcome="unknown").status_code == 303
    return client


def change(client, text="Un cane, Laika", confidence="2", **extra):
    fields = HiddenFields(client.get("/task?change=1").text).values
    return client.post("/first-answer/change", data={**fields, "text": text, "confidence": confidence, **extra})


def attempt_of(site, client):
    with client.session_transaction() as saved:
        attempt_id = saved["progress_id"]
    with sqlite3.connect(site.PROGRESS.store.path) as db:
        db.row_factory = sqlite3.Row
        original = db.execute("SELECT * FROM progress_first_answers WHERE attempt_id=?", (attempt_id,)).fetchone()
        changes = db.execute("SELECT * FROM progress_first_answer_changes WHERE attempt_id=?", (attempt_id,)).fetchall()
    return dict(original), [dict(row) for row in changes]


def test_after_non_lo_so_the_group_can_choose_to_write_an_answer(unknown):
    saved = unknown.get("/task").text
    assert "La tua prima risposta è:" in saved and "Non lo so" in saved
    assert 'id="first-answer-change" class="app-btn first-answer-outline" href="/task?change=1"' in saved
    form = unknown.get("/task?change=1").text
    assert 'action="/first-answer/change"' in form and 'id="first-answer-unknown"' not in form
    assert "first-answer-unknown-dialog" not in form and 'id="first-answer-change-cancel"' in form
    assert 'href="/task"' in form and "Secondo te, quanto è giusta la tua risposta?" in form


def test_the_written_answer_replaces_non_lo_so_and_the_original_stays(site, unknown):
    assert change(unknown).location.endswith("/task")
    saved = unknown.get("/task").text
    assert "Un cane, Laika" in saved and 'id="first-answer-change"' not in saved
    original, changes = attempt_of(site, unknown)
    assert (original["outcome"], original["text"], original["confidence"]) == ("unknown", None, None)
    assert [(row["text"], row["confidence"]) for row in changes] == [("Un cane, Laika", 2)]


def test_both_answers_are_logged_as_their_own_events(site, unknown):
    change(unknown)
    logged = events(site)
    submitted = [event for event in logged if event["type"] == "OwnKnowledgeAnswerSubmitted"]
    changed = [event for event in logged if event["type"] == "OwnKnowledgeAnswerChanged"]
    assert len(submitted) == 1 and submitted[0]["outcome"] == "unknown" and submitted[0]["answer"] is None
    assert len(changed) == 1
    assert (changed[0]["answer"], changed[0]["confidence"], changed[0]["outcome"], changed[0]["previousOutcome"],
            changed[0]["answerPhase"], changed[0]["source"]) == ("Un cane, Laika", 2, "answered", "unknown",
                                                                 "pre-search", "server")


def test_after_the_first_search_non_lo_so_stays(site, unknown):
    assert unknown.post("/result", data={"query": "primo animale spazio"}).status_code == 200
    assert 'id="first-answer-change"' not in unknown.get("/task").text
    assert 'action="/first-answer/change"' not in unknown.get("/task?change=1").text
    fields = HiddenFields(unknown.get("/search").text).values
    refused = unknown.post("/first-answer/change", data={**fields, "csrf_token": csrf(unknown),
                                                         "attempt_id": attempt_id(unknown), "question_number": "1",
                                                         "text": "Troppo tardi", "confidence": "1"})
    assert refused.status_code == 303
    assert attempt_of(site, unknown)[1] == []


def test_the_search_note_holds_after_the_session_is_lost(site, unknown):
    unknown.post("/result", data={"query": "primo animale spazio"})
    resumed = begin(site)
    assert 'id="first-answer-change"' not in resumed.get("/task").text


def test_the_search_page_offers_the_change_until_the_first_search(unknown):
    home = unknown.get("/search").text
    assert 'id="search-change-answer"' in home and 'href="/task?change=1"' in home
    assert "Cambia la mia risposta" in home
    assert 'id="search-first-answer-btn"' not in home, "one button at the top right: the change, not the pop-up"
    results = unknown.post("/result", data={"query": "laika"}).text
    assert 'id="search-change-answer"' not in results and 'id="search-first-answer-btn"' in results
    home = unknown.get("/search").text
    assert 'id="search-change-answer"' not in home and 'id="search-first-answer-btn"' in home


def test_the_search_page_offers_no_change_for_a_written_answer(site):
    client = begin(site)
    assert first(client).status_code == 303
    home = client.get("/search").text
    assert 'id="search-change-answer"' not in home and 'id="search-first-answer-btn"' in home


def test_the_search_page_offers_no_change_once_changed(site, unknown):
    assert change(unknown).status_code == 303
    assert 'id="search-change-answer"' not in unknown.get("/search").text


def test_a_written_first_answer_never_changes(site):
    client = begin(site)
    first(client, "Un gatto")
    assert 'id="first-answer-change"' not in client.get("/task").text
    assert 'action="/first-answer/change"' not in client.get("/task?change=1").text
    assert 'id="search-change-answer"' not in client.get("/search").text


@pytest.mark.parametrize(("text", "confidence"), [("   ", "2"), ("Laika", ""), ("Laika", "5")])
def test_a_change_needs_text_and_stars(site, unknown, text, confidence):
    refused = change(unknown, text=text, confidence=confidence)
    assert refused.status_code == 400 and "Scrivi una risposta e scegli quanto è giusta." in refused.text
    assert 'action="/first-answer/change"' in refused.text
    assert attempt_of(site, unknown)[1] == []


def test_a_change_needs_the_pages_token(site, unknown):
    assert change(unknown, csrf_token="wrong").status_code == 403
    assert attempt_of(site, unknown)[1] == []


def test_only_one_change_and_a_retry_adds_nothing(site, unknown):
    fields = HiddenFields(unknown.get("/task?change=1").text).values
    data = {**fields, "text": "Laika", "confidence": "3"}
    assert unknown.post("/first-answer/change", data=data).status_code == 303
    assert unknown.post("/first-answer/change", data=data).status_code == 303
    assert unknown.post("/first-answer/change", data={**data, "text": "Un altro"}).status_code == 303
    assert [row["text"] for row in attempt_of(site, unknown)[1]] == ["Laika"]
    assert len([event for event in events(site) if event["type"] == "OwnKnowledgeAnswerChanged"]) == 1


def test_a_tablet_cannot_upload_its_own_change_event(site, unknown):
    with unknown.session_transaction() as saved:
        forged = {"type": "OwnKnowledgeAnswerChanged", "answer": "Falso", "attempt_id": saved["progress_id"],
                  "task_number": 1, "uid": saved["user_id"], "sessionID": saved["session_id"]}
        session_id = saved["session_id"]
    assert unknown.post("/log_session", json={"session_id": session_id, "logs": [forged]}).status_code == 200
    assert not [event for event in events(site) if event["type"] == "OwnKnowledgeAnswerChanged"]
    assert attempt_of(site, unknown)[1] == []


def test_the_recap_and_the_store_show_the_written_answer(site, unknown):
    change(unknown, text="Laika")
    with unknown.session_transaction() as saved:
        key = site.PROGRESS.key({"study_id_at_collection": saved["progress_study_id"], "participant_id": saved["user_id"],
                                 "study_session_at_collection": saved["progress_session_id"],
                                 "is_test": saved.get("progress_is_test", False)})
        attempt = site.PROGRESS.store.get_attempt(key, saved["progress_id"])
    first_answer = attempt["tasks"][0]["first_answer"]
    assert (first_answer["outcome"], first_answer["text"], first_answer["confidence"]) == ("answered", "Laika", 2)
    assert first_answer["changed_from"]["outcome"] == "unknown"


def test_the_progress_schema_version_is_unchanged(site):
    with sqlite3.connect(site.PROGRESS.store.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 7


def csrf(client):
    with client.session_transaction() as saved:
        return saved["progress_csrf"]


def attempt_id(client):
    with client.session_transaction() as saved:
        return saved["progress_id"]
