"""Final drafts are durable, scoped and never equivalent to confirmed answers."""
from datetime import datetime, timedelta
from html import unescape
import sqlite3

import pytest

from .test_connected_first_answer import module, begin, first, context, Fields, events  # noqa: F401
from .test_study_enrollment import student_modules  # noqa: F401


def draft_context(client):
    with client.session_transaction() as state:
        return {"csrf_token": state["progress_csrf"], "attempt_id": state["progress_id"],
                "question_number": state["task_position"] + 1}


def save(client, text="A final draft", revision=0, **overrides):
    return client.post("/final-answer/draft", json={**draft_context(client), "text": text,
                                                   "revision": revision, **overrides})


@pytest.mark.parametrize("unknown", [False, True])
def test_final_draft_is_separate_and_restores_for_a_fresh_worker(module, student_modules, unknown):
    client = begin(module)
    first(client, "Original first", outcome="unknown" if unknown else "answered")
    text = '  Final\n</textarea><script>alert("draft")</script>'
    result = save(client, text)
    assert result.status_code == 200 and result.json["text"] == text and result.json["revision"] == 1
    resumed = begin(student_modules())
    html = resumed.get("/search").text
    field = unescape(html.split('id="textarea_feedback"', 1)[1].split('>', 1)[1].split('</textarea>', 1)[0])
    assert field.removeprefix("\n") == text
    assert '<script>alert("draft")</script>' not in html
    assert 'id="final-answer-draft-status"' in html and 'data-revision="1"' in html
    assert context(resumed) == context(client)
    assert not [event for event in events(module) if event["type"] == "TaskEnded"]
    assert len([event for event in events(module) if event["type"] == "OwnKnowledgeAnswerSubmitted"]) == 1


def test_final_draft_cannot_bypass_first_answer_or_act_as_a_final_submission(module):
    client = begin(module)
    assert save(client).status_code == 409
    assert client.get("/search").status_code == 302
    first(client)
    assert save(client, "").status_code == 200
    assert client.get("/search").status_code == 200
    assert client.post("/end").status_code == 409
    assert context(client)["task_number"] == 1


@pytest.mark.parametrize("override,status", [
    ({"csrf_token": "wrong"}, 403), ({"attempt_id": "another"}, 409),
    ({"question_number": 2}, 409), ({"revision": True}, 400), ({"text": None}, 400),
])
def test_invalid_or_foreign_final_draft_context_is_rejected(module, override, status):
    client = begin(module)
    first(client)
    assert save(client, **override).status_code == status


def test_concurrent_browser_revisions_cannot_silently_replace_another_draft(module):
    client, other = begin(module), begin(module)
    first(client)
    assert save(client, "From one").status_code == 200
    assert save(other, "From stale browser").status_code == 409
    assert save(other, "From latest browser", revision=1).json["revision"] == 2
    assert save(client, "Stale again", revision=1).status_code == 409
    assert "From latest browser" in begin(module).get("/search").text


def test_final_draft_write_failure_is_not_acknowledged(module, monkeypatch):
    client = begin(module)
    first(client)
    monkeypatch.setattr(module.PROGRESS.store, "save_draft",
                        lambda *a, **kw: (_ for _ in ()).throw(sqlite3.OperationalError("synthetic")))
    assert save(client, "Keep this text").status_code == 503


def test_final_draft_read_failure_is_retryable_too(module, monkeypatch):
    client = begin(module)
    first(client)
    monkeypatch.setattr(module.PROGRESS.store, "get_attempt",
                        lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError("synthetic")))
    assert save(client, "Keep this text").status_code == 503


def test_confirmed_final_and_retired_attempt_reject_late_drafts(module):
    client = begin(module)
    first(client, "First original")
    save(client, "Earlier final draft")
    ctx = context(client)
    assert client.post("/log_session", json={"session_id": ctx["sessionID"], "logs": [
        {**ctx, "type": "TaskEnded", "answer": "Confirmed final original"}]}).status_code == 200
    assert save(client, "A late replacement", revision=1).status_code == 409
    with sqlite3.connect(module.PROGRESS.store.path) as db:
        db.execute("UPDATE progress_attempts SET status='retired' WHERE attempt_id=?", (ctx["attempt_id"],))
    assert save(client, "Retired replacement", revision=1).status_code == 409
    finals = [event for event in events(module) if event["type"] == "TaskEnded"]
    assert len(finals) == 1 and finals[0]["answer"] == "Confirmed final original"


def test_final_draft_date_boundary_and_participant_isolation(module, monkeypatch):
    import student_progress

    client, other = begin(module), begin(module, "2")
    first(client)
    first(other)
    assert save(client, "Private draft one").status_code == 200
    assert "Private draft one" not in other.get("/search").text

    class Tomorrow(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(days=1)

    monkeypatch.setattr(student_progress, "datetime", Tomorrow)
    assert save(client, "Too late", revision=1).status_code == 403
