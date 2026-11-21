"""The tablets' signal: the live view's "Fuori dalla pagina" and "Nessun segnale", kept away from the logs."""
import re
import sqlite3
import time
from pathlib import Path

import pytest

from research_dashboard.presence import SILENT_AFTER_SECONDS, Presence
from .test_live_view import log_events, rows, signed_in, started, task
from .test_research_dashboard import app  # noqa: F401
from .test_study_enrollment import question_set, schedule, student_modules  # noqa: F401

@pytest.fixture
def site(student_modules):
    module = student_modules()
    schedule(module, question_set())
    return module


def signals(module):
    with sqlite3.connect(module.app.extensions["research"]["presence"].path) as db:
        return db.execute("SELECT technical_session_id, participant_id, page, visible FROM presence").fetchall()


def test_the_signal_answers_before_an_id_and_records_nothing(site):
    client = site.app.test_client()
    assert client.post("/presenza", json={"page": "/prova", "visible": True}).status_code == 204
    assert signals(site) == []


def test_a_runs_signal_records_its_page_and_visibility(site):
    client = site.app.test_client()
    client.post("/start", data={"user_id": "1"})
    with client.session_transaction() as saved:
        technical = saved["session_id"]
    assert client.post("/presenza", json={"page": "/search", "visible": True}).status_code == 204
    assert client.post("/presenza", json={"page": "/search", "visible": False}).status_code == 204
    assert signals(site) == [(technical, "1", "/search", 0)]


def test_the_signal_is_not_activity_and_writes_no_log_or_session(site):
    client = site.app.test_client()
    client.post("/start", data={"user_id": "1"})
    with client.session_transaction() as saved:
        before = dict(saved)
    files = sorted(path.name for path in Path(site.LOG_DIR).rglob("*") if path.is_file())
    for _ in range(3):
        client.post("/presenza", json={"page": "/task", "visible": True})
    with client.session_transaction() as saved:
        assert dict(saved) == before, "the idle limit and the run must not see the signal"
    assert sorted(path.name for path in Path(site.LOG_DIR).rglob("*") if path.is_file()) == files


@pytest.mark.parametrize("body", [b"not json", b"[1, 2]", b""])
def test_a_malformed_signal_is_answered_and_ignored(site, body):
    client = site.app.test_client()
    client.post("/start", data={"user_id": "1"})
    assert client.post("/presenza", data=body, content_type="application/json").status_code == 204
    assert signals(site) == []


def test_presence_states_follow_visibility_and_silence(tmp_path):
    presence = Presence(tmp_path)
    now = time.time()
    presence.beat("run-a", "1", "/search", True, now=now)
    presence.beat("run-b", "2", "/webpage", False, now=now)
    presence.beat("run-c", "3", "/task", True, now=now - SILENT_AFTER_SECONDS - 5)
    seen = presence.latest(["run-a", "run-b", "run-c", "run-unknown"], now=now)
    assert seen["run-a"]["state"] == "visible" and seen["run-b"]["state"] == "hidden"
    assert seen["run-c"]["state"] == "silent" and seen["run-c"]["seconds"] == SILENT_AFTER_SECONDS + 5
    assert "run-unknown" not in seen


def test_a_broken_presence_file_never_raises(tmp_path):
    presence = Presence(tmp_path)
    presence.path.write_bytes(b"not a database")
    assert presence.beat("run", "1", "/search", True) is False
    assert presence.latest(["run"]) == {}


def test_the_live_view_shows_off_the_page_and_no_signal(app):  # noqa: F811
    client, _ = signed_in(app)
    presence = app.extensions["research"]["presence"]
    started(app, "1")
    started(app, "2")
    started(app, "3")
    log_events(app, "3", "run-1", *task(1, "TaskStarted", "TaskEnded"), *task(2, "TaskStarted", "TaskEnded"),
               *task(3, "TaskStarted", "TaskEnded"))
    now = time.time()
    presence.beat("1-run-1", "1", "/search", False, now=now)
    presence.beat("2-run-1", "2", "/task", True, now=now - 75)
    presence.beat("3-run-1", "3", "/fine", False, now=now)
    _, by_id = rows(client)
    assert "Off the page" in by_id["1"]["html"]
    assert re.search(r"No signal for (7[5-9]|8\d) s", by_id["2"]["html"])
    assert "live-presence" not in by_id["3"]["html"], "a finished child needs no signal"
    assert "live-presence" not in by_id["4"]["html"], "nor one who has not started"
    italian = client.get("/dashboard/sessions/grade-4-session-1/live?lang=it").text
    assert "Fuori dalla pagina" in italian and "Nessun segnale da" in italian


def test_a_visible_tablet_adds_nothing_to_its_row(app):  # noqa: F811
    client, _ = signed_in(app)
    started(app, "1")
    app.extensions["research"]["presence"].beat("1-run-1", "1", "/search", True)
    _, by_id = rows(client)
    assert "live-presence" not in by_id["1"]["html"]
