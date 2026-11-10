"""Working researcher drafts never replace questions used for admission."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from .enrollment_helpers import enroll_initial_roster, school_year
from .test_study_enrollment import question_set
from research_dashboard.collection import record_run
from research_dashboard.question_versions import (
    discard_question_draft, publish_questions, published_questions, question_draft,
    remove_individual_questions, save_question_draft, working_questions,
)
from research_dashboard.state import State
from research_dashboard.study_config import assignment_for, scheduled_assignment, session_readiness


SESSION = "grade-4-session-1"


def configured_state(tmp_path):
    state = State(tmp_path / "state")
    settings = state.settings()
    today = datetime.now(ZoneInfo("Europe/Zurich")).date()
    enroll_initial_roster(settings, school_year(today))
    settings["sessions"][0].update(date=today.isoformat(), question_set=question_set("Published"))
    state.save_settings(settings, settings["revision"])
    return state


def persist(state, settings):
    state.save_settings(settings, settings["revision"])
    return state.settings()


def admit(state, directory, uid, run_id):
    settings = state.settings()
    selected = scheduled_assignment(settings, uid)
    assert selected and selected["ready"]
    return record_run(directory, state, uid, run_id, run_id, ["2", "3", "1"],
                      selected["topics"], settings=settings, study_session=selected["session"],
                      question_set=selected["question_set"], assignment_source=selected["source"],
                      admit=True)


def test_shared_draft_is_recoverable_without_changing_published_readiness(tmp_path):
    state = configured_state(tmp_path)
    settings = state.settings()
    original = deepcopy(settings["sessions"][0]["question_set"])
    draft = {"theme": "Next revision", "questions": [{"id": "work-1", "topic": "Sky", "question": ""}]}
    saved = save_question_draft(settings["sessions"][0], draft)
    assert saved["approved"] is False and "approved" not in draft
    settings = persist(state, settings)
    current = settings["sessions"][0]
    assert question_draft(current) == saved == working_questions(current)
    assert published_questions(current) == original
    assert session_readiness(settings, current)["complete"]
    assert assignment_for(settings, "1", SESSION)["question_set"] == original
    assert State(state.path.parent).settings()["sessions"][0]["question_draft"] == saved


def test_unpublished_individual_draft_keeps_shared_questions_available(tmp_path):
    state = configured_state(tmp_path)
    settings = state.settings()
    current = settings["sessions"][0]
    original = deepcopy(current["question_set"])
    candidate = working_questions(current, "1")
    assert candidate["approved"] is False
    assert candidate["questions"] == original["questions"]
    candidate["questions"][0]["question"] = ""
    save_question_draft(current, candidate, "1")
    settings = persist(state, settings)
    assignment = assignment_for(settings, "1", SESSION)
    assert assignment["ready"] and assignment["source"] == "shared"
    assert assignment["question_set"] == original
    assert published_questions(settings["sessions"][0], "1") is None
    assert question_draft(settings["sessions"][0], "1")["questions"][0]["question"] == ""


def test_individual_publication_and_removal_preserve_other_versions(tmp_path):
    state = configured_state(tmp_path)
    settings = state.settings()
    current = settings["sessions"][0]
    shared = deepcopy(current["question_set"])
    save_question_draft(current, question_set("Shared draft"))
    save_question_draft(current, question_set("Other draft"), "2")
    save_question_draft(current, question_set("Individual draft"), "1")
    published = publish_questions(current, question_draft(current, "1"), "1")
    assert published["approved"] and question_draft(current, "1") is None
    settings = persist(state, settings)
    assert assignment_for(settings, "1", SESSION)["source"] == "participant"
    assert assignment_for(settings, "1", SESSION)["question_set"] == published
    assert assignment_for(settings, "2", SESSION)["question_set"] == shared
    current = settings["sessions"][0]
    save_question_draft(current, {"questions": []}, "1")
    assert assignment_for(settings, "1", SESSION)["question_set"] == published
    assert remove_individual_questions(current, "1")
    assert published_questions(current, "1") is None and question_draft(current, "1") is None
    assert question_draft(current, "2") == question_set("Other draft", approved=False)
    assert question_draft(current) == question_set("Shared draft", approved=False)
    settings = persist(state, settings)
    assert assignment_for(settings, "1", SESSION)["question_set"] == shared


@pytest.mark.parametrize("participant", ["", "1"])
def test_legacy_unapproved_assignments_are_never_implicitly_published_or_repaired(tmp_path, participant):
    state = configured_state(tmp_path)
    settings = state.settings()
    current = settings["sessions"][0]
    legacy = question_set("Legacy draft", approved=False)
    if participant:
        current["participant_questions"] = {participant: legacy}
    else:
        current["question_set"] = legacy
    settings = persist(state, settings)
    before = deepcopy(settings)
    assert working_questions(settings["sessions"][0], participant) == legacy
    assert published_questions(settings["sessions"][0], participant) == legacy
    assert settings == before
    assert not assignment_for(settings, "1", SESSION)["ready"]
    save_question_draft(settings["sessions"][0], {"questions": []}, participant)
    settings = persist(state, settings)
    assert not assignment_for(settings, "1", SESSION)["ready"]
    assert published_questions(settings["sessions"][0], participant) == legacy


def test_discarding_shared_draft_and_failed_publish_leave_approved_text_intact(tmp_path):
    state = configured_state(tmp_path)
    current = state.settings()["sessions"][0]
    original = deepcopy(current["question_set"])
    save_question_draft(current, {"questions": []})
    before = deepcopy(current)
    with pytest.raises(ValueError, match="questions_incomplete"):
        publish_questions(current, question_draft(current))
    assert current == before
    assert discard_question_draft(current)
    assert not discard_question_draft(current)
    assert working_questions(current) == original
    returned = working_questions(current)
    returned["questions"][0]["metadata"]["difficulty"] = 99
    assert current["question_set"] == original


@pytest.mark.parametrize("field,value,error", [
    ("question_draft", {"questions": [], "approved": True}, "invalid_question_set"),
    ("question_draft", {"questions": [dict(id=str(i)) for i in range(4)]}, "invalid_question_set"),
    ("question_draft", {"questions": [], "metadata": {"number": float("inf")}}, "invalid_question_metadata"),
    ("participant_question_drafts", [], "invalid_participant_questions"),
    ("participant_question_drafts", {"bad id": {"questions": []}}, "invalid_participant_questions"),
    ("participant_question_drafts", {"1": {"questions": [], "approved": True}}, "invalid_question_set"),
    ("participant_question_drafts", {str(i): {"questions": []} for i in range(3001)}, "invalid_participant_questions"),
])
def test_state_rejects_invalid_working_fields_atomically(tmp_path, field, value, error):
    state = configured_state(tmp_path)
    before = state.settings()
    settings = deepcopy(before)
    settings["sessions"][0][field] = value
    with pytest.raises(ValueError, match=error):
        state.save_settings(settings, settings["revision"])
    assert state.settings() == before


def test_publishing_only_changes_future_admissions_and_preserves_immutable_attempts(tmp_path):
    state = configured_state(tmp_path)
    directory = tmp_path / "logs"
    original = admit(state, directory, "1", "first")
    original_bytes = next(directory.glob("1_first.run.json")).read_bytes()
    settings = state.settings()
    pending = question_set("Replacement")
    save_question_draft(settings["sessions"][0], pending)
    settings = persist(state, settings)
    while_editing = admit(state, directory, "2", "while-editing")
    assert while_editing["question_set_snapshot"] == original["question_set_snapshot"]
    publish_questions(settings["sessions"][0], question_draft(settings["sessions"][0]))
    persist(state, settings)
    after_publication = admit(state, directory, "3", "after-publication")
    assert after_publication["question_set_snapshot"] == pending
    assert state.attempt_metadata("first") == original
    assert next(directory.glob("1_first.run.json")).read_bytes() == original_bytes
    assert after_publication["tasks"][0]["question_id"] == "replacement-2"
