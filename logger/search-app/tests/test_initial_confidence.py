"""Initial confidence is part of the original answer, never a separate submission."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from .test_study_progress import QUESTIONS, make_store
from .test_connected_first_answer import begin, context, events, Fields, module  # noqa: F401
from .test_study_enrollment import student_modules  # noqa: F401


@pytest.mark.parametrize("confidence", [None, 0, 4, True, "2", [], {}])
def test_typed_first_answer_requires_a_valid_confidence(tmp_path, confidence):
    store, key = make_store(tmp_path)
    attempt = store.start_or_resume(key, QUESTIONS)
    with pytest.raises(ValueError):
        store.submit_first_answer(key, attempt["attempt_id"], 1, "Laika", confidence=confidence)
    assert store.get_attempt(key, attempt["attempt_id"]) == attempt
    assert store.pending_events(key, attempt["attempt_id"]) == []


@pytest.mark.parametrize("confidence", [1, 2, 3])
def test_confidence_survives_restart_and_identical_retries_with_one_event(tmp_path, confidence):
    from study_progress import SubmissionConflict
    store, key = make_store(tmp_path)
    aid = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    answer = store.submit_first_answer(key, aid, 1, "  Laika\n", confidence=confidence)
    reopened, _ = make_store(tmp_path)
    assert reopened.get_attempt(key, aid)["tasks"][0]["first_answer"] == answer
    assert answer["confidence"] == confidence
    assert reopened.submit_first_answer(key, aid, 1, "  Laika\n", confidence=confidence) == answer
    with pytest.raises(SubmissionConflict):
        reopened.submit_first_answer(key, aid, 1, "  Laika\n", confidence=confidence % 3 + 1)
    queued = reopened.pending_events(key, aid)
    assert len(queued) == 1
    assert queued[0]["payload"]["confidence"] == confidence
    assert queued[0]["payload"]["outcome"] == "answered"


def test_unknown_has_no_confidence_and_rejects_a_fabricated_assessment(tmp_path):
    store, key = make_store(tmp_path)
    aid = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    with pytest.raises(ValueError):
        store.submit_first_answer(key, aid, 1, unknown_confirmed=True, confidence=1)
    answer = store.submit_first_answer(key, aid, 1, unknown_confirmed=True)
    assert answer["confidence"] is None
    assert store.pending_events(key, aid)[0]["payload"]["confidence"] is None


def test_competing_confidence_values_preserve_one_original(tmp_path):
    from study_progress import SubmissionConflict
    store, key = make_store(tmp_path)
    aid = store.start_or_resume(key, QUESTIONS)["attempt_id"]

    def submit(value):
        worker, _ = make_store(tmp_path)
        try:
            return worker.submit_first_answer(key, aid, 1, "Same text", confidence=value)
        except SubmissionConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted = [value for value in pool.map(submit, [1, 3]) if value is not None]
    assert len(accepted) == 1
    assert store.get_attempt(key, aid)["tasks"][0]["first_answer"] == accepted[0]
    assert len(store.pending_events(key, aid)) == 1


def test_confidence_answer_phase_and_outbox_roll_back_together(tmp_path):
    store, key = make_store(tmp_path)
    aid = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    before = store.get_attempt(key, aid)
    with sqlite3.connect(store.path) as db:
        db.execute("""CREATE TRIGGER fail_phase BEFORE UPDATE OF phase ON progress_attempts
            BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.submit_first_answer(key, aid, 1, "Laika", confidence=2)
    assert store.get_attempt(key, aid) == before
    assert store.pending_events(key, aid) == []


def test_draft_confidence_is_revisioned_and_blank_resets_it(tmp_path):
    store, key = make_store(tmp_path)
    aid = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    draft = store.save_draft(key, aid, 1, "first-answer", "Laika", 0, confidence=3)
    reopened, _ = make_store(tmp_path)
    assert reopened.get_attempt(key, aid)["tasks"][0]["drafts"]["first-answer"] == draft
    assert draft["confidence"] == 3
    assert reopened.get_attempt(key, aid)["phase"] == "first-answer"
    blank = store.save_draft(key, aid, 1, "first-answer", "  ", 1, confidence=3)
    assert blank["confidence"] is None


def test_version_four_upgrade_preserves_originals_pending_events_and_drafts(tmp_path):
    store, key = make_store(tmp_path)
    aid = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    store.save_draft(key, aid, 1, "first-answer", "Old draft", 0)
    store.submit_first_answer(key, aid, 1, "Old original", confidence=2)
    with sqlite3.connect(store.path) as db:
        db.execute("ALTER TABLE progress_first_answers DROP COLUMN confidence")
        db.execute("ALTER TABLE progress_drafts DROP COLUMN confidence")
        # Historical events had no assessment field; migration must not invent one.
        db.execute("UPDATE progress_events SET payload = json_remove(payload, '$.confidence')")
        db.execute("PRAGMA user_version=4")
    pending = store.pending_events(key, aid)
    reopened, _ = make_store(tmp_path)
    assert reopened.runtime_settings()["schema_version"] == 7
    snapshot = reopened.get_attempt(key, aid)
    assert snapshot["tasks"][0]["first_answer"]["text"] == "Old original"
    assert snapshot["tasks"][0]["first_answer"]["confidence"] is None
    assert snapshot["tasks"][0]["drafts"]["first-answer"]["text"] == "Old draft"
    assert snapshot["phase"] == "search"
    assert reopened.pending_events(key, aid) == pending
    assert reopened.submit_first_answer(key, aid, 1, "Old original") == snapshot["tasks"][0]["first_answer"]
    assert reopened.pending_events(key, aid) == pending


