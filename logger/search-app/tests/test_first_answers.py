"""Confirmed first answers stay distinct from drafts and survive retries."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from .test_study_progress import QUESTIONS, make_store


def test_confirmed_first_answer_survives_restart_without_replacing_the_draft(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    draft = store.save_draft(key, attempt_id, 1, "first-answer", "An earlier idea", 0)
    answer = store.submit_first_answer(key, attempt_id, 1, "  La mia risposta è questa.\n")
    reopened, _ = make_store(tmp_path)
    saved = reopened.get_attempt(key, attempt_id)
    assert answer["text"] == "  La mia risposta è questa.\n"
    assert answer["outcome"] == "answered"
    assert saved["tasks"][0]["first_answer"] == answer
    assert saved["tasks"][0]["drafts"]["first-answer"] == draft
    assert saved["tasks"][1]["first_answer"] is None
    assert saved["phase"] == "search" and saved["question_number"] == 1


def test_confirmed_unknown_is_distinct_from_an_empty_draft(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    store.save_draft(key, attempt_id, 1, "first-answer", "", 0)
    answer = store.submit_first_answer(key, attempt_id, 1, unknown_confirmed=True)
    assert answer["outcome"] == "unknown" and answer["text"] is None
    assert store.get_attempt(key, attempt_id)["phase"] == "search"
    assert store.submit_first_answer(key, attempt_id, 1, unknown_confirmed=True) == answer


@pytest.mark.parametrize("text, unknown", [
    (None, False), ("", False), ("  \n\t", False), (42, False),
    ("An answer", True), ("", True), (None, 1),
])
def test_invalid_submission_keeps_first_answer_phase_and_saved_draft(tmp_path, text, unknown):
    store, key = make_store(tmp_path)
    attempt = store.start_or_resume(key, QUESTIONS)
    store.save_draft(key, attempt["attempt_id"], 1, "first-answer", "Recoverable draft", 0)
    before = store.get_attempt(key, attempt["attempt_id"])
    with pytest.raises(ValueError):
        store.submit_first_answer(key, attempt["attempt_id"], 1, text, unknown_confirmed=unknown)
    assert store.get_attempt(key, attempt["attempt_id"]) == before


def test_same_submission_retry_returns_original_and_conflicting_retry_is_rejected(tmp_path):
    from study_progress import SubmissionConflict
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    original = store.submit_first_answer(key, attempt_id, 1, "Original answer")
    assert store.submit_first_answer(key, attempt_id, 1, "Original answer") == original
    with pytest.raises(SubmissionConflict):
        store.submit_first_answer(key, attempt_id, 1, "A different answer")
    with pytest.raises(SubmissionConflict):
        store.submit_first_answer(key, attempt_id, 1, unknown_confirmed=True)
    assert store.get_attempt(key, attempt_id)["tasks"][0]["first_answer"] == original


def test_late_first_draft_is_rejected_and_final_draft_remains_separate(tmp_path):
    from study_progress import SubmissionConflict
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    store.save_draft(key, attempt_id, 1, "first-answer", "Draft", 0)
    original = store.submit_first_answer(key, attempt_id, 1, "Confirmed")
    with pytest.raises(SubmissionConflict):
        store.save_draft(key, attempt_id, 1, "first-answer", "Late autosave", 1)
    final = store.save_draft(key, attempt_id, 1, "final-answer", "After searching", 0)
    saved = store.get_attempt(key, attempt_id)
    assert saved["tasks"][0]["first_answer"] == original
    assert saved["tasks"][0]["drafts"]["final-answer"] == final


@pytest.mark.parametrize("number", [0, 2, 4, True])
def test_submission_cannot_skip_the_current_question(tmp_path, number):
    store, key = make_store(tmp_path)
    attempt = store.start_or_resume(key, QUESTIONS)
    with pytest.raises(ValueError):
        store.submit_first_answer(key, attempt["attempt_id"], number, "Answer")
    assert store.get_attempt(key, attempt["attempt_id"]) == attempt


def test_another_participant_cannot_submit_to_the_attempt(tmp_path):
    from study_progress import AttemptKey, AttemptNotFound
    store, key = make_store(tmp_path)
    attempt = store.start_or_resume(key, QUESTIONS)
    other = AttemptKey("study-2026", "synthetic-2", "grade-4-session-1")
    with pytest.raises(AttemptNotFound):
        store.submit_first_answer(other, attempt["attempt_id"], 1, "Wrong participant")
    assert store.get_attempt(key, attempt["attempt_id"]) == attempt


def test_simultaneous_confirmation_retries_create_one_original_answer(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    workers = [make_store(tmp_path)[0] for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        answers = list(pool.map(
            lambda worker: worker.submit_first_answer(key, attempt_id, 1, "Same answer"), workers))
    assert all(answer == answers[0] for answer in answers)
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM progress_first_answers").fetchone()[0] == 1


def test_competing_submissions_preserve_one_original_answer(tmp_path):
    from study_progress import SubmissionConflict
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    workers = [make_store(tmp_path)[0] for _ in range(2)]

    def submit(item):
        worker, text = item
        try:
            return worker.submit_first_answer(key, attempt_id, 1, text)
        except SubmissionConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, zip(workers, ["Answer A", "Answer B"])))
    accepted = [answer for answer in results if answer is not None]
    assert len(accepted) == 1
    saved = store.get_attempt(key, attempt_id)
    assert saved["tasks"][0]["first_answer"] == accepted[0]
    assert saved["phase"] == "search"


@pytest.mark.parametrize("status", ["completed", "retired"])
def test_inactive_attempt_rejects_new_submissions_and_identical_retries(tmp_path, status):
    from study_progress import SubmissionConflict
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    original = store.submit_first_answer(key, attempt_id, 1, "Original")
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE progress_attempts SET status = ? WHERE attempt_id = ?", (status, attempt_id))
    before = store.get_attempt(key, attempt_id)
    for number, text in [(1, "Original"), (2, "New answer")]:
        with pytest.raises(SubmissionConflict):
            store.submit_first_answer(key, attempt_id, number, text)
    assert store.get_attempt(key, attempt_id) == before
    assert before["tasks"][0]["first_answer"] == original


def test_delayed_identical_retry_does_not_rewind_the_next_question(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    original = store.submit_first_answer(key, attempt_id, 1, "Original")
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE progress_attempts SET question_number = 2, phase = 'first-answer'")
    before = store.get_attempt(key, attempt_id)
    assert store.submit_first_answer(key, attempt_id, 1, "Original") == original
    assert store.get_attempt(key, attempt_id) == before


def test_phase_update_failure_rolls_back_the_inserted_answer(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    store.save_draft(key, attempt_id, 1, "first-answer", "Recoverable draft", 0)
    before = store.get_attempt(key, attempt_id)
    with sqlite3.connect(store.path) as db:
        db.execute("""CREATE TRIGGER reject_search_phase BEFORE UPDATE OF phase
            ON progress_attempts WHEN NEW.phase = 'search'
            BEGIN SELECT RAISE(ABORT, 'synthetic phase failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic phase failure"):
        store.submit_first_answer(key, attempt_id, 1, "Not committed")
    assert store.get_attempt(key, attempt_id) == before
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM progress_first_answers").fetchone()[0] == 0
        db.execute("DROP TRIGGER reject_search_phase")
    assert store.submit_first_answer(key, attempt_id, 1, "Retry")["text"] == "Retry"


def test_failed_commit_keeps_draft_and_does_not_unlock_search(tmp_path):
    store, key = make_store(tmp_path, timeout=0.01)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    store.save_draft(key, attempt_id, 1, "first-answer", "Keep this draft", 0)
    before = store.get_attempt(key, attempt_id)
    reader = sqlite3.connect(store.path)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM progress_attempts").fetchall()
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            store.submit_first_answer(key, attempt_id, 1, "Save failed")
    finally:
        reader.rollback()
        reader.close()
    assert store.get_attempt(key, attempt_id) == before
    assert store.submit_first_answer(key, attempt_id, 1, "Retry")["text"] == "Retry"


def test_version_one_database_upgrades_without_changing_existing_progress(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    store.save_draft(key, attempt_id, 1, "first-answer", "Version one draft", 0)
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TABLE IF EXISTS progress_first_answers")
        db.execute("PRAGMA user_version=1")
    upgraded, _ = make_store(tmp_path)
    saved = upgraded.get_attempt(key, attempt_id)
    assert upgraded.runtime_settings()["schema_version"] == 2
    assert [task["snapshot"] for task in saved["tasks"]] == QUESTIONS
    assert saved["tasks"][0]["drafts"]["first-answer"]["text"] == "Version one draft"
    assert saved["phase"] == "first-answer"
    assert upgraded.submit_first_answer(key, attempt_id, 1, "Still works")["text"] == "Still works"
