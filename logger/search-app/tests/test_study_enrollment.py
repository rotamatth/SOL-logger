"""Student collection uses only approved, dated V2 assignments in isolated storage."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import importlib.util
import json
import sys
import types

from .enrollment_helpers import enroll_initial_roster, school_year

import pytest

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))


@pytest.fixture
def student_modules(tmp_path, monkeypatch):
    monkeypatch.chdir(APP_ROOT)
    monkeypatch.setenv("SOL_LOG_DIR", str(tmp_path / "v2"))
    monkeypatch.setenv("RESEARCH_LEGACY_LOG_DIR", str(tmp_path / "legacy"))
    monkeypatch.setenv("RESEARCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setitem(sys.modules, "search_backend", types.ModuleType("search_backend"))
    import flask_session
    original = flask_session.Session

    def isolated_session(app):
        app.config["SESSION_FILE_DIR"] = str(tmp_path / "student-sessions")
        return original(app)

    monkeypatch.setattr(flask_session, "Session", isolated_session)
    modules = []

    def load_worker():
        spec = importlib.util.spec_from_file_location(f"study_student_worker_{len(modules)}", APP_ROOT / "search_app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.app.config["TESTING"] = True
        modules.append(module)
        return module

    return load_worker


def question_set(label="Today", approved=True, missing_reward=False):
    return {"approved": approved, "theme": f"{label} theme", "metadata": {"condition": label},
            "questions": [{"id": f"{label.lower()}-{number}", "topic": f"{label} topic {number}",
                           "question": f"{label} question {number}",
                           "metadata": {"difficulty": number, **({"gif": "missing.gif"} if missing_reward else {})}}
                          for number in range(1, 4)]}


def schedule(module, shared=None, override=None):
    state = module.RESEARCH_STATE
    settings = state.settings()
    today = datetime.now(ZoneInfo("Europe/Zurich")).date()
    for study_session in settings["sessions"]:
        study_session["date"] = (today + timedelta(days=study_session["number"] - 2)).isoformat()
        study_session["question_set"] = question_set("Future" if study_session["number"] == 3 else "Past")
        if study_session["grade"] == "4" and study_session["number"] == 2:
            study_session["question_set"] = deepcopy(shared or question_set())
            study_session["participant_questions"] = {"1": deepcopy(override)} if override else {}
    enroll_initial_roster(settings, school_year(today))
    state.save_settings(settings, settings["revision"])
    return state.settings()


def metadata_files(tmp_path):
    return [json.loads(path.read_text()) for path in (tmp_path / "v2").glob("*.run.json")]


def test_fresh_roster_has_no_legacy_assignment_or_future_question_disclosure(student_modules, tmp_path):
    module = student_modules()
    client = module.app.test_client()
    page = client.get("/start")
    assert 'value="1"' in page.text
    assert 'value="21"' in page.text
    response = client.post("/start", data={"user_id": "1"})
    assert response.status_code == 400
    assert "Session not available" in response.text
    assert not metadata_files(tmp_path)

    schedule(module)
    page = client.get("/start")
    assert "Today question" not in page.text and "Future question" not in page.text
    assert client.post("/start", data={"user_id": "1"}).status_code == 302
    assert "Today question" in client.get("/task").text
    assert "Future question" not in client.get("/task").text
    with client.session_transaction() as active:
        run_id = active["session_id"]
    assert client.post("/start", data={"user_id": "unknown"}).status_code == 400
    with client.session_transaction() as active:
        assert active["session_id"] == run_id


@pytest.mark.parametrize("draft", [
    question_set(approved=False),
    {"approved": True, "questions": []},
])
def test_unapproved_or_incomplete_today_questions_reject_start(student_modules, tmp_path, draft):
    module = student_modules()
    schedule(module, shared=draft)
    response = module.app.test_client().post("/start", data={"user_id": "1"})
    assert response.status_code == 400
    assert "Session not available" in response.text
    assert not metadata_files(tmp_path)


def test_override_and_shared_assignment_snapshot_identity_and_metadata(student_modules, tmp_path):
    module = student_modules()
    settings = schedule(module, override=question_set("Override"))
    first, second = module.app.test_client(), module.app.test_client()
    assert first.post("/start", data={"user_id": "1"}).status_code == 302
    assert second.post("/start", data={"user_id": "2"}).status_code == 302
    assert "Override question" in first.get("/task").text
    assert "Today question" in second.get("/task").text
    saved = {item["participant_id"]: item for item in metadata_files(tmp_path)}
    own = saved["1"]
    assert own["study_session_at_collection"] == "grade-4-session-2"
    assert own["settings_revision_at_collection"] == settings["revision"]
    assert own["assignment_source"] == "participant"
    assert own["question_set_theme"] == "Override theme"
    assert own["question_set_metadata"] == {"condition": "Override"}
    assert "participant_questions" not in own["study_session_snapshot"]
    for task in own["tasks"]:
        topic = int(task["topic_id"])
        assert task["question_id"] == f"override-{topic}"
        assert task["question_metadata"] == {"difficulty": topic}
        assert task["question"] == f"Override question {topic}"
    assert saved["2"]["assignment_source"] == "shared"


def test_settings_changes_apply_across_running_workers_and_preserve_started_attempt(student_modules, tmp_path):
    module = student_modules()
    schedule(module)
    running = module.app.test_client()
    assert running.post("/start", data={"user_id": "1"}).status_code == 302
    original = metadata_files(tmp_path)[0]
    with running.session_transaction() as active:
        frozen_order = active["task_order"]
        frozen_config = active["task_config"]
    worker = student_modules()
    schedule(module, shared=question_set("Changed"))
    fresh = worker.app.test_client()
    assert fresh.post("/start", data={"user_id": "2"}).status_code == 302
    assert "Changed question" in fresh.get("/task").text
    assert "Today question" in running.get("/task").text
    with running.session_transaction() as active:
        assert active["task_config"] == frozen_config
        assert active["task_order"] == frozen_order
    assert original in metadata_files(tmp_path)


@pytest.mark.parametrize("missing_reward", [False, True])
def test_three_questions_finish_without_puzzle_media_and_keep_reward_events(student_modules, tmp_path, missing_reward):
    module = student_modules()
    schedule(module, shared=question_set(missing_reward=missing_reward))
    client = module.app.test_client()
    assert client.post("/start", data={"user_id": "1"}).status_code == 302
    with client.session_transaction() as active:
        sid = active["session_id"]
    for position in range(1, 4):
        assert client.get("/task").status_code == 200
        assert client.get("/search").status_code == 200
        response = client.post("/log_session", json={"session_id": sid, "logs": [
            {"type": "TaskEnded", "uid": "1", "sessionID": sid, "answer": f"answer {position}",
             "timestamp": datetime.now(ZoneInfo("Europe/Zurich")).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]}]})
        assert response.status_code == 200
        assert client.post("/end").status_code == 302
        reward = client.get("/reward")
        assert reward.status_code == 200
        assert f"Avete completato la domanda {position}!" in reward.text
        assert 'id="reward-piece-img"' not in reward.text
        assert "missing.gif" not in reward.text
        assert client.get("/reward").status_code == 200
        if position < 3:
            assert client.get("/next_task").status_code == 302
    completion = client.get("/thank_you")
    assert completion.status_code == 200
    assert 'class="final-reward-media"' not in completion.text
    assert 'id="finish-experiment-btn" class="app-btn app-btn-primary is-visible">' in completion.text
    response = client.post("/log_session", json={"session_id": sid, "logs": [
        {"type": "experimentFinished", "uid": "1", "sessionID": sid,
         "timestamp": datetime.now(ZoneInfo("Europe/Zurich")).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]}]})
    assert response.status_code == 200
    events = [json.loads(line) for line in next((tmp_path / "v2").glob("*_FULL.log")).read_text().splitlines()]
    assert len([event for event in events if event["type"] == "rewardShown"]) == 3
    assert [event["task_number"] for event in events if event["type"] == "TaskEnded"] == [1, 2, 3]
    assert events[-1]["type"] == "experimentFinished"
    from tools.check_logs import check_path
    for path in (tmp_path / "v2").glob("*.log"):
        checked_events, warnings = check_path(path)
        assert checked_events and not warnings, warnings


def test_explicit_session_snapshot_survives_midnight(student_modules, tmp_path, monkeypatch):
    module = student_modules()
    settings = schedule(module)
    from research_dashboard import collection
    chosen = next(item for item in settings["sessions"] if item["id"] == "grade-4-session-2")
    assignment = module.scheduled_assignment(settings, "1")
    actual_datetime = collection.datetime

    class NextDay:
        @staticmethod
        def now(tz):
            return actual_datetime.now(tz) + timedelta(days=1)

    monkeypatch.setattr(collection, "datetime", NextDay)
    collection.record_run(tmp_path / "v2", module.RESEARCH_STATE, "1", "midnight", "midnight",
                          ["2", "3", "1"], assignment["topics"], settings=settings,
                          study_session=chosen, question_set=assignment["question_set"])
    saved = metadata_files(tmp_path)[0]
    assert saved["study_session_at_collection"] == "grade-4-session-2"
    assert saved["study_session_snapshot"]["date"] == chosen["date"]
    assert saved["tasks"][0]["question_id"] == "today-2"
