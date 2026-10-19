"""Unused sessions can be removed and restored without changing identity/history."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import json

import pytest

from .test_research_dashboard import app, configure, csrf, login, write_run
from .test_study_enrollment import question_set
from research_dashboard.state import identity, validate_settings
from research_dashboard.study_config import assignment_for, scheduled_assignment, session_readiness

URL = "/dashboard/settings?section=sessions&grade=4"


def action(client, state, session_id, operation="remove_session", **extra):
    return client.post(URL, data={"action": operation, "csrf": csrf(client.get(URL)),
                       "revision": state.settings()["revision"], "session_id": session_id,
                       "confirm_remove": "1", **extra})


def test_remove_middle_session_preserves_draft_and_restore_recovers_exact_configuration(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    settings = configure(app)
    target = settings["sessions"][1]
    target["question_set"] = question_set("Saved draft", approved=False)
    state.save_settings(settings, settings["revision"])
    before = state.settings()
    response = action(client, state, target["id"])
    assert response.status_code == 302
    removed = state.settings()
    assert removed["sessions"][1] == {**before["sessions"][1], "removed": True}
    assert removed["sessions"][:1] == before["sessions"][:1]
    assert removed["sessions"][2:] == before["sessions"][2:]
    page = client.get(response.location)
    assert 'id="grade-4-session-2"' not in page.text
    assert "Removed sessions (1)" in page.text
    assert "Restore session" in page.text
    assert client.get(f"/dashboard/settings/questions/{target['id']}").status_code == 404
    assert action(client, state, target["id"], "restore_session").status_code == 302
    restored = state.settings()["sessions"][1]
    assert restored == {**before["sessions"][1], "removed": False}
    assert "Saved draft question 1" in client.get(f"/dashboard/settings/questions/{target['id']}").text


def test_removing_latest_reserves_number_and_allows_reusing_only_date(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    configure(app)
    assert action(client, state, "grade-4-session-3").status_code == 302
    current = state.settings()
    created = state.add_study_session("4", "2026-10-03", current["revision"], "Replacement")
    assert created["id"] == "grade-4-session-4" and created["number"] == 4
    conflict = action(client, state, "grade-4-session-3", "restore_session")
    assert conflict.status_code == 400 and "cannot use the same date" in conflict.text
    assert action(client, state, "grade-4-session-3", "restore_session", date="2026-10-04").status_code == 302


def test_removed_sessions_never_resolve_student_assignments(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    settings = configure(app)
    settings["sessions"][0]["question_set"] = question_set()
    state.save_settings(settings, settings["revision"])
    today = date(2026, 10, 1)
    assert scheduled_assignment(state.settings(), "1", today)
    assert action(client, state, "grade-4-session-1").status_code == 302
    settings = state.settings()
    assert scheduled_assignment(settings, "1", today) is None
    assert assignment_for(settings, "1", "grade-4-session-1") is None
    readiness = session_readiness(settings, settings["sessions"][0])
    assert readiness["ready"] == 0
    assert all(person["problem"] == "session_removed" for person in readiness["participants"])


@pytest.mark.parametrize("metadata_only,trashed", [(False, False), (False, True), (True, False)])
def test_started_or_trashed_records_block_removal_without_touching_sources(app, metadata_only, trashed):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    configure(app)
    key, root, stem = write_run(app)
    if metadata_only:
        for path in root.glob("*.log"):
            path.unlink()
    if trashed:
        state.trash_run(key)
    originals = {path: path.read_bytes() for path in root.iterdir()}
    before = state.settings()
    response = action(client, state, "grade-4-session-1")
    assert response.status_code == 400 and "has participant records" in response.text
    assert state.settings() == before
    assert {path: path.read_bytes() for path in root.iterdir()} == originals


def test_explicit_recorded_session_blocks_removal_even_with_conflicting_identity(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    configure(app)
    _, root, stem = write_run(app)
    path = root / f"{stem}.run.json"
    metadata = json.loads(path.read_text())
    metadata.update(participant_id="21", study_session_at_collection="grade-4-session-2")
    path.write_text(json.dumps(metadata))
    response = action(client, state, "grade-4-session-2")
    assert response.status_code == 400 and "has participant records" in response.text


@pytest.mark.parametrize("problem", ["missing-directory", "malformed-source"])
def test_uncertain_storage_blocks_removal(app, problem):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    configure(app)
    root = Path(app.config["RESEARCH_LEGACY_LOG_DIR"])
    if problem == "missing-directory":
        root.rmdir()
    else:
        (root / "unknown_FULL.log").write_text("not valid JSON\n")
    before = state.settings()
    response = action(client, state, "grade-4-session-1")
    assert response.status_code == 400 and "Unable to verify" in response.text
    assert state.settings() == before


def test_legacy_session_records_are_protected(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    settings = configure(app)
    settings["historical_grades"] = [{"id": "1" * 24, "collection": "legacy", "grade": "4",
        "school_year": "2026/2027", "date_from": "2026-10-01", "date_to": "2026-10-31",
        "start": 1, "end": 20, "prefix": "", "width": 0}]
    state.save_settings(settings, settings["revision"])
    write_run(app, collection="legacy", metadata=False)
    response = action(client, state, "grade-4-session-1")
    assert response.status_code == 400 and "has participant records" in response.text


def test_all_sessions_can_be_removed_without_removing_grade_or_reusing_ids(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    configure(app)
    for number in (1, 2, 3):
        assert action(client, state, f"grade-4-session-{number}").status_code == 302
    assert client.get(URL).status_code == 200
    assert "No sessions yet" in client.get(URL).text
    assert client.get("/dashboard/settings?section=participants&grade=4").status_code == 200
    assert client.get("/dashboard?grade=4").status_code == 200
    settings = state.settings()
    assert state.add_study_session("4", "2026-10-01", settings["revision"])["number"] == 4


def test_confirmation_auth_csrf_and_revision_are_required(app):
    state = app.extensions["research"]["state"]
    configure(app)
    guest = app.test_client()
    assert guest.post(URL, data={"action": "remove_session"}).status_code == 302
    client = app.test_client()
    login(client)
    before = state.settings()
    assert action(client, state, "grade-4-session-1", confirm_remove="").status_code == 400
    assert action(client, state, "grade-4-session-1", csrf="forged").status_code == 400
    assert action(client, state, "grade-4-session-1", revision=before["revision"] - 1).status_code == 400
    assert state.settings() == before
    assert action(client, state, "grade-5-session-1").status_code == 400


def test_in_flight_run_arriving_after_removal_keeps_history_accessible(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    settings = configure(app)
    original_session = deepcopy(settings["sessions"][0])
    assert action(client, state, original_session["id"]).status_code == 302
    key, root, stem = write_run(app)
    sidecar = root / f"{stem}.run.json"
    metadata = json.loads(sidecar.read_text())
    metadata.update(study_session_at_collection=original_session["id"],
                    study_session_snapshot=original_session)
    sidecar.write_text(json.dumps(metadata))
    originals = {path: path.read_bytes() for path in root.iterdir()}
    app.extensions["research"]["index"].refresh(force=True)
    assert client.get(f"/dashboard?grade=4&session={original_session['id']}").status_code == 200
    participant = client.get(f"/dashboard/participants/v2/{identity('1')}?session={original_session['id']}&view=logs")
    assert participant.status_code == 200 and key in participant.text
    assert client.get(f"/dashboard/runs/{key}").status_code == 200
    assert {path: path.read_bytes() for path in root.iterdir()} == originals


@pytest.mark.parametrize("invalid", ["1", 1, None, [], {}])
def test_removed_flag_must_be_boolean(app, invalid):
    settings = deepcopy(app.extensions["research"]["state"].settings())
    settings["sessions"][0]["removed"] = invalid
    with pytest.raises(ValueError, match="invalid_sessions"):
        validate_settings(settings)
