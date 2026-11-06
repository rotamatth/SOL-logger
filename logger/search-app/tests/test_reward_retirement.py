"""Reward removal keeps legacy progress and researcher question assignments usable."""
from .test_study_enrollment import question_set, schedule, student_modules  # noqa: F401


def test_removed_reward_route_does_not_advance_a_question(student_modules):
    module = student_modules()
    schedule(module)
    client = module.app.test_client()
    client.post("/start", data={"user_id": "1"})
    assert client.get("/reward").status_code == 404
    assert client.get("/search").status_code == 302


def test_legacy_completed_question_continues_without_a_reward(student_modules):
    module = student_modules()
    schedule(module)
    client = module.app.test_client()
    client.post("/start", data={"user_id": "1"})
    with client.session_transaction() as state:
        state.pop("progress_id")
        topic = state["task_number"]
        state["pieces_earned"] = [topic]  # A pre-upgrade persisted browser session.
    assert client.get("/start").location.endswith("/next_task")
    assert client.get("/next_task").location.endswith("/task")
    with client.session_transaction() as state:
        assert state["task_position"] == 1
        assert "pieces_earned" not in state and state["completed_tasks"] == [topic]


def test_legacy_question_sets_need_questions_without_reward_assets(tmp_path):
    from research_dashboard.student_config import assignment_problem, validate_topics
    topics = {f"{n}_{kind}": f"Question {n}" for n in range(1, 4) for kind in ("short", "full")}
    assert validate_topics(topics) == topics
    assert assignment_problem(topics, tmp_path / "missing-assets") is None
    topics["1_full"] = ""
    assert assignment_problem(topics, tmp_path) == "assignment_invalid"


def test_completion_and_close_events_survive_reward_removal_and_publication_retry(student_modules, monkeypatch):
    from .test_connected_first_answer import events
    from .progress_helpers import confirm_first, final_event
    module = student_modules()
    schedule(module)
    client = module.app.test_client()
    client.post("/start", data={"user_id": "1"})
    for number in (1, 2, 3):
        confirm_first(client)
        with client.session_transaction() as state:
            sid = state["session_id"]
        assert client.post("/log_session", json={"session_id": sid, "logs": [final_event(client, f"Final {number}")]}).status_code == 200
        client.get("/next_task")
    assert client.get("/thank_you").status_code == 200
    assert client.get("/thank_you").status_code == 200
    assert len([e for e in events(module) if e["type"] == "sessionCompleted"]) == 1
    with monkeypatch.context() as patch:
        patch.setattr(module.PROGRESS, "publish", lambda _: False)
        assert client.get("/welcome?reset=1&finished=1").status_code == 503
    with client.session_transaction() as state:
        assert state["session_id"] == sid
    assert client.get("/welcome?reset=1&finished=1").status_code == 200
    finished = [e for e in events(module) if e["type"] == "experimentFinished"]
    assert len(finished) == 1 and finished[0]["task_number"] == 3
    assert not [e for e in events(module) if e["type"] in ("rewardShown", "finalRewardRevealClicked", "finalRewardRevealCompleted")]
