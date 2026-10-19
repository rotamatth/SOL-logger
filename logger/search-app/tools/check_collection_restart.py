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
    settings["current_school_year"] = "2026/2027"
    settings["sessions"][0].update(
        date=datetime.now(ZoneInfo("Europe/Zurich")).date().isoformat(),
        question_set={"approved": True, "questions": [
            {"id": f"synthetic-{n}", "topic": f"Test topic {n}", "question": f"Test question {n}"}
            for n in range(1, 4)]})
    module.RESEARCH_STATE.save_settings(settings, settings["revision"])
    client = module.app.test_client()
    assert client.post("/start", data={"user_id": "1"}).status_code == 302
    assert client.get("/search").status_code == 200
    with client.session_transaction() as active:
        sid, questions = active["session_id"], active["task_config"]
    body = {"session_id": sid, "batch_id": "synthetic-lost-ack", "logs": [
        {"type": "TaskEnded", "answer": "Synthetic answer after restart"}]}
    response = client.post("/log_session", json=body)
    assert response.status_code == 200
    assert client.post("/end").status_code == 302
    assert client.get("/next_task").status_code == 302
    evidence = {"cookie": client.get_cookie("session").value, "body": body,
                "receipt": response.json, "questions": questions,
                "snapshot": module.RESEARCH_STATE.attempt_metadata(sid)}
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
    records = [json.loads(line) for line in next((root / "logs-v2").glob("*_FULL.log")).read_text().splitlines()]
    assert len([entry for entry in records if entry["type"] == "TaskEnded"]) == 1
    assert not list((root / "logs-v2").glob("*_task2_*.log"))
    assert client.get("/task").status_code == 200
    assert client.get("/health/ready").status_code == 200


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("seed", "verify"))
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    {"seed": seed, "verify": verify}[args.operation](args.root.resolve())
    print("Synthetic collection restart check: " + args.operation + " passed")
