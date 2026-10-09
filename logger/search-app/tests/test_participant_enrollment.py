"""Enrollment uses temporary settings and logs; no real collection is modified."""
from pathlib import Path
import importlib.util
import json
import sys
import types

import pytest
from werkzeug.security import generate_password_hash

from .test_research_dashboard import APP_ROOT, PASSWORD, app, csrf, login
from research_dashboard.student_config import eligible_students, task_catalog
from research_dashboard.collection import record_run


def ranges_form(app, client, **changes):
    page = client.get("/dashboard/settings?grade=4")
    settings = app.extensions["research"]["state"].settings()
    fields = {"action": "save_ranges", "revision": settings["revision"],
              "csrf": csrf(page), "ranges_editor": "1"}
    for rule in settings["ranges"]:
        grade = rule["grade"]
        for key in ("start", "end", "width", "prefix"):
            fields[f"{grade}_{key}"] = rule[key]
        fields[f"{grade}_task_set"] = "saved" if rule.get("assignment") else "existing"
        fields[f"{grade}_assignment_mode"] = rule.get("assignment", {}).get("mode", "missing")
        if grade == "3":
            fields["3_enabled"] = "1"
    fields.update(changes)
    return fields


def test_preview_shows_readiness_exact_ids_and_changes_without_saving(app):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    before = state.settings()
    task_set = task_catalog(app)[0]
    assert len(eligible_students(app, before)) == 18
    response = client.post("/dashboard/settings?grade=4", data=ranges_form(
        app, client, action="preview_ranges", **{"4_end": 22, "5_start": 23,
                                                 "5_task_set": task_set["id"]}))
    assert response.status_code == 200
    assert "Preview — changes have not been saved" in response.text
    assert "18 / 22 ready to start" in response.text
    assert "<strong>18</strong> IDs becoming available in student login" in response.text
    assert "2 IDs changing grade" in response.text
    assert 'name="4_end" value="22"' in response.text
    assert state.settings() == before


def test_preview_explains_student_access_and_effective_question_changes(app):
    client = app.test_client()
    login(client)
    catalog = task_catalog(app)
    before = app.extensions["research"]["state"].settings()
    response = client.post("/dashboard/settings", data=ranges_form(
        app, client, action="preview_ranges", **{"4_task_set": catalog[0]["id"],
                                                 "4_assignment_mode": "all"}))
    assert response.status_code == 200
    assert "<strong>2</strong> IDs becoming available in student login" in response.text
    assert "<strong>8</strong> IDs receiving different questions or rewards" in response.text
    assert "Review each participant&#39;s assignment (20)" in response.text
    assert "20 / 20 ready to start" in response.text
    unconfigured = client.get("/dashboard/settings?section=participants&grade=5")
    assert "No task set assigned" in unconfigured.text
    assert "Cannot start yet" in unconfigured.text
    assert "C-001" not in response.text
    assert app.extensions["research"]["state"].settings() == before


def test_stale_range_form_keeps_values_and_requires_reload_before_resubmitting(app):
    client = app.test_client()
    login(client)
    fields = ranges_form(app, client, **{"4_end": "19"})
    state = app.extensions["research"]["state"]
    current = state.settings()
    current["current_school_year"] = "2026/2027"
    state.save_settings(current, current["revision"])
    latest = state.settings()
    for _ in range(2):
        response = client.post("/dashboard/settings", data=fields)
        assert response.status_code == 400
        participant_section = response.text.split('id="participant-ids"', 1)[1]
        assert 'name="4_end" value="19"' in participant_section
        assert f'name="revision" value="{fields["revision"]}"' in participant_section
        assert "Another researcher updated the settings" in participant_section
        assert state.settings() == latest


@pytest.mark.parametrize("changes, message", [
    ({"4_end": "25"}, "overlapping participant IDs"),
    ({"4_start": "9", "4_end": "2"}, "at most 1,000 IDs"),
    ({"4_end": "invalid"}, "at most 1,000 IDs"),
    ({"4_task_set": "forged"}, "Choose an available task set"),
])
def test_invalid_ranges_keep_draft_and_do_not_save(app, changes, message):
    client = app.test_client()
    login(client)
    state = app.extensions["research"]["state"]
    before = state.settings()
    response = client.post("/dashboard/settings", data=ranges_form(app, client, **changes))
    assert response.status_code == 400 and message in response.text
    if "4_end" in changes:
        assert f'name="4_end" value="{changes["4_end"]}"' in response.text
    assert state.settings() == before


