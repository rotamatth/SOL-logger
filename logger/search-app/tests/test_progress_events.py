"""Answer-event intents commit durably with answers and publish idempotently."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from .test_study_progress import QUESTIONS, make_store
from study_progress import AttemptKey, AttemptNotFound


def test_answer_events_survive_restart_with_original_context_and_no_duplicates(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    first = store.submit_first_answer(key, attempt_id, 1, "  Before\n")
    final = store.submit_final_answer(key, attempt_id, 1, "  After\n")
    events = store.pending_events(key, attempt_id)
    assert [event["type"] for event in events] == ["OwnKnowledgeAnswerSubmitted", "TaskEnded"]
    for event, answer, phase in zip(events, [first, final], ["pre-search", "post-search"]):
        payload = event["payload"]
        assert payload["event_id"] == event["event_id"]
        assert payload["timestamp"] == answer["submitted_at"] == event["created_at"]
        assert payload["answer"] == answer["text"] and payload["answerPhase"] == phase
        assert payload["uid"] == key.participant_id and payload["study_id"] == key.study_id
        assert payload["study_session_id"] == key.study_session_id
        assert payload["attempt_id"] == attempt_id and payload["is_test"] is False
        assert payload["task_number"] == 1 and payload["actual_topic_number"] == "3"
        assert payload["task_order"] == ["3", "1", "2"]
    assert events[0]["payload"]["outcome"] == "answered"
    reopened, _ = make_store(tmp_path)
    assert reopened.pending_events(key, attempt_id) == events
    assert reopened.submit_first_answer(key, attempt_id, 1, "  Before\n") == first
    assert reopened.submit_final_answer(key, attempt_id, 1, "  After\n") == final
    assert reopened.pending_events(key, attempt_id) == events


def test_unknown_answer_event_preserves_explicit_outcome_and_null_answer(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    store.submit_first_answer(key, attempt_id, 1, unknown_confirmed=True)
    event, = store.pending_events(key, attempt_id)
    assert event["payload"]["answer"] is None and event["payload"]["outcome"] == "unknown"


def test_drafts_and_invalid_submissions_do_not_enqueue_events(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    store.save_draft(key, attempt_id, 1, "first-answer", "Draft only", 0)
    with pytest.raises(ValueError):
        store.submit_first_answer(key, attempt_id, 1, " ")
    assert store.pending_events(key, attempt_id) == []


def test_acknowledgement_survives_restart_and_retries_without_resurrecting_events(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    store.submit_first_answer(key, attempt_id, 1, "Original")
    event, = store.pending_events(key, attempt_id)
    published_at = store.acknowledge_event(key, attempt_id, event["event_id"])
    assert published_at and store.pending_events(key, attempt_id) == []
    reopened, _ = make_store(tmp_path)
    assert reopened.acknowledge_event(key, attempt_id, event["event_id"]) == published_at
    reopened.submit_first_answer(key, attempt_id, 1, "Original")
    assert reopened.pending_events(key, attempt_id) == []


@pytest.mark.parametrize("other", [
    AttemptKey("other-study", "synthetic-1", "grade-4-session-1"),
    AttemptKey("study-2026", "other-child", "grade-4-session-1"),
    AttemptKey("study-2026", "synthetic-1", "other-session"),
    AttemptKey("study-2026", "synthetic-1", "grade-4-session-1", is_test=True),
])
def test_pending_events_and_acknowledgements_require_the_same_scope(tmp_path, other):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    store.submit_first_answer(key, attempt_id, 1, "Original")
    events = store.pending_events(key, attempt_id)
    with pytest.raises(AttemptNotFound):
        store.pending_events(other, attempt_id)
    with pytest.raises(AttemptNotFound):
        store.acknowledge_event(other, attempt_id, events[0]["event_id"])
    other_attempt = store.start_or_resume(other, QUESTIONS)["attempt_id"]
    with pytest.raises(ValueError):
        store.acknowledge_event(other, other_attempt, events[0]["event_id"])
    assert store.pending_events(key, attempt_id) == events


def test_test_events_are_labelled_and_retired_attempt_events_remain_publishable(tmp_path):
    store, _ = make_store(tmp_path)
    key = AttemptKey("study-2026", "TEST", "grade-4-session-1", is_test=True)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    store.submit_first_answer(key, attempt_id, 1, "Synthetic")
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE progress_attempts SET status = 'retired'")
    event, = store.pending_events(key, attempt_id)
    assert event["payload"]["is_test"] is True and event["payload"]["uid"] == "TEST"
    store.acknowledge_event(key, attempt_id, event["event_id"])
    assert store.get_attempt(key, attempt_id)["status"] == "retired"


def test_simultaneous_submission_retries_enqueue_one_event(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    workers = [make_store(tmp_path)[0] for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        answers = list(pool.map(lambda worker: worker.submit_first_answer(
            key, attempt_id, 1, "Same answer"), workers))
    assert all(answer == answers[0] for answer in answers)
    assert len(store.pending_events(key, attempt_id)) == 1


@pytest.mark.parametrize("phase", ["first-answer", "final-answer"])
def test_failed_event_insert_rolls_back_answer_and_progress_together(tmp_path, phase):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    if phase == "final-answer":
        store.submit_first_answer(key, attempt_id, 1, "Before")
    store.save_draft(key, attempt_id, 1, phase, "Recoverable draft", 0)
    before = store.get_attempt(key, attempt_id)
    pending = store.pending_events(key, attempt_id)
    with sqlite3.connect(store.path) as db:
        db.execute("""CREATE TRIGGER fail_event BEFORE INSERT ON progress_events
            BEGIN SELECT RAISE(ABORT, 'synthetic event failure'); END""")
    submit = store.submit_first_answer if phase == "first-answer" else store.submit_final_answer
    with pytest.raises(sqlite3.IntegrityError, match="synthetic event failure"):
        submit(key, attempt_id, 1, "Not committed")
    assert store.get_attempt(key, attempt_id) == before
    assert store.pending_events(key, attempt_id) == pending
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TRIGGER fail_event")
    submit(key, attempt_id, 1, "Retry")
    assert len(store.pending_events(key, attempt_id)) == len(pending) + 1


def test_version_three_backfills_all_original_events_in_question_order_once(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    for number in (1, 2, 3):
        store.submit_first_answer(key, attempt_id, number, f"Before {number}")
        store.submit_final_answer(key, attempt_id, number, f"After {number}")
    originals = store.get_attempt(key, attempt_id)
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TABLE IF EXISTS progress_events")
        db.execute("PRAGMA user_version=3")
    upgraded, _ = make_store(tmp_path)
    assert upgraded.runtime_settings()["schema_version"] == 4
    events = upgraded.pending_events(key, attempt_id)
    assert [event["payload"]["answer"] for event in events] == [
        "Before 1", "After 1", "Before 2", "After 2", "Before 3", "After 3"]
    assert upgraded.get_attempt(key, attempt_id) == originals
    assert len({event["event_id"] for event in events}) == 6
    for event in events:
        task = originals["tasks"][event["payload"]["task_number"] - 1]
        original = task["final_answer"] if event["type"] == "TaskEnded" else task["first_answer"]
        assert event["created_at"] == event["payload"]["timestamp"] == original["submitted_at"]
        upgraded.acknowledge_event(key, attempt_id, event["event_id"])
    reopened, _ = make_store(tmp_path)
    assert reopened.pending_events(key, attempt_id) == []


@pytest.mark.parametrize("operation", ["first-answer", "final-answer", "acknowledge"])
def test_commit_failure_keeps_answers_and_pending_events_recoverable(tmp_path, operation):
    store, key = make_store(tmp_path, timeout=0.01)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    if operation != "first-answer":
        store.submit_first_answer(key, attempt_id, 1, "Before")
    before = store.get_attempt(key, attempt_id)
    events = store.pending_events(key, attempt_id)
    if operation == "acknowledge":
        action = lambda: store.acknowledge_event(key, attempt_id, events[0]["event_id"])
    else:
        submit = store.submit_first_answer if operation == "first-answer" else store.submit_final_answer
        action = lambda: submit(key, attempt_id, 1, "Retryable")
    reader = sqlite3.connect(store.path)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM progress_events").fetchall()
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            action()
    finally:
        reader.rollback()
        reader.close()
    assert store.get_attempt(key, attempt_id) == before
    assert store.pending_events(key, attempt_id) == events
    action()
    assert len(store.pending_events(key, attempt_id)) == len(events) + (-1 if operation == "acknowledge" else 1)
