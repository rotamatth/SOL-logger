"""The live view reports started attempts and finished questions from the original logs."""
import json
import re
from pathlib import Path

import pytest

from .test_research_dashboard import app, configure, csrf, identity, login  # noqa: F401
from .test_study_enrollment import question_set, student_modules  # noqa: F401

YEAR = "2026/2027"
SESSION = "grade-4-session-1"
LIVE = f"/dashboard/sessions/{SESSION}/live"
DATA = LIVE + ".json"


def started(app, uid, run="run-1", order=("1", "2", "3"), at="2026-11-05T09:00:00.000+01:00", session=SESSION):
    state = app.extensions["research"]["state"]
    metadata = {"participant_id": uid, "technical_session_id": f"{uid}-{run}", "log_id": run, "started_at": at,
                "experiment_date": "2026-11-05", "assignment_source": "shared",
                "tasks": [{"presented_number": number, "topic_id": topic, "question": f"Question {topic}?"}
                          for number, topic in enumerate(order, 1)]}
    with state.connect() as db:
        db.execute("INSERT INTO study_attempts VALUES (?,?,?,?,1)",
                   (metadata["technical_session_id"], session, uid, json.dumps(metadata)))
    return metadata


def log_events(app, uid, run, *events, partial=None):
    path = Path(app.config["RESEARCH_LOG_DIR"]) / f"{uid}_{run}_FULL.log"
    with path.open("ab") as target:
        for event in events:
            target.write((json.dumps(event) + "\n").encode())
        if partial:
            target.write(partial)
    return path


def task(number, *kinds, minute=0, answer="Synthetic"):
    events = []
    for offset, kind in enumerate(kinds):
        event = {"type": kind, "task_number": number, "timestamp": f"2026-11-05T09:{minute + offset:02d}:00.000"}
        if kind == "TaskEnded":
            event["answer"] = answer
        events.append(event)
    return events


def signed_in(app, questions=True):
    settings = configure(app)
    state = app.extensions["research"]["state"]
    if questions:
        settings["sessions"][0]["question_set"] = question_set()
        state.save_settings(settings, settings["revision"])
    client = app.test_client()
    login(client)
    return client, state


def rows(client):
    response = client.get(DATA)
    assert response.status_code == 200
    return response.json, {row["id"]: row for row in response.json["rows"]}


def test_every_expected_child_is_listed_as_not_started_before_anyone_begins(app):
    client, _ = signed_in(app)
    page = client.get(LIVE)
    assert page.status_code == 200 and page.text.count('class="live-child live-not_started"') == 20
    data, by_id = rows(client)
    assert len(by_id) == 20 and "Not started" in by_id["1"]["html"]
    assert "<dd>20</dd>" in data["totals"]


def test_a_started_child_with_nothing_saved_is_in_progress_without_guessing(app):
    client, _ = signed_in(app)
    started(app, "1")
    _, by_id = rows(client)
    assert "In progress" in by_id["1"]["html"] and "Nothing saved yet" in by_id["1"]["html"]
    assert "Question 1 / 3" in by_id["1"]["html"]


def test_figures_appear_only_once_a_question_is_finished(app):
    client, _ = signed_in(app)
    started(app, "1")
    log_events(app, "1", "run-1", *task(1, "TaskStarted", "querySubmitted", "clickedResult", "TaskEnded"),
               *task(2, "TaskStarted", "querySubmitted", minute=5))
    _, by_id = rows(client)
    html = by_id["1"]["html"]
    assert "Question 2 / 3" in html and "1 / 3 finished" in html
    assert "3 min" in html  # Question 1 ran from minute 0 to minute 3.
    assert "since 09:05" in html
    assert "Not reached yet" in html
    assert html.count('<td data-label="Time">') == 1  # Only the finished question has figures.
    assert "2 searches" in html


def test_three_finished_questions_complete_the_child_in_the_totals(app):
    client, _ = signed_in(app)
    started(app, "1")
    log_events(app, "1", "run-1", *[event for number in (1, 2, 3) for event in task(number, "TaskStarted", "TaskEnded")])
    data, by_id = rows(client)
    assert "Completed" in by_id["1"]["html"] and "3 / 3 finished" in by_id["1"]["html"]
    assert "<dt>Completed</dt><dd>1</dd>" in data["totals"].replace("\n", "")
    assert "Question 1?" in data["questions"]


