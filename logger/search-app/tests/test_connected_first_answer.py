"""Real participant routes use durable answers, not browser flags, to unlock search."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from html.parser import HTMLParser
import json
import sqlite3
import re

import pytest

from .test_study_enrollment import question_set, schedule, student_modules  # noqa: F401


class Fields(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.values = {}
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type") == "hidden":
            self.values[attrs["name"]] = attrs.get("value", "")


@pytest.fixture
def module(student_modules):
    module = student_modules()
    schedule(module)
    return module


def begin(module, uid="1"):
    client = module.app.test_client()
    assert client.post("/start", data={"user_id": uid}).status_code == 302
    return client


def first(client, text="Un'idea", outcome="answered"):
    fields = Fields(client.get("/task").text).values
    return client.post("/first-answer", data={**fields, "outcome": outcome,
                       **({"text": text} if outcome == "answered" else {})})


def context(client):
    with client.session_transaction() as saved:
        return {"attempt_id": saved["progress_id"],
                "task_number": saved["task_position"] + 1,
                "sessionID": saved["session_id"], "uid": saved["user_id"]}


def events(module):
    return [json.loads(line) for path in module.LOG_STORE.root.glob("*_FULL.log")
            for line in path.read_text().splitlines()]


def test_real_task_page_opens_the_approved_first_answer_form(module):
    client = begin(module)
    page = client.get("/task")
    assert page.status_code == 200 and 'id="first-answer-form"' in page.text
    assert 'name="attempt_id"' in page.text and 'name="question_number"' in page.text
    assert "Today question" in page.text
    client.get("/task")
    started = [event for event in events(module) if event["type"] == "TaskStarted"]
    assert len(started) == 1 and started[0]["task_number"] == 1
    assert started[0]["attempt_id"] == context(client)["attempt_id"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}", started[0]["timestamp"])


@pytest.mark.parametrize("path", ["/search", "/result?query=blocked", "/webpage?url=https://example.org"])
def test_direct_search_routes_are_locked_before_a_persisted_answer(module, path):
    client = begin(module)
    response = client.get(path)
    assert response.status_code == 302 and response.location.endswith("/task")
    assert client.get("/autocomplete?q=blocked").json["suggestions"] == []
    assert client.get("/iframe_check?url=https://example.org").json["reason"] == "no-active-search"


def test_first_confirmation_and_retry_unlock_search_on_the_same_question_page(module):
    client = begin(module)
    fields = Fields(client.get("/task").text).values
    data = {**fields, "outcome": "answered", "text": "  Laika\n"}
    assert client.post("/first-answer", data=data).status_code == 303
    assert client.post("/first-answer", data=data).status_code == 303
    page = client.get("/task")
    assert "La mia prima risposta" in page.text and 'href="/search"' in page.text
    assert client.get("/search").status_code == 200
    submitted = [event for event in events(module) if event["type"] == "OwnKnowledgeAnswerSubmitted"]
    assert len(submitted) == 1 and submitted[0]["answer"] == "  Laika\n"
    assert submitted[0]["answerPhase"] == "pre-search"


def test_search_phase_cannot_be_rewound_by_a_late_browser_session_write(module):
    client = begin(module)
    assert first(client).status_code == 303
    assert client.get("/search").status_code == 200
    with client.session_transaction() as state:
        state["tasks_started"] = []
    module.search_backend.search = lambda query, page, rpp: (query, [], 0, "none")
    assert client.get("/result?query=still-searching").status_code == 200


def test_blank_unknown_csrf_and_stale_context_are_distinct(module):
    client = begin(module)
    fields = Fields(client.get("/task").text).values
    assert client.post("/first-answer", data={**fields, "outcome": "answered", "text": "  "}).status_code == 400
    assert client.post("/first-answer", data={**fields, "csrf_token": "wrong", "outcome": "unknown"}).status_code == 403
    assert client.post("/first-answer", data={**fields, "attempt_id": "another-attempt", "outcome": "unknown"}).status_code == 409
    assert client.get("/search").status_code == 302
    assert client.post("/first-answer", data={**fields, "outcome": "unknown"}).status_code == 303
    saved = [event for event in events(module) if event["type"] == "OwnKnowledgeAnswerSubmitted"]
    assert len(saved) == 1 and saved[0]["outcome"] == "unknown" and saved[0]["answer"] is None


def test_first_draft_survives_fresh_browser_worker_and_configuration_changes(module, student_modules):
    client = begin(module)
    page = client.get("/task")
    fields = Fields(page.text).values
    response = client.post("/first-answer/draft", json={**fields, "text": "Recoverable draft", "revision": 0})
    assert response.status_code == 200 and response.json["revision"] == 1
    assert client.post("/first-answer/draft", json={**fields, "text": "Stale", "revision": 0}).status_code == 409
    assert client.get("/search").status_code == 302
    original = context(client)
    schedule(module, shared=question_set("Changed"))
    other = begin(student_modules())
    resumed = other.get("/task")
    assert "Recoverable draft" in resumed.text and "Today question" in resumed.text
    assert "Changed question" not in resumed.text
    assert context(other) == original
    assert other.get("/search").status_code == 302


def test_first_save_failure_keeps_text_and_search_locked(module, monkeypatch):
    client = begin(module)
    client.get("/task")

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic failure")

    fields = Fields(client.get("/task").text).values
    monkeypatch.setattr(module.PROGRESS.store, "submit_first_answer", fail)
    monkeypatch.setattr(module.PROGRESS.store, "mark_task_started", fail)
    response = client.post("/first-answer", data={**fields, "outcome": "answered", "text": "Keep my answer"})
    assert response.status_code == 503 and "Keep my answer" in response.text
    assert 'id="first-answer-error"' in response.text
    assert client.get("/search").status_code == 302


def test_task_start_write_failure_renders_a_retryable_page(module, monkeypatch):
    client = begin(module)
    monkeypatch.setattr(module.PROGRESS.store, "mark_task_started",
                        lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError("synthetic")))
    assert client.get("/task").status_code == 503


@pytest.mark.parametrize("saved", [False, True])
def test_date_boundary_rejects_new_finals_but_allows_durable_retries(module, monkeypatch, saved):
    import student_progress

    class Tomorrow(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(days=1)

    client = begin(module)
    first(client)
    ctx = context(client)
    upload = {"session_id": ctx["sessionID"], "batch_id": "before-midnight",
              "logs": [{**ctx, "type": "TaskEnded", "answer": "Final original"}]}
    if saved:
        assert client.post("/log_session", json=upload).status_code == 200
    monkeypatch.setattr(student_progress, "datetime", Tomorrow)
    response = client.post("/log_session", json={**upload, "batch_id": "after-midnight"})
    assert response.status_code == (200 if saved else 403)
    assert len([event for event in events(module) if event["type"] == "TaskEnded"]) == int(saved)


def retire(module, client):
    with sqlite3.connect(module.PROGRESS.store.path) as db:
        db.execute("UPDATE progress_attempts SET status = 'retired' WHERE attempt_id = ?",
                   (context(client)["attempt_id"],))


def test_retired_attempt_cannot_search_or_restart_without_an_authorized_reset(module):
    client = begin(module)
    first(client)
    retire(module, client)
    assert client.get("/search").status_code == 302
    assert client.get("/result?query=blocked").status_code == 302
    assert client.get("/webpage?url=https://example.org").status_code == 302
    assert client.get("/autocomplete?q=blocked").json["suggestions"] == []
    assert client.get("/iframe_check?url=https://example.org").json["reason"] == "no-active-search"
    assert module.app.test_client().post("/start", data={"user_id": "1"}).status_code == 409
    with sqlite3.connect(module.PROGRESS.store.path) as db:
        assert db.execute("SELECT count(*) FROM progress_attempts").fetchone()[0] == 1


@pytest.mark.parametrize("invalid", [{"task_number": None}, {"sessionID": "another-run"}])
def test_final_requires_explicit_question_and_matching_technical_context(module, invalid):
    client = begin(module)
    first(client)
    ctx = context(client)
    event = {**ctx, "type": "TaskEnded", "answer": "After one"}
    assert client.post("/log_session", json={"session_id": ctx["sessionID"], "logs": [event]}).status_code == 200
    assert client.post("/end").status_code == 302
    first(client)
    ctx = context(client)
    event = {**ctx, "type": "TaskEnded", "answer": "Wrong context", **invalid}
    if invalid.get("task_number", 1) is None:
        del event["task_number"]
    assert client.post("/log_session", json={"session_id": ctx["sessionID"], "logs": [event]}).status_code == 400
    metadata = module.RESEARCH_STATE.attempt_metadata(ctx["sessionID"])
    attempt = module.PROGRESS.store.get_attempt(module.PROGRESS.key(metadata), ctx["attempt_id"])
    assert attempt["tasks"][1]["final_answer"] is None


def test_log_publication_failure_is_recovered_by_readiness_without_another_participant_request(module, monkeypatch):
    client = begin(module)
    client.get("/task")
    accept = module.LOG_STORE.accept

    def unavailable(run, batch, payload, prepare):
        if payload.get("type") == "OwnKnowledgeAnswerSubmitted":
            raise OSError("synthetic failure before log receipt")
        return accept(run, batch, payload, prepare)

    with monkeypatch.context() as patch:
        patch.setattr(module.LOG_STORE, "accept", unavailable)
        assert first(client, "Durably queued").status_code == 303
        assert not any(event["type"] == "OwnKnowledgeAnswerSubmitted" for event in events(module))
    assert module.LOG_STORE.accept == accept
    assert module.app.test_client().get("/health/ready").status_code == 200
    assert module.app.test_client().get("/health/ready").status_code == 200
    assert len([event for event in events(module) if event["type"] == "OwnKnowledgeAnswerSubmitted"]) == 1


def test_concurrent_starts_share_one_admission_and_logical_attempt(module, student_modules):
    other = student_modules()
    with ThreadPoolExecutor(max_workers=2) as pool:
        clients = list(pool.map(begin, [module, other]))
    assert context(clients[0]) == context(clients[1])
    with module.RESEARCH_STATE.connect() as db:
        assert db.execute("SELECT count(*) FROM study_attempts").fetchone()[0] == 1


def test_failed_progress_initialization_recovers_the_admitted_snapshot(module, monkeypatch):
    original = module.PROGRESS.store.start_or_resume
    with monkeypatch.context() as patch:
        patch.setattr(module.PROGRESS.store, "start_or_resume",
                      lambda *a, **kw: (_ for _ in ()).throw(sqlite3.OperationalError("synthetic")))
        failed = module.app.test_client().post("/start", data={"user_id": "1"})
        assert failed.status_code == 503
    assert module.PROGRESS.store.start_or_resume == original
    schedule(module, shared=question_set("Changed"))
    resumed = begin(module)
    assert "Today question" in resumed.get("/task").text
    with module.RESEARCH_STATE.connect() as db:
        assert db.execute("SELECT count(*) FROM study_attempts").fetchone()[0] == 1


def test_three_question_flow_saves_originals_once_and_skips_rewards(module):
    client = begin(module)
    for number in range(1, 4):
        assert f"#{number}" in client.get("/task").text
        assert first(client, f"Before {number}").status_code == 303
        assert client.get("/search").status_code == 200
        ctx = context(client)
        upload = {"session_id": ctx["sessionID"], "batch_id": f"final-{number}",
                  "logs": [{**ctx, "type": "TaskEnded", "answer": f"After {number}"}]}
        assert client.post("/log_session", json=upload).status_code == 200
        assert client.post("/log_session", json=upload).status_code == 200
        # A new batch retry must not append a second TaskEnded either.
        assert client.post("/log_session", json={**upload, "batch_id": f"retry-{number}"}).status_code == 200
        assert client.post("/end").status_code == 302
        assert client.get("/reward").status_code == 302
    complete = client.get("/task", follow_redirects=True)
    assert "Hai risposto alle tre domande" in complete.text
    own = events(module)
    assert [event["task_number"] for event in own if event["type"] == "TaskEnded"] == [1, 2, 3]
    assert all(event["answerPhase"] == "post-search" for event in own if event["type"] == "TaskEnded")
    assert not any(event["type"] == "rewardShown" for event in own)
    # Starting the same completed date cannot create another attempt.
    resumed = begin(module)
    assert "Hai risposto alle tre domande" in resumed.get("/task", follow_redirects=True).text


def test_invalid_batch_cannot_partially_confirm_a_final_answer(module):
    client = begin(module)
    first(client)
    client.get("/search")
    ctx = context(client)
    response = client.post("/log_session", json={"session_id": ctx["sessionID"], "batch_id": "invalid",
        "logs": [{**ctx, "type": "TaskEnded", "answer": "Must not be confirmed"},
                 {**ctx, "type": "querySubmitted", "attempt_id": "wrong-attempt"}]})
    assert response.status_code == 400
    metadata = module.RESEARCH_STATE.attempt_metadata(ctx["sessionID"])
    attempt = module.PROGRESS.store.get_attempt(module.PROGRESS.key(metadata), ctx["attempt_id"])
    assert attempt["tasks"][0]["final_answer"] is None
    assert not any(event["type"] == "TaskEnded" for event in events(module))


def test_final_upload_is_not_acknowledged_until_its_canonical_event_is_durable(module, monkeypatch):
    client = begin(module)
    first(client)
    ctx = context(client)
    upload = {"session_id": ctx["sessionID"], "batch_id": "lost-final-write",
              "logs": [{**ctx, "type": "TaskEnded", "answer": "Final original"}]}
    write = module.LOG_STORE._write

    def fail_final(name, offset, content):
        if '"type": "TaskEnded"' in content:
            raise OSError("synthetic")
        return write(name, offset, content)

    with monkeypatch.context() as patch:
        patch.setattr(module.LOG_STORE, "_write", fail_final)
        assert client.post("/log_session", json=upload).status_code == 503
    assert client.post("/log_session", json=upload).status_code == 200
    assert client.post("/log_session", json=upload).status_code == 200
    assert len([event for event in events(module) if event["type"] == "TaskEnded"]) == 1
