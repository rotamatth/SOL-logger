"""The one-step setup gives the real session of 10 November, and refuses anything but a fresh dashboard."""
from datetime import date
import importlib.util
import json
from pathlib import Path

import pytest

from research_dashboard.index import Index
from research_dashboard.participants import roster
from research_dashboard.state import State
from research_dashboard.study_config import scheduled_assignment, session_readiness

SPEC = importlib.util.spec_from_file_location(
    "setup_session", Path(__file__).resolve().parents[1] / "tools" / "setup_session_2026_11_10.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)

CLASS_4 = ["1", "2", "3", "4", "5", "6", "7", "8", "17", "18"]
CLASS_5 = ["9", "10", "11", "12", "13", "14", "15", "16", "19", "20"]
ORECCHIO = (("Uno", "Domanda uno?"), ("Due", "Domanda due?"), ("Tre", "Domanda tre?"))
PERIODS = {"3": (("2026-05-20", "2026-05-20"),), "4": (("2026-05-21", "2026-05-22"),)}
MAY_IDS = {"3": ("1", "17"), "4": ("9", "19")}
DAY = date(2026, 11, 10)


@pytest.fixture
def ready(tmp_path):
    (tmp_path / "logs").mkdir()
    state = State(tmp_path / "state")
    setup.apply(state, tmp_path / "logs", orecchio=ORECCHIO, periods=PERIODS, may_ids=MAY_IDS)
    return state, tmp_path


def test_this_years_classes_have_their_real_ids_and_nothing_pre_filled(ready):
    state, _ = ready
    settings = state.settings()
    classes = roster(settings, "2026/2027")
    assert [uid for uid, grade in classes.items() if grade == "4"] == CLASS_4
    assert [uid for uid, grade in classes.items() if grade == "5"] == CLASS_5
    assert sorted(settings["participant_registry"], key=int) == sorted(CLASS_4 + CLASS_5, key=int)
    assert all(person["active"] for person in settings["participant_registry"].values())


def test_may_holds_the_same_children_a_class_lower(ready):
    state, _ = ready
    classes = roster(state.settings(), "2025/2026")
    assert [uid for uid, grade in classes.items() if grade == "3"] == CLASS_4
    assert [uid for uid, grade in classes.items() if grade == "4"] == CLASS_5


def test_only_the_two_real_sessions_exist_and_both_are_ready(ready):
    state, _ = ready
    settings = state.settings()
    assert [(item["id"], item["name"], item["date"], item["number"]) for item in settings["sessions"]] == [
        ("grade-4-session-1", "4a spazio", "2026-11-10", 1), ("grade-5-session-1", "5a orecchio", "2026-11-10", 1)]
    assert all(session_readiness(settings, item)["complete"] for item in settings["sessions"])


@pytest.mark.parametrize(("uid", "theme", "first_question"), [
    ("1", "spazio", "Come si chiamano i satelliti maggiori di Giove?"), ("18", "spazio", None),
    ("9", "orecchio", "Domanda uno?"), ("20", "orecchio", None)])
def test_each_child_opens_their_class_only_on_the_day(ready, uid, theme, first_question):
    state, _ = ready
    settings = state.settings()
    assignment = scheduled_assignment(settings, uid, DAY)
    assert assignment["question_set"]["theme"] == theme
    if first_question:
        assert assignment["question_set"]["questions"][0]["question"] == first_question
    assert scheduled_assignment(settings, uid, date(2026, 11, 9)) is None
    assert scheduled_assignment(settings, "21", DAY) is None


def test_the_spazio_questions_are_last_years_in_clip_order(ready):
    state, _ = ready
    questions = state.settings()["sessions"][0]["question_set"]["questions"]
    assert [item["topic"] for item in questions] == ["Sistema solare Giove", "Primo animale nello spazio", "Altre galassie"]


def test_without_its_questions_class_5_stays_a_draft_that_keeps_its_theme(tmp_path):
    (tmp_path / "logs").mkdir()
    state = State(tmp_path / "state")
    setup.apply(state, tmp_path / "logs", orecchio=(), periods=PERIODS, may_ids=MAY_IDS)
    settings = state.settings()
    assert scheduled_assignment(settings, "9", DAY) is None
    assert scheduled_assignment(settings, "1", DAY) is not None
    assert settings["sessions"][1]["question_set"]["theme"] == "orecchio"


def write_may_run(folder, uid, day):
    event = {"type": "pageView", "uid": uid, "sessionID": "synthetic", "timestamp": f"{day}T10:00:00.000"}
    (folder / f"{uid}_{day}_10-00-00_00000001_FULL.log").write_text(json.dumps(event) + "\n")


def test_may_records_join_their_class_and_child_and_test_names_stay_out(ready):
    state, root = ready
    legacy = root / "legacy"
    legacy.mkdir()
    for uid, day in (("1", "2026-05-20"), ("9", "2026-05-21"), ("Utente1", "2026-05-20"), ("UserTestLog1", "2026-05-20"),
                     ("1", "2026-05-11")):
        write_may_run(legacy, uid, day)
    before = {path.name: path.read_bytes() for path in legacy.iterdir()}
    index = Index(root / "state", {"v2": root / "logs", "legacy": legacy})
    index.refresh(force=True)
    runs = {(run["participant_id"], run["date"]): run for run in index.summaries(state.settings())}
    one, nine = runs[("1", "2026-05-20")], runs[("9", "2026-05-21")]
    assert (one["grade"], one["school_year"], one["study_participant_id"]) == ("3", "2025/2026", "1")
    assert (nine["grade"], nine["school_year"], nine["study_participant_id"]) == ("4", "2025/2026", "9")
    for key in (("Utente1", "2026-05-20"), ("UserTestLog1", "2026-05-20"), ("1", "2026-05-11")):
        assert (runs[key]["grade"], runs[key]["study_participant_id"]) == (None, None)
    assert {path.name: path.read_bytes() for path in legacy.iterdir()} == before


@pytest.mark.parametrize("change", ["again", "year", "attempt", "log"])
def test_anything_but_a_fresh_dashboard_is_refused_and_left_untouched(tmp_path, change):
    (tmp_path / "logs").mkdir()
    state = State(tmp_path / "state")
    if change == "again":
        setup.apply(state, tmp_path / "logs")
    elif change == "year":
        settings = state.settings()
        settings["current_school_year"] = "2026/2027"
        state.save_settings(settings, settings["revision"])
    elif change == "attempt":
        with state.connect() as db:
            db.execute("INSERT INTO study_attempts VALUES ('run','grade-4-session-1','1','{}',1)")
    else:
        (tmp_path / "logs" / "1_run_FULL.log").write_text("{}\n")
    revision = state.settings()["revision"]
    with pytest.raises(setup.NotFresh):
        setup.apply(state, tmp_path / "logs")
    assert state.settings()["revision"] == revision


def test_a_permanent_test_attempt_does_not_stop_the_setup(tmp_path):
    (tmp_path / "logs").mkdir()
    state = State(tmp_path / "state")
    with state.connect() as db:
        db.execute("""INSERT INTO study_attempts VALUES ('run','test-spazio-1','TEST-spazio',?,1)""",
                   (json.dumps({"is_test": True}),))
    setup.apply(state, tmp_path / "logs")
    assert state.settings()["current_school_year"] == "2026/2027"


def test_the_dry_run_saves_nothing(tmp_path, monkeypatch, capsys):
    (tmp_path / "logs").mkdir()
    state = State(tmp_path / "state")
    revision = state.settings()["revision"]
    monkeypatch.setattr("sys.argv", ["setup", "--state", str(tmp_path / "state"), "--logs", str(tmp_path / "logs"), "--dry-run"])
    assert setup.main() == 0
    assert "Dry run" in capsys.readouterr().out and "4a spazio" not in str(state.settings()["sessions"])
    assert state.settings()["revision"] == revision
