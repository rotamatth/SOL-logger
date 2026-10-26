"""Original final answers and question transitions survive retries and failures."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from study_progress import AttemptKey, AttemptNotFound, SubmissionConflict
from .test_study_progress import QUESTIONS, make_store


def ready_question(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    store.submit_first_answer(key, attempt_id, 1, "Before searching")
    return store, key, attempt_id


def test_final_answer_preserves_both_originals_and_drafts_after_restart(tmp_path):
    store, key, attempt_id = ready_question(tmp_path)
    first = store.get_attempt(key, attempt_id)["tasks"][0]["first_answer"]
    draft = store.save_draft(key, attempt_id, 1, "final-answer", "Earlier draft", 0)
    answer = store.submit_final_answer(key, attempt_id, 1, "  Final answer.\n")
    reopened, _ = make_store(tmp_path)
    saved = reopened.get_attempt(key, attempt_id)
    assert answer["text"] == "  Final answer.\n" and answer["submitted_at"]
    assert saved["tasks"][0]["first_answer"] == first
    assert saved["tasks"][0]["final_answer"] == answer
    assert saved["tasks"][0]["drafts"]["final-answer"] == draft
    assert saved["tasks"][1]["final_answer"] is None
    assert saved["question_number"] == 2 and saved["phase"] == "first-answer"
    assert [task["snapshot"] for task in saved["tasks"]] == QUESTIONS


@pytest.mark.parametrize("text", [None, "", " \n\t", 42])
def test_invalid_final_answer_does_not_change_progress_or_draft(tmp_path, text):
    store, key, attempt_id = ready_question(tmp_path)
    store.save_draft(key, attempt_id, 1, "final-answer", "Keep my draft", 0)
    before = store.get_attempt(key, attempt_id)
    with pytest.raises(ValueError):
        store.submit_final_answer(key, attempt_id, 1, text)
    assert store.get_attempt(key, attempt_id) == before


@pytest.mark.parametrize("number", [0, 2, 4, True])
def test_final_answer_cannot_skip_or_reuse_an_invalid_question_number(tmp_path, number):
    store, key, attempt_id = ready_question(tmp_path)
    before = store.get_attempt(key, attempt_id)
    with pytest.raises(ValueError):
        store.submit_final_answer(key, attempt_id, number, "Answer")
    assert store.get_attempt(key, attempt_id) == before


@pytest.mark.parametrize("phase", ["first-answer", "search"])
def test_final_answer_requires_a_persisted_first_submission(tmp_path, phase):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    store.save_draft(key, attempt_id, 1, "first-answer", "Only a draft", 0)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE progress_attempts SET phase = ?", (phase,))
    before = store.get_attempt(key, attempt_id)
    with pytest.raises(SubmissionConflict):
        store.submit_final_answer(key, attempt_id, 1, "Too early")
    assert store.get_attempt(key, attempt_id) == before


def test_three_questions_finish_in_recap_and_identical_retries_do_not_advance(tmp_path):
    store, key = make_store(tmp_path)
    attempt_id = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    for number in (1, 2, 3):
        store.submit_first_answer(key, attempt_id, number, unknown_confirmed=True)
        answer = store.submit_final_answer(key, attempt_id, number, f"Final {number}")
        saved = store.get_attempt(key, attempt_id)
        assert saved["question_number"] == min(number + 1, 3)
        assert saved["phase"] == ("recap" if number == 3 else "first-answer")
        assert saved["status"] == ("completed" if number == 3 else "active")
        assert store.submit_final_answer(key, attempt_id, number, f"Final {number}") == answer
        assert store.get_attempt(key, attempt_id) == saved
    assert store.start_or_resume(key, None) == saved
    assert [task["final_answer"]["text"] for task in saved["tasks"]] == ["Final 1", "Final 2", "Final 3"]
    with pytest.raises(SubmissionConflict):
        store.submit_final_answer(key, attempt_id, 3, "Replace completed answer")
    assert store.get_attempt(key, attempt_id) == saved


@pytest.mark.parametrize("phase", ["first-answer", "recap"])
def test_final_answer_requires_search_even_when_first_answer_exists(tmp_path, phase):
    store, key, attempt_id = ready_question(tmp_path)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE progress_attempts SET phase = ?", (phase,))
    before = store.get_attempt(key, attempt_id)
    with pytest.raises(SubmissionConflict):
        store.submit_final_answer(key, attempt_id, 1, "Wrong phase")
    assert store.get_attempt(key, attempt_id) == before


def test_final_original_cannot_be_replaced_by_a_retry_or_late_autosave(tmp_path):
    store, key, attempt_id = ready_question(tmp_path)
    store.submit_final_answer(key, attempt_id, 1, "Original final answer")
    before = store.get_attempt(key, attempt_id)
    with pytest.raises(SubmissionConflict):
        store.submit_final_answer(key, attempt_id, 1, "Replacement")
    with pytest.raises(SubmissionConflict):
        store.save_draft(key, attempt_id, 1, "final-answer", "Late autosave", 0)
    assert store.get_attempt(key, attempt_id) == before
    assert store.save_draft(key, attempt_id, 2, "first-answer", "Next draft", 0)["text"] == "Next draft"


@pytest.mark.parametrize("same_text", [True, False])
def test_concurrent_final_submissions_advance_only_once(tmp_path, same_text):
    store, key, attempt_id = ready_question(tmp_path)
    workers = [make_store(tmp_path)[0] for _ in range(2)]
    texts = ["Answer A", "Answer A" if same_text else "Answer B"]

    def submit(item):
        worker, text = item
        try:
            return worker.submit_final_answer(key, attempt_id, 1, text)
        except SubmissionConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, zip(workers, texts)))
    accepted = [answer for answer in results if answer is not None]
    assert len(accepted) == (2 if same_text else 1)
    assert all(answer == accepted[0] for answer in accepted)
    saved = store.get_attempt(key, attempt_id)
    assert saved["tasks"][0]["final_answer"] == accepted[0]
    assert saved["question_number"] == 2 and saved["phase"] == "first-answer"


def test_final_submission_cannot_cross_participant_or_test_scope(tmp_path):
    store, key, attempt_id = ready_question(tmp_path)
    before = store.get_attempt(key, attempt_id)
    for other in [AttemptKey(key.study_id, "other", key.study_session_id),
                  AttemptKey(key.study_id, key.participant_id, key.study_session_id, is_test=True)]:
        with pytest.raises(AttemptNotFound):
            store.submit_final_answer(other, attempt_id, 1, "Wrong scope")
    assert store.get_attempt(key, attempt_id) == before


@pytest.mark.parametrize("submitted", [False, True])
def test_retired_attempt_rejects_final_submissions_and_retries(tmp_path, submitted):
    store, key, attempt_id = ready_question(tmp_path)
    if submitted:
        store.submit_final_answer(key, attempt_id, 1, "Original")
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE progress_attempts SET status = 'retired'")
    before = store.get_attempt(key, attempt_id)
    with pytest.raises(SubmissionConflict):
        store.submit_final_answer(key, attempt_id, 1, "Original")
    assert store.get_attempt(key, attempt_id) == before


def test_transition_failure_rolls_back_final_answer_and_keeps_search_and_draft(tmp_path):
    store, key, attempt_id = ready_question(tmp_path)
    store.save_draft(key, attempt_id, 1, "final-answer", "Recoverable", 0)
    before = store.get_attempt(key, attempt_id)
    with sqlite3.connect(store.path) as db:
        db.execute("""CREATE TRIGGER reject_next_question BEFORE UPDATE ON progress_attempts
            BEGIN SELECT RAISE(ABORT, 'synthetic transition failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic transition failure"):
        store.submit_final_answer(key, attempt_id, 1, "Not committed")
    assert store.get_attempt(key, attempt_id) == before
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TRIGGER reject_next_question")
    assert store.submit_final_answer(key, attempt_id, 1, "Retry")["text"] == "Retry"


def test_schema_two_upgrade_preserves_first_answers_and_drafts(tmp_path):
    store, key, attempt_id = ready_question(tmp_path)
    store.save_draft(key, attempt_id, 1, "final-answer", "Version two draft", 0)
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TABLE IF EXISTS progress_final_answers")
        db.execute("PRAGMA user_version=2")
    upgraded, _ = make_store(tmp_path)
    saved = upgraded.get_attempt(key, attempt_id)
    assert upgraded.runtime_settings()["schema_version"] == 4
    assert saved["tasks"][0]["first_answer"]["text"] == "Before searching"
    assert saved["tasks"][0]["drafts"]["final-answer"]["text"] == "Version two draft"
    assert saved["tasks"][0]["final_answer"] is None and saved["phase"] == "search"
    assert upgraded.submit_final_answer(key, attempt_id, 1, "After upgrade")["text"] == "After upgrade"


def test_failed_final_commit_keeps_draft_and_allows_retry_without_advancing(tmp_path):
    store, key, attempt_id = ready_question(tmp_path)
    store, _ = make_store(tmp_path, timeout=0.01)
    store.save_draft(key, attempt_id, 1, "final-answer", "Recoverable draft", 0)
    before = store.get_attempt(key, attempt_id)
    reader = sqlite3.connect(store.path)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM progress_attempts").fetchall()
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            store.submit_final_answer(key, attempt_id, 1, "Not committed")
    finally:
        reader.rollback()
        reader.close()
    assert store.get_attempt(key, attempt_id) == before
    assert store.submit_final_answer(key, attempt_id, 1, "Retry")["text"] == "Retry"