def test_a_partial_last_line_and_bad_lines_are_ignored(app):
    client, _ = signed_in(app)
    started(app, "1")
    path = log_events(app, "1", "run-1", *task(1, "TaskStarted"), partial=b'{"type":"TaskEnded","task_number":1')
    _, by_id = rows(client)
    assert "1 / 3 finished" not in by_id["1"]["html"] and "0 / 3 finished" in by_id["1"]["html"]
    with path.open("ab") as target:
        target.write(b'\nnot json\n[1,2]\n{"type":"TaskStarted","task_number":true}\n')
    assert rows(client)[1]["1"]["html"]


def test_an_answer_saved_after_a_refresh_is_picked_up(app):
    client, _ = signed_in(app)
    started(app, "1")
    log_events(app, "1", "run-1", *task(1, "TaskStarted"))
    first = rows(client)[1]["1"]
    log_events(app, "1", "run-1", *task(1, "TaskEnded"))
    second = rows(client)[1]["1"]
    assert second["digest"] != first["digest"] and "1 / 3 finished" in second["html"]
    assert rows(client)[1]["1"]["digest"] == second["digest"]  # Unchanged data keeps its digest.


def test_the_latest_run_decides_the_row_and_the_count_shows(app):
    client, _ = signed_in(app)
    started(app, "1", "run-1", at="2026-11-05T09:00:00.000+01:00")
    started(app, "1", "run-2", at="2026-11-05T09:30:00.000+01:00")
    log_events(app, "1", "run-1", *task(1, "TaskStarted", "TaskEnded"))
    log_events(app, "1", "run-2", *task(1, "TaskStarted"))
    html = rows(client)[1]["1"]["html"]
    assert "0 / 3 finished" in html and "2 runs" in html


def test_trashed_runs_are_left_out(app):
    client, state = signed_in(app)
    started(app, "1")
    log_events(app, "1", "run-1", *task(1, "TaskStarted", "TaskEnded"))
    state.trash_run(identity("v2\0" + "1_run-1"))
    assert "Not started" in rows(client)[1]["1"]["html"]


def test_other_sessions_stay_out_and_a_child_no_longer_expected_stays_listed(app):
    client, state = signed_in(app)
    started(app, "2", session="grade-4-session-2")
    started(app, "21")  # Enrolled in another class, but really started here.
    _, by_id = rows(client)
    assert "Not started" in by_id["2"]["html"]
    assert "In progress" in by_id["21"]["html"]


def test_questions_group_by_what_was_asked_when_order_is_shuffled(app):
    client, _ = signed_in(app)
    started(app, "1", order=("1", "2", "3"))
    started(app, "2", order=("2", "1", "3"))
    log_events(app, "1", "run-1", *task(1, "TaskStarted", "TaskEnded"))
    log_events(app, "2", "run-1", *task(2, "TaskStarted", "TaskEnded"))
    data, _ = rows(client)
    # Child 1 saw it first and child 2 second: it is one question, finished by two children.
    assert data["questions"].count('class="stats-question"') == 1
    assert "Question 1?" in data["questions"] and '<td data-label="Finished">2 / 20</td>' in data["questions"]


def test_sign_in_is_required_and_failures_are_json(app):
    client, _ = signed_in(app)
    guest = app.test_client()
    assert guest.get(LIVE).status_code == 302
    expired = guest.get(DATA)
    assert expired.status_code == 401 and expired.is_json
    missing = client.get("/dashboard/sessions/unknown/live.json")
    assert missing.status_code == 404 and missing.is_json


def test_a_removed_session_has_no_live_view(app):
    client, state = signed_in(app)
    settings = state.settings()
    settings["sessions"][0]["removed"] = True
    state.save_settings(settings, settings["revision"])
    assert client.get(LIVE).status_code == 404


def test_reading_never_changes_state_or_logs(app):
    client, state = signed_in(app)
    started(app, "1")
    path = log_events(app, "1", "run-1", *task(1, "TaskStarted"))
    before, content = state.settings(), path.read_bytes()
    for _ in range(3):
        rows(client)
    assert state.settings() == before and path.read_bytes() == content