@pytest.mark.parametrize("confidence", [0, 4, True, "2", [], {}])
def test_invalid_draft_assessments_do_not_change_saved_data(tmp_path, confidence):
    store, key = make_store(tmp_path)
    aid = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    before = store.get_attempt(key, aid)
    with pytest.raises(ValueError):
        store.save_draft(key, aid, 1, "first-answer", "Laika", 0, confidence=confidence)
    assert store.get_attempt(key, aid) == before


def test_route_requires_assessment_and_logs_it_once_in_full_and_task_logs(module):
    client = begin(module)
    fields = Fields(client.get("/task").text).values
    data = {**fields, "outcome": "answered", "text": "Laika"}
    assert client.post("/first-answer", data=data).status_code == 400
    assert client.get("/search").status_code == 302
    assert client.post("/first-answer", data={**data, "confidence": "invalid"}).status_code == 400
    data["confidence"] = "2"
    assert client.post("/first-answer", data=data).status_code == 303
    assert client.post("/first-answer", data=data).status_code == 303
    assert client.post("/first-answer", data={**data, "confidence": "1"}).status_code == 409
    submitted = [e for e in events(module) if e["type"] == "OwnKnowledgeAnswerSubmitted"]
    assert len(submitted) == 1 and submitted[0]["confidence"] == 2
    assert submitted[0]["attempt_id"] == context(client)["attempt_id"]
    import json
    task_events = [json.loads(line) for path in module.LOG_STORE.root.glob("*_task*.log")
                   for line in path.read_text().splitlines()]
    assert [e for e in task_events if e["type"] == "OwnKnowledgeAnswerSubmitted"] == submitted


def test_failed_confirmation_preserves_text_and_assessment(module, monkeypatch):
    client = begin(module)
    fields = Fields(client.get("/task").text).values

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic failure")

    with monkeypatch.context() as patch:
        patch.setattr(module.PROGRESS.store, "submit_first_answer", fail)
        response = client.post("/first-answer", data={**fields, "outcome": "answered",
                               "text": "Keep this", "confidence": "3"})
    assert response.status_code == 503 and "Keep this</textarea>" in response.text
    assert 'value="3" required checked' in response.text
    assert client.get("/search").status_code == 302


def test_draft_route_restores_confidence_in_another_worker(module, student_modules):
    client = begin(module)
    fields = Fields(client.get("/task").text).values
    saved = client.post("/first-answer/draft", json={**fields, "text": "Laika", "confidence": 1, "revision": 0})
    assert saved.status_code == 200 and saved.json["confidence"] == 1
    assert client.post("/first-answer/draft", json={**fields, "text": "Laika", "confidence": 3, "revision": 0}).status_code == 409
    resumed = begin(student_modules())
    page = resumed.get("/task")
    assert "Laika</textarea>" in page.text and 'value="1" required checked' in page.text
    assert resumed.get("/search").status_code == 302


def test_task_page_concurrently_advanced_by_another_worker_resumes_safely(module, monkeypatch):
    client = begin(module)
    original = module.PROGRESS.store.mark_task_started

    def advance(key, aid, number):
        module.PROGRESS.store.submit_first_answer(key, aid, number, "Idea", confidence=2)
        module.PROGRESS.store.submit_final_answer(key, aid, number, "Final")
        return original(key, aid, number)

    monkeypatch.setattr(module.PROGRESS.store, "mark_task_started", advance)
    response = client.get("/task")
    assert response.status_code == 302
    with client.session_transaction() as state:
        assert state["task_position"] == 1


def test_transient_task_start_failure_cannot_put_submission_before_start(module, monkeypatch):
    client = begin(module)
    original = module.PROGRESS.store.mark_task_started

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic start failure")

    monkeypatch.setattr(module.PROGRESS.store, "mark_task_started", fail)
    page = client.get("/task")
    assert page.status_code == 503
    fields = Fields(page.text).values
    monkeypatch.setattr(module.PROGRESS.store, "mark_task_started", original)
    assert client.post("/first-answer", data={**fields, "outcome": "answered", "text": "Idea", "confidence": "2"}).status_code == 303
    assert [e["type"] for e in events(module) if e["type"] in ("TaskStarted", "OwnKnowledgeAnswerSubmitted")] == [
        "TaskStarted", "OwnKnowledgeAnswerSubmitted"]
