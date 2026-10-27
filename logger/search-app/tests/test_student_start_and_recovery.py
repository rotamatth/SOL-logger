"""Starts are not duplicated, concurrent researcher saves do not refuse a start, and no upload gets stuck."""
from datetime import datetime, timedelta
import json
import re

from .test_study_enrollment import APP_ROOT, schedule, student_modules  # noqa: F401
from research_dashboard.state import SETTING_FIELDS
from .progress_helpers import confirm_first, final_event


def attempts(module):
    with module.RESEARCH_STATE.connect() as db:
        return [row[0] for row in db.execute("SELECT technical_session_id FROM study_attempts")]


def test_same_id_submitted_twice_continues_the_untouched_run(student_modules, tmp_path):
    module = student_modules()
    schedule(module)
    client = module.app.test_client()
    assert client.post("/start", data={"user_id": "1"}).status_code == 302
    with client.session_transaction() as student:
        first = student["session_id"]
    again = client.post("/start", data={"user_id": "1"})
    assert again.status_code == 302 and again.location.endswith("/task")
    with client.session_transaction() as student:
        assert student["session_id"] == first
    assert attempts(module) == [first]
    assert len(list((tmp_path / "v2").glob("*.run.json"))) == 1


def test_start_after_searching_resumes_the_same_logical_attempt(student_modules):
    module = student_modules()
    schedule(module)
    client = module.app.test_client()
    client.post("/start", data={"user_id": "1"})
    client.get("/task")
    confirm_first(client)
    client.get("/search")
    assert client.post("/start", data={"user_id": "1"}).status_code == 302
    assert len(attempts(module)) == 1


def test_researcher_save_during_a_start_is_retried_instead_of_refused(student_modules, monkeypatch):
    module = student_modules()
    schedule(module)
    state = module.RESEARCH_STATE
    admit, raced = state.admit_attempt, []

    def save_settings_first(metadata):
        if not raced:
            raced.append(True)
            current = state.settings()
            state.save_settings({key: current[key] for key in SETTING_FIELDS}, current["revision"])
        return admit(metadata)

    monkeypatch.setattr(state, "admit_attempt", save_settings_first)
    client = module.app.test_client()
    assert client.post("/start", data={"user_id": "1"}).status_code == 302
    [technical_session_id] = attempts(module)
    metadata = state.attempt_metadata(technical_session_id)
    assert metadata["settings_revision_at_collection"] == state.settings()["revision"]


def test_batch_from_an_earlier_session_is_recovered_instead_of_blocking_uploads(student_modules, tmp_path):
    module = student_modules()
    schedule(module)
    client = module.app.test_client()
    client.post("/start", data={"user_id": "1"})
    confirm_first(client)
    client.get("/search")
    with client.session_transaction() as student:
        current = student["session_id"]
    earlier = {"session_id": "earlier-session", "batch_id": "pending-from-earlier-page",
               "logs": [{"uid": "1", "sessionID": "earlier-session", "type": "TaskStarted"}]}
    first = client.post("/log_session", json=earlier)
    assert first.status_code == 200
    assert first.json["status"] == "logged" and first.json["batch_id"] == earlier["batch_id"]
    assert first.json["recovered_incomplete"] == {"1": 1}
    assert client.post("/log_session", json=earlier).json == first.json  # a retry is not written twice
    recovered = (tmp_path / "v2" / "1_earlier-session_INCOMPLETE.log").read_text().splitlines()
    assert [json.loads(line)["type"] for line in recovered] == ["TaskStarted", "incompleteExperiment"]
    newer = {"session_id": current, "batch_id": "newer", "logs": [final_event(client, "a")]}
    assert client.post("/log_session", json=newer).status_code == 200


def test_idle_limit_counts_and_applies_on_every_page(student_modules):
    module = student_modules()
    schedule(module)
    client = module.app.test_client()
    client.post("/start", data={"user_id": "1"})
    client.get("/task")
    confirm_first(client)
    client.get("/search")

    def idle(minutes):
        with client.session_transaction() as student:
            student["last_active"] = (datetime.now() - timedelta(minutes=minutes)).isoformat()

    # Reading a result page is activity: a long task does not end while the child keeps going.
    idle(50)
    assert client.get("/webpage?url=https://example.org/page").status_code == 200
    with client.session_transaction() as student:
        assert datetime.now() - datetime.fromisoformat(student["last_active"]) < timedelta(minutes=1)
    assert client.get("/search").status_code == 200
    # A run left open for an hour ends on whichever page is opened first, so it
    # cannot continue days later on the same device.
    for path in ("/webpage?url=https://example.org/page", "/result?query=api&page=1", "/search"):
        client.post("/start", data={"user_id": "1"})
        client.get("/task")
        client.get("/search")
        idle(70)
        response = client.get(path)
        assert response.status_code == 302 and response.location.endswith("/welcome"), path
        with client.session_transaction() as student:
            assert "user_id" not in student, path


def test_children_see_the_line_breaks_of_a_multi_line_question():
    css = (APP_ROOT / "static" / "main.css").read_text()
    for selector in (".task-question", ".task-help-question"):
        rule = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
        assert rule and "white-space: pre-line" in rule[1], selector
    preview = (APP_ROOT / "research_dashboard" / "static" / "workflow.css").read_text()
    assert re.search(r"\.preview-task-question \{[^}]*white-space:pre-line", preview)


def test_start_button_is_disabled_after_the_first_tap():
    template = (APP_ROOT / "templates" / "start.html").read_text()
    assert 'form.dataset.submitting === "1"' in template and "startIdButton.disabled = true" in template
    assert 'addEventListener("pageshow"' in template