def test_only_a_session_running_today_refreshes_itself(app, monkeypatch):
    client, _ = signed_in(app)
    assert "data-live-url" not in client.get(LIVE).text
    assert "not running today" in client.get(LIVE).text
    monkeypatch.setattr("research_dashboard.live_views.zurich_today", lambda: "2026-10-01")
    today = client.get(LIVE)
    assert "data-live-url" in today.text and "not running today" not in today.text


@pytest.mark.parametrize("lang,text", [("en", "Not started"), ("it", "Non iniziato")])
def test_the_page_is_translated(app, lang, text):
    client, _ = signed_in(app)
    assert text in client.get(LIVE + f"?lang={lang}").text
    assert text in client.get(DATA + f"?lang={lang}").json["rows"][0]["html"]


def test_the_list_and_session_page_link_to_it_only_on_the_day(app, monkeypatch):
    monkeypatch.setattr("research_dashboard.session_views.zurich_today", lambda: "2026-10-01")
    monkeypatch.setattr("research_dashboard.preparation_views.zurich_today", lambda: "2026-10-01")
    client, _ = signed_in(app)
    listed = client.get(f"/dashboard/sessions?grade=4&year={YEAR}")
    assert listed.text.count(f"/dashboard/sessions/{SESSION}/live") == 1
    assert "/dashboard/sessions/grade-4-session-2/live" not in listed.text
    session_page = client.get(f"/dashboard/prepare?grade=4&year={YEAR}&session={SESSION}")
    assert f"/dashboard/sessions/{SESSION}/live" in session_page.text
    assert "/live" not in client.get(f"/dashboard/prepare?grade=4&year={YEAR}&session=grade-4-session-2").text
    assert csrf(session_page)


def test_a_real_student_run_reaches_the_live_view(student_modules):
    """Real admission, first answer and upload route, with no shortcut through the test helpers."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from werkzeug.security import generate_password_hash

    from .enrollment_helpers import enroll_initial_roster, school_year
    from .progress_helpers import confirm_first, final_event
    from .test_research_dashboard import PASSWORD

    module = student_modules()
    module.app.config.update(RESEARCH_PASSWORD_HASH=generate_password_hash(PASSWORD, method="pbkdf2:sha256:1000"),
                             RESEARCH_PASSWORD_HASH_FILE="")
    state = module.RESEARCH_STATE
    settings = state.settings()
    session = next(item for item in settings["sessions"] if item["id"] == SESSION)
    session.update(date=datetime.now(ZoneInfo("Europe/Zurich")).date().isoformat(), question_set=question_set())
    enroll_initial_roster(settings, school_year(session["date"]))
    state.save_settings(settings, settings["revision"])
    researcher, student = module.app.test_client(), module.app.test_client()
    login(researcher)

    assert "Not started" in rows(researcher)[1]["1"]["html"]
    assert student.post("/start", data={"user_id": "1"}).status_code == 302
    assert "In progress" in rows(researcher)[1]["1"]["html"]
    confirm_first(student)
    with student.session_transaction() as active:
        sid = active["session_id"]

    def upload(*events):
        logs = [{"uid": "1", "sessionID": sid, **event} for event in events]
        response = student.post("/log_session", json={"session_id": sid, "logs": logs})
        assert response.status_code == 200, response.data[:200]

    upload({"type": "querySubmitted", "timestamp": "2026-11-05T09:00:30.000", "query": "synthetic"},
           {"type": "clickedResult", "timestamp": "2026-11-05T09:01:00.000", "rank": "2"})
    html = rows(researcher)[1]["1"]["html"]
    assert "0 / 3 finished" in html and "1 search<" in html and "since " in html
    upload(final_event(student, "Synthetic answer"))
    data, by_id = rows(researcher)
    html = by_id["1"]["html"]
    assert "1 / 3 finished" in html and "average position 2" in html
    # Start and end now come from the server's clock, so the time is real: it must show, not "—".
    assert re.search(r'data-label="Time">\d+ (s|min)', html)
    assert 'data-label="Finished">1 / 20</td>' in data["questions"]
