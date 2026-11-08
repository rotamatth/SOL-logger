"""Storage contracts consumed by the separate recap and researcher-reset work."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from .test_study_progress import QUESTIONS, make_store


def completed(store, key):
    attempt = store.start_or_resume(key, QUESTIONS, {"technical_session_id": "run-1", "log_id": "log-1"})
    aid = attempt["attempt_id"]
    for number in (1, 2, 3):
        store.submit_first_answer(key, aid, number, unknown_confirmed=True)
        store.submit_final_answer(key, aid, number, f"Final {number}")
    editor = {"study_session_id": key.study_session_id, "attempt_id": aid, "technical_session_id": "run-1"}
    return aid, editor


def test_recap_drafts_resume_and_revisions_preserve_originals(tmp_path):
    from study_progress import DraftConflict, SubmissionConflict
    store, key = make_store(tmp_path)
    aid, editor = completed(store, key)
    originals = store.get_attempt(key, aid)
    draft = store.save_recap_draft(key, aid, 1, "first-answer", "My new idea", 0, editing_context=editor)
    reopened, _ = make_store(tmp_path)
    assert reopened.recap_state(key, aid, editing_context=editor)["tasks"][0]["recap_drafts"]["first-answer"] == draft
    with pytest.raises(DraftConflict):
        store.save_recap_draft(key, aid, 1, "first-answer", "Stale draft", 0, editing_context=editor)
    revision = store.append_answer_revision(key, aid, 1, "first-answer", "My new idea", 0,
                                            request_id="edit-1", editing_context=editor)
    assert revision["before_text"] is None and revision["after_text"] == "My new idea"
    assert revision["editing_context"] == editor and revision["revision"] == 1
    assert store.append_answer_revision(key, aid, 1, "first-answer", "My new idea", 0,
                                        request_id="edit-1", editing_context=editor) == revision
    with pytest.raises(SubmissionConflict):
        store.append_answer_revision(key, aid, 1, "first-answer", "Different", 0,
                                     request_id="edit-1", editing_context=editor)
    next_revision = store.append_answer_revision(key, aid, 1, "first-answer", "Revised again", 1,
                                                 request_id="edit-2", editing_context=editor)
    assert next_revision["before_text"] == "My new idea" and next_revision["revision"] == 2
    history = reopened.recap_state(key, aid, editing_context=editor)
    assert history["tasks"][0]["revisions"] == [revision, next_revision]
    assert history["tasks"][0]["recap_drafts"] == {}
    assert store.get_attempt(key, aid) == originals


def test_recap_editing_context_is_verified_and_cross_session_edits_stay_scoped(tmp_path):
    from study_progress import AttemptKey, AttemptNotFound
    store, key = make_store(tmp_path)
    aid, editor = completed(store, key)
    other_key = AttemptKey(key.study_id, key.participant_id, "later-session")
    later = store.start_or_resume(other_key, QUESTIONS, {"technical_session_id": "run-2"})
    later_editor = {"study_session_id": "later-session", "attempt_id": later["attempt_id"], "technical_session_id": "run-2"}
    store.save_recap_draft(key, aid, 1, "final-answer", "Later edit", 0, editing_context=later_editor)
    assert store.recap_state(key, aid, editing_context=editor)["tasks"][0]["recap_drafts"] == {}
    assert store.recap_state(key, aid, editing_context=later_editor)["tasks"][0]["recap_drafts"]["final-answer"]["text"] == "Later edit"
    with pytest.raises(ValueError):
        store.save_recap_draft(key, aid, 1, "final-answer", "Wrong run", 0,
                              editing_context={**editor, "technical_session_id": "foreign-run"})
    foreign_key = AttemptKey(key.study_id, "another-participant", key.study_session_id)
    with pytest.raises(AttemptNotFound):
        store.recap_state(foreign_key, aid, editing_context=editor)


def test_concurrent_recap_edits_keep_one_revision_and_reject_stale_base(tmp_path):
    from study_progress import DraftConflict
    store, key = make_store(tmp_path)
    aid, editor = completed(store, key)

    def edit(text):
        worker, _ = make_store(tmp_path)
        try:
            return worker.append_answer_revision(key, aid, 1, "final-answer", text, 0,
                                                  request_id=text, editing_context=editor)
        except DraftConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [result for result in pool.map(edit, ["Edit A", "Edit B"]) if result]
    assert len(results) == 1 and results[0]["before_text"] == "Final 1"
    assert store.recap_state(key, aid, editing_context=editor)["tasks"][0]["revisions"] == results


@pytest.mark.parametrize("save_first", [False, True])
def test_delayed_recap_autosave_cannot_resurrect_a_confirmed_draft(tmp_path, save_first):
    from study_progress import DraftConflict
    store, key = make_store(tmp_path)
    aid, editor = completed(store, key)
    if save_first:
        store.save_recap_draft(key, aid, 1, "final-answer", "Confirmed edit", 0, editing_context=editor)
    old_revision = 1 if save_first else 0
    store.append_answer_revision(key, aid, 1, "final-answer", "Confirmed edit", 0,
                                 request_id="confirm", editing_context=editor)
    with pytest.raises(DraftConflict):
        store.save_recap_draft(key, aid, 1, "final-answer", "Late autosave", old_revision, editing_context=editor)
    current = store.recap_state(key, aid, editing_context=editor)["tasks"][0]
    newer = store.save_recap_draft(key, aid, 1, "final-answer", "New idea", current["recap_draft_revisions"]["final-answer"], editing_context=editor)
    assert newer["revision"] > old_revision + 1
    with pytest.raises(DraftConflict):
        store.save_recap_draft(key, aid, 1, "final-answer", "Stale again", old_revision + 1, editing_context=editor)
    assert store.recap_state(key, aid, editing_context=editor)["tasks"][0]["recap_drafts"]["final-answer"] == newer


def test_repeat_clones_original_snapshot_order_and_preserves_all_history(tmp_path):
    from study_progress import SubmissionConflict
    store, key = make_store(tmp_path)
    aid, editor = completed(store, key)
    store.append_answer_revision(key, aid, 1, "final-answer", "A recap edit", 0,
                                 request_id="recap-1", editing_context=editor)
    original = store.get_attempt(key, aid)
    repeated = store.repeat_attempt(key, aid, authorized_by="researcher", request_id="repeat-1",
                                    technical_session_id="run-repeat", log_id="log-repeat")
    assert repeated["attempt_id"] != aid
    assert repeated["question_number"] == 1 and repeated["phase"] == "first-answer"
    assert [task["snapshot"] for task in repeated["tasks"]] == QUESTIONS
    assert all(task["first_answer"] is None and task["final_answer"] is None and not task["drafts"] for task in repeated["tasks"])
    assert repeated["metadata"]["source_attempt_id"] == aid
    assert repeated["metadata"]["repeat_authorized_by"] == "researcher"
    retired = store.get_attempt(key, aid)
    assert retired["status"] == "retired" and retired["tasks"] == original["tasks"]
    with pytest.raises(SubmissionConflict):
        store.submit_final_answer(key, aid, 1, "Final 1")
    with pytest.raises(SubmissionConflict):
        store.save_recap_draft(key, aid, 1, "final-answer", "Stale", 0, editing_context=editor)
    assert store.start_or_resume(key, list(reversed(QUESTIONS))) == repeated
    assert store.repeat_attempt(key, aid, authorized_by="researcher", request_id="repeat-1",
                                technical_session_id="run-repeat", log_id="log-repeat") == repeated
    repeat_editor = {**editor, "attempt_id": repeated["attempt_id"], "technical_session_id": "run-repeat"}
    history = store.recap_state(key, aid, editing_context=repeat_editor)
    assert history["tasks"][0]["revisions"][0]["after_text"] == "A recap edit"
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM progress_answer_revisions").fetchone()[0] == 1


def test_repeat_retirement_and_clone_are_atomic_and_idempotent_across_workers(tmp_path):
    store, key = make_store(tmp_path)
    aid = store.start_or_resume(key, QUESTIONS, {"technical_session_id": "original-run"})["attempt_id"]
    options = dict(authorized_by="researcher", request_id="request-1", technical_session_id="new-run", log_id="new-log")
    with sqlite3.connect(store.path) as db:
        db.execute("""CREATE TRIGGER reject_clone BEFORE INSERT ON progress_attempts
            BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.repeat_attempt(key, aid, **options)
    assert store.get_attempt(key, aid)["status"] == "active"
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TRIGGER reject_clone")

    def repeat(_):
        worker, _ = make_store(tmp_path)
        return worker.repeat_attempt(key, aid, **options)

    with ThreadPoolExecutor(max_workers=4) as pool:
        attempts = list(pool.map(repeat, range(4)))
    assert len({attempt["attempt_id"] for attempt in attempts}) == 1
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM progress_attempts WHERE status='active'").fetchone()[0] == 1


