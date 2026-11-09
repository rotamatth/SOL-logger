"""A test ID runs a permanent experiment on any day and as often as needed, apart from the results."""
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import pytest

from .test_connected_first_answer import begin
from .test_editable_recap import commit, complete_today
from .test_study_enrollment import metadata_files, schedule, student_modules  # noqa: F401

TEST_ID = "TEST-spazio"
TODAY_SESSION = "grade-4-session-2"


def start(module, uid=TEST_ID, client=None):
    client = client or module.app.test_client()
    assert client.post("/start", data={"user_id": uid}).status_code == 302
    return client


def real_files(tmp_path):
    return sorted(path.name for path in (tmp_path / "v2").iterdir()
                  if path.is_file() and not path.name.startswith("."))


def in_test_folder(tmp_path):
    return sorted(path.name for path in (tmp_path / "v2" / "test-runs").iterdir()
                  if not path.name.startswith("."))


def run_state(client):
    with client.session_transaction() as saved:
        return dict(saved)


def indexed_participants(module):
    research = module.app.extensions["research"]
    research["index"].refresh(force=True)
    return {run["participant_id"] for run in research["index"].summaries(research["state"].settings())}


def test_the_test_ids_close_the_start_list(student_modules):
    module = student_modules()
    options = re.findall(r'<option value="([^"]+)">', module.app.test_client().get("/start").text)
    assert options[-2:] == ["TEST-spazio", "TEST-orecchio"]
    assert options[:-2] == [str(number) for number in range(1, len(options) - 1)]


@pytest.mark.parametrize(("uid", "theme", "clip"), [("TEST-spazio", "space", "Spazio_0"),
                                                    ("TEST-orecchio", "ear", "Orecchio_0")])
def test_a_test_id_needs_no_session_and_has_its_theme(student_modules, uid, theme, clip):
    module = student_modules()
    assert not any(item["date"] for item in module.RESEARCH_STATE.settings()["sessions"])
    client = start(module, uid)
    page = client.get("/task")
    assert page.status_code == 200 and "PROVA" in page.text and 'id="first-answer-form"' in page.text
    with module.app.test_request_context():
        from flask import session
        session.update(run_state(client))
        assert module.run_theme() == theme
    complete_today(client)
    assert clip in client.get("/task-review/1").text or clip in client.get("/thank_you").text


def test_the_test_ids_ask_the_questions_of_the_10_november_sessions():
    """TEST-spazio asks what the setup gave 4a spazio, TEST-orecchio what Diletta entered for 5a orecchio, in clip order."""
    from research_dashboard.permanent_test import TEST_EXPERIMENTS
    spec = importlib.util.spec_from_file_location(
        "setup_session_for_test_ids", Path(__file__).resolve().parents[1] / "tools" / "setup_session_2026_11_10.py")
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)

    def rows(uid):
        return tuple((item["topic"], item["question"]) for item in TEST_EXPERIMENTS[uid]["questions"])

    assert rows("TEST-spazio") == setup.SPAZIO_QUESTIONS
    assert rows("TEST-orecchio") == (
        ("Fact-finding -- Ossicini Orecchio", "Quali sono i 3 ossicini dentro al nostro orecchio?"),
        ("Multi-step -- Coclea", "Che forma ha la coclea e dove si trova?"),
        ("Open-ended -- animali", "Quali sono 5 animali con l'udito più sviluppato al mondo?"))


def test_a_whole_test_run_stays_out_of_the_real_folder(student_modules, tmp_path):
    module = student_modules()
    client = start(module)
    auth = complete_today(client)
    assert commit(client, auth, "finish").status_code == 200
    assert real_files(tmp_path) == []
    names = in_test_folder(tmp_path)
    assert sum(name.endswith("_FULL.log") for name in names) == 1
    assert sum(name.endswith(".run.json") for name in names) == 1
    assert sum("_task" in name for name in names) == 3
    assert all(name.startswith(f"{TEST_ID}_") for name in names)
    full = next(tmp_path / "v2" / "test-runs" / name for name in names if name.endswith("_FULL.log"))
    events = [json.loads(line) for line in full.read_text().splitlines()]
    assert {"TaskStarted", "TaskEnded", "sessionCompleted"} <= {event["type"] for event in events}
    assert all(event["is_test"] is True for event in events if event.get("source") == "server")
    assert not (tmp_path / "v2" / ".uploads.sqlite3").exists()


def test_results_never_see_a_test_run_beside_a_real_child(student_modules, tmp_path):
    module = student_modules()
    schedule(module)
    child = begin(module, "1")
    complete_today(child)
    complete_today(start(module))
    state = module.RESEARCH_STATE
    assert indexed_participants(module) == {"1"}
    assert [item["participant_id"] for item in state.session_attempts(TODAY_SESSION)] == ["1"]
    today = datetime.now(ZoneInfo("Europe/Zurich")).date().isoformat()
    assert state.progress_ids_for_date(today) == {"1"}
    assert state.progress_run_for_date(TEST_ID, today) is None
    assert ["is_test" in sidecar for sidecar in metadata_files(tmp_path)] == [False]
    assert all(name.startswith("1_") or name == "log_registry.jsonl" for name in real_files(tmp_path))
    assert TEST_ID not in (tmp_path / "v2" / "log_registry.jsonl").read_text()


