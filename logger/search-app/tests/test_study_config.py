"""Session questions use fresh synthetic settings and never historical assets."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_dashboard.state import State, default_settings, validate_settings
from research_dashboard.study_config import (
    assignment_for, question_library, question_set_problem, question_set_topics,
    scheduled_assignment, session_readiness, validate_question_set,
)


def question_set(theme="New theme", approved=True):
    return {"theme": theme, "approved": approved,
            "questions": [{"id": f"question-{number}", "topic": f"Topic {number}",
                           "question": f"{theme}: question {number}?"}
                          for number in range(1, 4)]}


def configured_settings():
    settings = default_settings()
    settings["revision"] = 9
    settings["sessions"][0].update(date="2026-10-15", question_set=question_set())
    return settings


def test_existing_settings_and_legacy_range_assignment_create_no_session_questions():
    settings = default_settings()
    old_topics = {f"{number}_{field}": f"old {field}" for number in range(1, 4)
                  for field in ("short", "full", "gif")}
    for number in range(1, 4):
        old_topics[f"{number}_gif"] = f"old-{number}.gif"
    old_topics["full_gif"] = "old-full.mp4"
    settings["ranges"][0]["assignment"] = {"id": "a" * 24, "topics": old_topics, "mode": "all"}
    settings["sessions"][0]["date"] = "2026-10-15"
    validate_settings(settings)
    assignment = assignment_for(settings, "1", "grade-4-session-1")
    assert assignment["question_set"] is None
    assert assignment["problem"] == "question_set_missing"
    assert scheduled_assignment(settings, "1", datetime(2026, 10, 15)) is None
    assert all("question_set" not in item for item in settings["sessions"])


def test_shared_questions_are_scoped_to_exact_grade_session_and_roster():
    settings = configured_settings()
    assert assignment_for(settings, "1", "grade-4-session-1")["ready"]
    assert assignment_for(settings, "20", "grade-4-session-1")["source"] == "shared"
    assert assignment_for(settings, "21", "grade-4-session-1") is None
    assert assignment_for(settings, "1", "grade-5-session-1") is None
    assert assignment_for(settings, "001", "grade-4-session-1") is None
    assert assignment_for(settings, "999", "grade-4-session-1") is None
    assert assignment_for(settings, "1", "grade-4-session-2")["question_set"] is None


def test_padded_prefixed_ids_and_participant_override_are_exact():
    settings = configured_settings()
    settings["ranges"][0].update(start=1, end=2, prefix="C-", width=3)
    study_session = settings["sessions"][0]
    study_session["participant_questions"] = {"C-001": question_set("Individual")}
    override = assignment_for(settings, "C-001", study_session["id"])
    shared = assignment_for(settings, "C-002", study_session["id"])
    assert override["question_set"]["theme"] == "Individual"
    assert override["source"] == "participant" and shared["source"] == "shared"
    assert shared["question_set"]["theme"] == "New theme"
    assert assignment_for(settings, "C-1", study_session["id"]) is None
    override["question_set"]["questions"][0]["question"] = "Edited snapshot"
    override["session"]["date"] = "2027-01-01"
    assert study_session["participant_questions"]["C-001"]["questions"][0]["question"] != "Edited snapshot"
    assert study_session["date"] == "2026-10-15"


def test_override_draft_blocks_one_id_without_falling_back_to_approved_shared_set():
    settings = configured_settings()
    study_session = settings["sessions"][0]
    study_session["participant_questions"] = {"1": {"questions": [], "approved": False}}
    result = session_readiness(settings, study_session)
    assert result["count"] == 20 and result["ready"] == 19
    assert result["missing"] == ["1"] and not result["complete"]
    assert result["participants"][0]["problem"] == "questions_incomplete"
    assert result["participants"][1]["ready"]


@pytest.mark.parametrize("draft, problem", [
    ({"questions": []}, "questions_incomplete"),
    ({"questions": [{"id": "", "topic": "", "question": ""}]}, "questions_incomplete"),
    (question_set(approved=False), "questions_unapproved"),
])
def test_drafts_save_but_do_not_enable_participants(draft, problem):
    assert validate_question_set(draft) is draft
    settings = configured_settings()
    settings["sessions"][0]["question_set"] = draft
    validate_settings(settings)
    assert assignment_for(settings, "1", "grade-4-session-1")["problem"] == problem
    with pytest.raises(ValueError, match=problem):
        validate_question_set(draft, require_ready=True)


def test_readiness_requires_date_complete_text_and_explicit_approval():
    settings = configured_settings()
    study_session = settings["sessions"][0]
    assert session_readiness(settings, study_session)["complete"]
    study_session["date"] = ""
    assert assignment_for(settings, "1", study_session["id"])["problem"] == "session_date_missing"
    study_session["date"] = "2026-10-15"
    study_session["question_set"]["questions"][1]["question"] = "   "
    assert assignment_for(settings, "1", study_session["id"])["problem"] == "questions_incomplete"
    study_session["question_set"]["questions"][1]["question"] = "Complete?"
    del study_session["question_set"]["approved"]
    assert assignment_for(settings, "1", study_session["id"])["problem"] == "questions_unapproved"


@pytest.mark.parametrize("change, error", [
    (lambda value: value.update(approved="yes"), "invalid_question_set"),
    (lambda value: value.update(questions=value["questions"] + [value["questions"][0]]), "invalid_question_set"),
    (lambda value: value["questions"][1].update(id="question-1"), "duplicate_question_id"),
    (lambda value: value["questions"][0].update(question=12), "invalid_question_set"),
    (lambda value: value["questions"][0].update(question="x" * 2001), "invalid_question_set"),
    (lambda value: value.update(metadata={"value": float("nan")}), "invalid_question_metadata"),
    (lambda value: value["questions"][0].update(metadata=[]), "invalid_question_metadata"),
])
def test_malformed_config_cannot_enter_settings(change, error):
    settings = configured_settings()
    change(settings["sessions"][0]["question_set"])
    with pytest.raises(ValueError, match=error):
        validate_settings(settings)


def test_metadata_and_assets_are_optional_for_readiness_and_preserved_when_supplied():
    value = question_set()
    assert question_set_problem(value) is None
    topics = question_set_topics(value)
    assert topics["1_full"] == "New theme: question 1?" and topics["1_gif"] == ""
    assert topics["full_gif"] == ""
    value["metadata"] = {"full_gif": "optional.mp4", "research": {"interests": ["science"]}}
    value["questions"][0]["metadata"] = {"gif": "optional.gif", "keywords": ["river"]}
    assert validate_question_set(value, require_ready=True) is value
    assert question_set_topics(value)["1_gif"] == "optional.gif"
    assert question_set_topics(value)["full_gif"] == "optional.mp4"


def test_schedule_uses_zurich_date_at_utc_midnight_boundary_and_no_fallback():
    settings = configured_settings()
    now = datetime(2026, 10, 14, 22, 30, tzinfo=timezone.utc)
    assignment = scheduled_assignment(settings, "1", now)
    assert assignment["session"]["id"] == "grade-4-session-1"
    assert assignment["settings_revision"] == 9
    assert scheduled_assignment(settings, "1", datetime(2026, 10, 14, 21, 30, tzinfo=timezone.utc)) is None
    assert scheduled_assignment(settings, "1", datetime(2026, 10, 16)) is None
    assert scheduled_assignment(settings, "21", now) is None
    settings["sessions"][0]["question_set"]["approved"] = False
    assert scheduled_assignment(settings, "1", now) is None


def test_library_offers_historical_and_configured_text_without_using_rewards():
    legacy = {f"{number}_{field}": f"Legacy {field} {number}" for number in range(1, 4)
              for field in ("short", "full")}
    app = SimpleNamespace(config={"STUDENT_TOPICS": {"1": legacy, "2": deepcopy(legacy)},
                                  "STUDENT_ASSET_DIR": "/missing-assets"}, extensions={})
    settings = configured_settings()
    settings["sessions"][0]["participant_questions"] = {"1": question_set("Individual")}
    before = deepcopy(settings)
    catalog = question_library(app, settings)
    assert len(catalog) == 3
    historical = next(entry for entry in catalog if entry["label"] == "Legacy short 1")
    assert historical["question_set"]["questions"][0]["question"] == "Legacy full 1"
    assert historical["question_set"]["questions"][0]["metadata"]["legacy_topic_id"] == "1"
    assert all(entry["question_set"]["approved"] is False for entry in catalog)
    assert settings == before
    assert question_library(app, settings) == catalog
    assert len({entry["id"] for entry in catalog}) == 3


def test_additive_settings_roundtrip_preserves_hundred_sessions_and_history(tmp_path):
    state = State(tmp_path / "state")
    settings = state.settings()
    settings["current_school_year"] = "2026/2027"
    settings["sessions"] = [{"id": f"grade-{grade}-session-{number}", "grade": grade,
                             "number": number, "date": "", "name": f"Session {number}"}
                            for grade in ("4", "5") for number in range(1, 101)]
    settings["sessions"][99].update(date="2026-10-15", question_set=question_set())
    settings["sessions"][99]["participant_questions"] = {"1": question_set("Individual")}
    state.save_settings(settings, settings["revision"])
    saved = state.settings()
    assert saved["schema_version"] == 1 and len(saved["sessions"]) == 200
    assert saved["sessions"] == settings["sessions"]
    assert saved["historical_grades"] == settings["historical_grades"]
    assert saved["current_school_year"] == "2026/2027"
    assert assignment_for(saved, "1", "grade-4-session-100")["ready"]
    assert "question_set" not in saved["sessions"][0]


@pytest.mark.parametrize("overrides", [[], {"invalid/id": question_set()}, {"1": None}])
def test_invalid_participant_override_is_rejected(overrides):
    settings = configured_settings()
    settings["sessions"][0]["participant_questions"] = overrides
    with pytest.raises(ValueError):
        validate_settings(settings)