@pytest.mark.parametrize("field", ["authorized_by", "request_id", "technical_session_id", "log_id"])
def test_repeat_requires_explicit_authorization_and_new_run_identity(tmp_path, field):
    store, key = make_store(tmp_path)
    aid = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    options = dict(authorized_by="researcher", request_id="repeat", technical_session_id="new", log_id="new-log")
    options[field] = ""
    with pytest.raises(ValueError):
        store.repeat_attempt(key, aid, **options)
    assert store.get_attempt(key, aid)["status"] == "active"


def test_failed_revision_confirmation_keeps_original_history_and_recoverable_draft(tmp_path):
    store, key = make_store(tmp_path)
    aid, editor = completed(store, key)
    draft = store.save_recap_draft(key, aid, 1, "final-answer", "Keep this edit", 0, editing_context=editor)
    with sqlite3.connect(store.path) as db:
        db.execute("""CREATE TRIGGER fail_draft_clear BEFORE UPDATE ON progress_recap_drafts
            BEGIN SELECT RAISE(ABORT, 'synthetic clear failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.append_answer_revision(key, aid, 1, "final-answer", "Keep this edit", 0,
                                     request_id="edit", editing_context=editor)
    state = store.recap_state(key, aid, editing_context=editor)["tasks"][0]
    assert state["revisions"] == [] and state["recap_drafts"]["final-answer"] == draft
    assert state["final_answer"]["text"] == "Final 1"


def test_conflicting_repeat_retry_and_reused_technical_identity_do_not_change_progress(tmp_path):
    from study_progress import SubmissionConflict
    store, key = make_store(tmp_path)
    aid = store.start_or_resume(key, QUESTIONS, {"technical_session_id": "run-1", "log_id": "log-1"})["attempt_id"]
    options = dict(authorized_by="researcher", request_id="repeat", technical_session_id="run-2", log_id="log-2")
    repeated = store.repeat_attempt(key, aid, **options)
    with pytest.raises(SubmissionConflict):
        store.repeat_attempt(key, aid, **{**options, "authorized_by": "different-researcher"})
    with pytest.raises(SubmissionConflict):
        store.repeat_attempt(key, aid, **{**options, "request_id": "different-request"})
    assert store.get_attempt(key, repeated["attempt_id"]) == repeated


def test_schema_five_upgrade_preserves_confidence_and_existing_outbox(tmp_path):
    store, key = make_store(tmp_path)
    aid = store.start_or_resume(key, QUESTIONS)["attempt_id"]
    original = store.submit_first_answer(key, aid, 1, "Idea", confidence=3)
    pending = store.pending_events(key, aid)
    with sqlite3.connect(store.path) as db:
        for table in ("progress_recap_drafts", "progress_answer_revisions", "progress_repeat_requests",
                      "progress_recap_exports"):
            db.execute(f"DROP TABLE {table}")
        db.execute("PRAGMA user_version=5")
    reopened, _ = make_store(tmp_path)
    assert reopened.runtime_settings()["schema_version"] == 7
    assert reopened.get_attempt(key, aid)["tasks"][0]["first_answer"] == original
    assert reopened.pending_events(key, aid) == pending