def test_prefix_padding_optional_third_grade_and_missing_only_assignment(app):
    client = app.test_client()
    login(client)
    task_set = task_catalog(app)[0]
    response = client.post("/dashboard/settings", data=ranges_form(
        app, client, **{"4_task_set": task_set["id"], "5_task_set": task_set["id"],
                        "3_enabled": "1", "3_start": 1, "3_end": 2, "3_prefix": "C-",
                        "3_width": 3, "3_task_set": task_set["id"], "3_assignment_mode": "all"}))
    assert response.status_code == 302
    settings = app.extensions["research"]["state"].settings()
    students = eligible_students(app, settings)
    assert len(students) == 42 and "C-001" in students and "C-002" in students
    assert "C-1" not in students
    assert students["10"]["1_full"] == app.config["STUDENT_TOPICS"]["10"]["1_full"]
    assert students["40"] == task_set["topics"]
    assert b"C-001" in client.get("/dashboard?grade=3").data


def test_stale_enrollment_and_unavailable_rewards_are_rejected(app, tmp_path):
    client = app.test_client()
    login(client)
    fields = ranges_form(app, client, **{"4_task_set": task_catalog(app)[0]["id"]})
    state = app.extensions["research"]["state"]
    settings = state.settings()
    state.save_settings(settings, settings["revision"])
    assert client.post("/dashboard/settings", data=fields).status_code == 400
    fields = ranges_form(app, client, **{"4_task_set": task_catalog(app)[0]["id"]})
    app.config["STUDENT_ASSET_DIR"] = str(tmp_path / "missing-rewards")
    before = state.settings()
    assert client.post("/dashboard/settings", data=fields).status_code == 400
    assert state.settings() == before


def test_run_metadata_uses_enrollment_revision_even_when_settings_change(app, tmp_path):
    state = app.extensions["research"]["state"]
    enrollment = state.settings()
    changed = state.settings()
    changed["ranges"][0].update(start=41, end=60)
    changed["ranges"][1].update(start=1, end=20)
    state.save_settings(changed, changed["revision"])
    record_run(tmp_path / "new-run", state, "1", "session", "run", ["1", "2", "3"],
               app.config["STUDENT_TOPICS"]["1"], settings=enrollment)
    metadata = json.loads((tmp_path / "new-run/1_run.run.json").read_text())
    assert metadata["grade_at_collection"] == "4"
    assert metadata["settings_revision_at_collection"] == enrollment["revision"]


@pytest.fixture
def student_app(tmp_path, monkeypatch):
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
    spec = importlib.util.spec_from_file_location("enrollment_student_app", APP_ROOT / "search_app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.app.config.update(TESTING=True, RESEARCH_PASSWORD_HASH=generate_password_hash(
        PASSWORD, method="pbkdf2:sha256:1000"), RESEARCH_PASSWORD_HASH_FILE="")
    return module


def test_saving_assignment_enables_new_student_and_snapshots_running_tasks(student_app, tmp_path):
    module = student_app
    app = module.app
    researcher = app.test_client()
    student = app.test_client()
    login(researcher)
    catalog = task_catalog(app)
    assert len(catalog) == 2
    assert 'value="21"' not in student.get("/start").text
    response = researcher.post("/dashboard/settings", data=ranges_form(
        app, researcher, **{"5_task_set": catalog[0]["id"], "5_assignment_mode": "all"}))
    assert response.status_code == 302
    assert 'value="21"' in student.get("/start").text
    assert student.post("/start", data={"user_id": "21"}).status_code == 302
    with student.session_transaction() as active:
        topic = active["task_number"]
        question = active["task_config"][f"{topic}_full"]
        first_run = active["session_id"]
    metadata = json.loads(next((tmp_path / "v2").glob("*.run.json")).read_text())
    assert metadata["participant_id"] == "21" and metadata["grade_at_collection"] == "5"
    assert metadata["tasks"][0]["question"] == question
    assert researcher.post("/dashboard/settings", data=ranges_form(
        app, researcher, **{"5_task_set": catalog[1]["id"], "5_assignment_mode": "all"})).status_code == 302
    with app.test_request_context():
        assert module.get_user_config("21") == catalog[1]["topics"]
    assert student.get("/task").status_code == 200
    with student.session_transaction() as active:
        assert active["task_config"] == catalog[0]["topics"]
    assert student.post("/start", data={"user_id": "999999"}).status_code == 400
    with student.session_transaction() as active:
        assert active["session_id"] == first_run
    assert len(list((tmp_path / "v2").glob("*.run.json"))) == 1


def test_removing_ids_blocks_new_runs_and_keeps_in_progress_run(student_app):
    app = student_app.app
    researcher, student = app.test_client(), app.test_client()
    login(researcher)
    assert student.post("/start", data={"user_id": "1"}).status_code == 302
    assert researcher.post("/dashboard/settings", data=ranges_form(
        app, researcher, **{"4_start": 2})).status_code == 302
    assert student.get("/task").status_code == 200
    fresh = app.test_client()
    assert 'value="1"' not in fresh.get("/start").text
    assert fresh.post("/start", data={"user_id": "1"}).status_code == 400
