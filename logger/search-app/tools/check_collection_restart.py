"""Synthetic two-process/container restart check; never reads configured study data.

Run `seed --root /empty/private/path`, then `verify` against the same path from a
fresh container. The seed refuses an existing directory to prevent accidental use
on a real collection. Search is stubbed and no external API credentials are read.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import types
from zoneinfo import ZoneInfo


def load_app(root):
    app_root = Path(__file__).resolve().parents[1]
    os.chdir(app_root)
    sys.path.insert(0, str(app_root))
    os.environ.update(SOL_ENV="development", FLASK_SECRET_KEY="",
                      FLASK_SECRET_KEY_FILE=str(root / "student-sessions/signing-secret"),
                      SOL_SESSION_DIR=str(root / "student-sessions"), SOL_LOG_DIR=str(root / "logs-v2"),
                      RESEARCH_STATE_DIR=str(root / "research-state"),
                      RESEARCH_LEGACY_LOG_DIR=str(root / "logs"),
                      RESEARCH_PASSWORD_HASH="", RESEARCH_PASSWORD_HASH_FILE="")
    sys.modules["search_backend"] = types.ModuleType("search_backend")
    import search_app
    search_app.app.config["TESTING"] = True
    return search_app


def seed(root):
    root.mkdir(mode=0o700)
    module = load_app(root)
    settings = module.RESEARCH_STATE.settings()
    today = datetime.now(ZoneInfo("Europe/Zurich")).date()
    start_year = today.year if today.month >= 9 else today.year - 1
    settings["current_school_year"] = f"{start_year}/{start_year + 1}"
    settings["sessions"][0].update(school_year=settings["current_school_year"],
        date=today.isoformat(),
        question_set={"approved": True, "questions": [
            {"id": f"synthetic-{n}", "topic": f"Test topic {n}", "question": f"Test question {n}"}
            for n in range(1, 4)]})
    module.RESEARCH_STATE.save_settings(settings, settings["revision"])
    client = module.app.test_client()
    assert client.post("/start", data={"user_id": "1"}).status_code == 302
    assert client.get("/task").status_code == 200
    with client.session_transaction() as active:
        first_context = {"csrf_token": active["progress_csrf"], "attempt_id": active["progress_id"],
                         "question_number": active["task_position"] + 1}
    assert client.post("/first-answer", data={**first_context, "outcome": "answered",
                                             "text": "Synthetic first answer"}).status_code == 303
    assert client.get("/search").status_code == 200
    with client.session_transaction() as active:
        sid, questions = active["session_id"], active["task_config"]
    body = {"session_id": sid, "batch_id": "synthetic-lost-ack", "logs": [
        {"type": "TaskEnded", "answer": "Synthetic answer after restart",
         "attempt_id": first_context["attempt_id"], "task_number": 1, "sessionID": sid, "uid": "1"}]}
    response = client.post("/log_session", json=body)
    assert response.status_code == 200
    assert client.post("/end").status_code == 302
    assert client.get("/next_task").status_code == 302
    evidence = {"cookie": client.get_cookie("session").value, "body": body,
                "receipt": response.json, "questions": questions,
                "snapshot": module.RESEARCH_STATE.attempt_metadata(sid),
                "registry": module.RESEARCH_STATE.settings()["participant_registry"],
                "enrollments": module.RESEARCH_STATE.settings()["enrollments"]}
    (root / "research-state/synthetic-restart.json").write_text(json.dumps(evidence))
    (root / "research-state/synthetic-restart.json").chmod(0o600)


def verify(root):
    evidence = json.loads((root / "research-state/synthetic-restart.json").read_text())
    module = load_app(root)
    client = module.app.test_client()
    client.set_cookie("session", evidence["cookie"])
    with client.session_transaction() as active:
        assert active["session_id"] == evidence["body"]["session_id"]
        assert active["task_config"] == evidence["questions"]
        assert active["task_position"] == 1
    assert client.post("/log_session", json=evidence["body"]).json == evidence["receipt"]
    assert module.RESEARCH_STATE.attempt_metadata(evidence["body"]["session_id"]) == evidence["snapshot"]
    settings = module.RESEARCH_STATE.settings()
    assert settings["participant_registry"] == evidence["registry"]
    assert settings["enrollments"] == evidence["enrollments"]
    assert evidence["snapshot"]["participant_key"] == settings["participant_registry"]["1"]["key"]
    records = [json.loads(line) for line in next((root / "logs-v2").glob("*_FULL.log")).read_text().splitlines()]
    assert len([entry for entry in records if entry["type"] == "TaskEnded"]) == 1
    assert len([entry for entry in records if entry["type"] == "OwnKnowledgeAnswerSubmitted"]) == 1
    # Viewing Q2 now emits TaskStarted; a late Q1 retry must never become its final answer.
    for path in (root / "logs-v2").glob("*_task2_*.log"):
        assert all(json.loads(line)["type"] != "TaskEnded" for line in path.read_text().splitlines())
    # A fresh browser must resume the same logical attempt after process/backup replacement.
    fresh = module.app.test_client()
    assert fresh.post("/start", data={"user_id": "1"}).status_code == 302
    with fresh.session_transaction() as active:
        assert active["progress_id"] == evidence["body"]["logs"][0]["attempt_id"]
        assert active["task_position"] == 1
        assert active["task_config"] == evidence["questions"]
    assert fresh.get("/search").status_code == 302
    with fresh:
        fresh.get("/task")
        progress = module.PROGRESS.current()
        assert progress["tasks"][0]["first_answer"]["text"] == "Synthetic first answer"
        assert progress["tasks"][0]["final_answer"]["text"] == "Synthetic answer after restart"
    assert client.get("/task").status_code == 200
    assert client.get("/health/ready").status_code == 200


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("seed", "verify"))
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    {"seed": seed, "verify": verify}[args.operation](args.root.resolve())
    print("Synthetic collection restart check: " + args.operation + " passed")
