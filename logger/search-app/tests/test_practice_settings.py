"""The practice question is stored apart from the study settings, with revisions of its own."""
import sqlite3

import pytest

from research_dashboard.practice_settings import PRACTICE_DEFAULT, QUESTION_MAX, TOPIC_MAX
from research_dashboard.state import State


@pytest.fixture
def state(tmp_path):
    return State(tmp_path / "state")


def test_before_any_save_the_practice_is_the_volcano_question_and_on(state):
    practice = state.practice()
    assert practice == {**PRACTICE_DEFAULT, "revision": 0, "updated_at": None}
    assert practice["enabled"] is True and "vulcaniche" in practice["question"]


def test_a_saved_practice_is_read_back_tidied(state):
    revision = state.save_practice({"enabled": False, "topic": "  Terremoti ", "question": "Come si misura\n un terremoto?"}, 0)
    practice = state.practice()
    assert practice["revision"] == revision == 1
    assert (practice["enabled"], practice["topic"], practice["question"]) == (False, "Terremoti", "Come si misura un terremoto?")


def test_a_save_from_an_old_form_is_refused_and_keeps_the_newer_one(state):
    state.save_practice({**PRACTICE_DEFAULT, "topic": "Prima"}, 0)
    with pytest.raises(ValueError, match="practice_changed"):
        state.save_practice({**PRACTICE_DEFAULT, "topic": "Seconda"}, 0)
    assert state.practice()["topic"] == "Prima"


@pytest.mark.parametrize(("value", "error"), [
    ({**PRACTICE_DEFAULT, "question": "   "}, "practice_question_invalid"),
    ({**PRACTICE_DEFAULT, "question": "x" * (QUESTION_MAX + 1)}, "practice_question_invalid"),
    ({**PRACTICE_DEFAULT, "question": "Una\x07domanda"}, "practice_question_invalid"),
    ({**PRACTICE_DEFAULT, "topic": ""}, "practice_topic_invalid"),
    ({**PRACTICE_DEFAULT, "topic": "t" * (TOPIC_MAX + 1)}, "practice_topic_invalid"),
    ({**PRACTICE_DEFAULT, "enabled": "yes"}, "invalid_practice"),
    ("not a document", "invalid_practice"),
])
def test_an_unusable_practice_is_refused_and_nothing_is_saved(state, value, error):
    with pytest.raises(ValueError, match=error):
        state.save_practice(value, 0)
    assert state.practice()["revision"] == 0


def test_saving_the_practice_leaves_the_study_settings_and_their_revision_alone(state):
    before = state.settings()
    state.save_practice({**PRACTICE_DEFAULT, "enabled": False}, 0)
    after = state.settings()
    assert after == before


def test_the_practice_table_needs_no_new_schema_version(state):
    """An older application opens the same database after a rollback and ignores the table."""
    with sqlite3.connect(state.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db.execute("SELECT name FROM sqlite_master WHERE name='practice_question'").fetchone()


def test_reopening_the_database_keeps_the_saved_practice(state, tmp_path):
    state.save_practice({**PRACTICE_DEFAULT, "topic": "Terremoti"}, 0)
    assert State(tmp_path / "state").practice()["topic"] == "Terremoti"