def test_every_restart_is_a_new_attempt_as_often_as_needed(student_modules, tmp_path):
    module = student_modules()
    client = start(module)
    seen = {run_state(client)["progress_id"]}
    complete_today(client)
    for _ in range(2):
        response = client.get("/test-run/restart")
        assert response.status_code == 302 and response.location.endswith("/start")
        assert 'id="enter-id-form"' in client.get("/start").text
        start(module, client=client)
        seen.add(run_state(client)["progress_id"])
    assert len(seen) == 3
    assert sum(name.endswith(".run.json") for name in in_test_folder(tmp_path)) == 3
    assert 'id="first-answer-form"' in client.get("/task").text


def test_a_double_tap_still_starts_one_attempt(student_modules, tmp_path):
    module = student_modules()
    client = start(module)
    first_attempt = run_state(client)["progress_id"]
    start(module, client=client)
    assert run_state(client)["progress_id"] == first_attempt
    assert sum(name.endswith(".run.json") for name in in_test_folder(tmp_path)) == 1


def test_a_childs_run_cannot_be_left_and_carries_no_test_marks(student_modules, tmp_path):
    module = student_modules()
    schedule(module)
    child = begin(module, "1")
    before = run_state(child)["progress_id"]
    page = child.get("/task").text
    assert "PROVA" not in page and "test-run" not in page
    assert child.get("/test-run/restart").status_code == 302
    assert run_state(child)["progress_id"] == before
    [sidecar] = metadata_files(tmp_path)
    assert "is_test" not in sidecar and sidecar["participant_id"] == "1"
    assert '"is_test"' not in page.split("window.STUDY_PROGRESS_CONTEXT =", 1)[1].split(";", 1)[0]


def test_unsent_test_events_reaching_a_childs_browser_go_to_the_test_folder(student_modules, tmp_path):
    module = student_modules()
    schedule(module)
    client = start(module)
    old = run_state(client)["session_id"]
    client.get("/test-run/restart")
    start(module, "1", client=client)
    event = {"type": "pageView", "uid": TEST_ID, "sessionID": old}
    assert client.post("/log_session", json={"session_id": old, "logs": [event]}).status_code == 200
    assert f"{TEST_ID}_{old}_INCOMPLETE.log" in in_test_folder(tmp_path)
    assert not any("INCOMPLETE" in name for name in real_files(tmp_path))
    assert indexed_participants(module) == {"1"}


def test_a_test_event_without_a_server_run_goes_to_the_test_folder(student_modules, tmp_path):
    """Leaving a test run at its introduction leaves the choice of ID unsent, under the browser's own ID."""
    module = student_modules()
    schedule(module)
    client = begin(module, "1")
    event = {"type": "idSubmitted", "uid": TEST_ID, "sessionID": "browser-made"}
    assert client.post("/log_session", json={"session_id": "browser-made", "logs": [event]}).status_code == 200
    assert f"{TEST_ID}_browser-made_INCOMPLETE.log" in in_test_folder(tmp_path)
    assert not any("TEST" in name for name in real_files(tmp_path))
    child = {"type": "idSubmitted", "uid": "1", "sessionID": "another"}
    assert client.post("/log_session", json={"session_id": "another", "logs": [child]}).status_code == 200
    assert "1_another_INCOMPLETE.log" in real_files(tmp_path)


def test_unsent_child_events_reaching_a_test_browser_stay_with_the_child(student_modules, tmp_path):
    module = student_modules()
    schedule(module)
    client = begin(module, "1")
    old = run_state(client)["session_id"]
    with client.session_transaction() as saved:
        saved.clear()
    start(module, client=client)
    event = {"type": "pageView", "uid": "1", "sessionID": old}
    assert client.post("/log_session", json={"session_id": old, "logs": [event]}).status_code == 200
    assert f"1_{old}_INCOMPLETE.log" in real_files(tmp_path)
    assert not any("INCOMPLETE" in name for name in in_test_folder(tmp_path))


def test_a_test_file_in_the_real_folder_is_never_read_as_a_child(student_modules, tmp_path):
    module = student_modules()
    (tmp_path / "v2" / f"{TEST_ID}_abc_INCOMPLETE.log").write_text(json.dumps({"type": "pageView"}) + "\n")
    assert indexed_participants(module) == set()


def test_a_test_attempt_that_was_not_published_goes_to_the_test_folder(student_modules, tmp_path):
    module = student_modules()
    client = start(module)
    research = module.app.extensions["research"]
    with research["state"].connect() as db:
        db.execute("UPDATE study_attempts SET published=0")
    for path in (tmp_path / "v2" / "test-runs").glob("*.run.json"):
        path.unlink()
    from research_dashboard.collection import publish_pending_runs
    publish_pending_runs(str(tmp_path / "v2"), research["state"])
    assert real_files(tmp_path) == []
    assert sum(name.endswith(".run.json") for name in in_test_folder(tmp_path)) == 1
    assert run_state(client)["user_id"] == TEST_ID
