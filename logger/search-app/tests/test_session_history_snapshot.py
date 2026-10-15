"""Collection-time session assignments survive later calendar edits."""
from copy import deepcopy
from pathlib import Path
import json
import sys

import pytest
from flask import template_rendered

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from research_dashboard import display_session
from research_dashboard.index import Index
from research_dashboard.state import DEFAULT_STUDY_ID, default_settings
from .test_research_dashboard import app, configure, login, write_run as write_dashboard_run


@pytest.fixture
def history_index(tmp_path):
    roots = {kind: tmp_path / kind for kind in ("v2", "legacy")}
    for root in roots.values():
        root.mkdir()
    directory = tmp_path / "index"
    directory.mkdir()
    settings = default_settings()
    settings["revision"] = 1
    settings["sessions"][0].update(date="2026-10-01", name="First visit", theme="Climate")
    return Index(directory, roots), roots, settings


def write_run(roots, metadata=None, collection="v2"):
    root = roots[collection]
    events = [{"uid": "1", "sessionID": "technical-1", "task_number": 1,
               "type": "TaskStarted", "timestamp": "2026-10-01T09:00:00+02:00"}]
    (root / "historical_FULL.log").write_text("".join(json.dumps(event) + "\n" for event in events))
    if metadata is not None:
        value = {"schema_version": 1, "participant_id": "1", "technical_session_id": "technical-1",
                 "started_at": "2026-10-01T09:00:00+02:00", "grade_at_collection": "4",
                 "school_year_at_collection": "2026/2027", "tasks": [], **metadata}
        (root / "historical.run.json").write_text(json.dumps(value))


def redate_first_visit(settings):
    updated = deepcopy(settings)
    updated["revision"] += 1
    updated["current_school_year"] = "2027/2028"
    updated["sessions"][0].update(date="2026-10-02", name="Renamed visit", theme="Technology")
    updated["sessions"][1]["date"] = "2026-10-01"
    return updated


def test_session_snapshot_survives_calendar_edits_and_index_rebuild(history_index):
    index, roots, settings = history_index
    snapshot = deepcopy(settings["sessions"][0])
    write_run(roots, {"study_id_at_collection": DEFAULT_STUDY_ID,
                      "study_session_at_collection": snapshot["id"], "study_session_snapshot": snapshot})
    originals = {path: path.read_bytes() for path in roots["v2"].iterdir()}
    index.refresh(force=True)
    before = index.summaries(settings)[0]
    assert before["study_session"] == snapshot

    updated = redate_first_visit(settings)
    index.refresh(force=True)
    after = index.summaries(updated)[0]
    detail = index.run(after["id"], updated)
    assert after["study_session"] == detail["study_session"] == snapshot
    assert after["study_session"]["id"] != updated["sessions"][1]["id"]
    assert after["grade"] == "4" and after["grade_source"] == "recorded"
    assert after["school_year"] == "2026/2027" and after["school_year_source"] == "recorded"
    assert detail["metadata"]["study_session_snapshot"] == snapshot
    assert {path: path.read_bytes() for path in originals} == originals


def test_explicitly_unassigned_run_stays_unassigned_when_calendar_gains_date(history_index):
    index, roots, settings = history_index
    settings["sessions"][0]["date"] = ""
    write_run(roots, {"study_session_at_collection": None, "study_session_snapshot": None})
    index.refresh(force=True)
    assert index.summaries(settings)[0]["study_session"] is None

    settings["sessions"][0]["date"] = "2026-10-01"
    settings["revision"] += 1
    index.refresh(force=True)
    summary = index.summaries(settings)[0]
    assert "study_session_at_collection" in summary
    assert summary["study_session"] is None
    assert index.run(summary["id"], settings)["study_session"] is None


def test_older_sidecar_session_id_survives_redating_without_snapshot(history_index):
    index, roots, settings = history_index
    session_id = settings["sessions"][0]["id"]
    write_run(roots, {"study_session_at_collection": session_id})
    index.refresh(force=True)
    updated = redate_first_visit(settings)
    assert index.summaries(updated)[0]["study_session"]["id"] == session_id


@pytest.mark.parametrize("collection", ["v2", "legacy"])
def test_runs_without_recorded_session_keep_date_classification(history_index, collection):
    index, roots, settings = history_index
    if collection == "legacy":
        settings["historical_grades"] = [{"id": "a" * 24, "collection": "legacy", "grade": "4",
                                          "start": 1, "end": 1, "prefix": "", "width": 0,
                                          "date_from": "2026-10-01", "date_to": "2026-10-01",
                                          "school_year": "2026/2027"}]
    write_run(roots, {} if collection == "v2" else None, collection)
    index.refresh(force=True)
    assert index.summaries(settings)[0]["study_session"]["id"] == settings["sessions"][0]["id"]
    updated = redate_first_visit(settings)
    assert index.summaries(updated)[0]["study_session"]["id"] == settings["sessions"][1]["id"]


def test_foreign_study_does_not_inherit_current_study_session_snapshot(history_index):
    index, roots, settings = history_index
    write_run(roots, {"study_id_at_collection": "another-study",
                      "study_session_at_collection": settings["sessions"][0]["id"],
                      "study_session_snapshot": settings["sessions"][0]})
    index.refresh(force=True)
    assert index.summaries(settings)[0]["study_session"] is None


def test_invalid_snapshot_falls_back_to_recorded_id_and_reports_problem(history_index):
    index, roots, settings = history_index
    write_run(roots, {"study_session_at_collection": settings["sessions"][0]["id"],
                      "study_session_snapshot": {**settings["sessions"][0], "number": "1"}})
    index.refresh(force=True)
    run = index.summaries(redate_first_visit(settings))[0]
    assert run["study_session"]["id"] == settings["sessions"][0]["id"]
    assert run["issues"] == ["invalid_recorded_study_session_snapshot"]
    assert run["issue_count"] == 1


def write_dashboard_snapshot(app, snapshot, suffix="old", school_year="2026/2027"):
    key, root, stem = write_dashboard_run(app, date=snapshot["date"], suffix=suffix)
    sidecar = root / f"{stem}.run.json"
    metadata = json.loads(sidecar.read_text())
    metadata.update(study_session_at_collection=snapshot["id"], study_session_snapshot=snapshot,
                    school_year_at_collection=school_year)
    sidecar.write_text(json.dumps(metadata))
    return key


def rendered_context(app, client, path):
    captured = []

    def capture(sender, template, context, **extra):
        captured.append(context)

    with template_rendered.connected_to(capture, app):
        response = client.get(path)
    assert response.status_code == 200
    return response, captured[-1]


def test_historical_session_labels_survive_edits_in_overview_and_participant_history(app):
    settings = configure(app)
    snapshot = {**settings["sessions"][0], "name": "Original visit", "theme": "Climate"}
    key = write_dashboard_snapshot(app, snapshot)
    settings["sessions"][0].update(name="Replacement visit", date="2026-10-04")
    state = app.extensions["research"]["state"]
    state.save_settings(settings, settings["revision"])
    client = app.test_client()
    login(client)
    overview, context = rendered_context(app, client, "/dashboard?grade=4&session=grade-4-session-1")
    assert context["selected_session"] == snapshot
    card = next(card for card in context["session_cards"] if card["session"]["id"] == snapshot["id"])
    assert card["session"] == snapshot and [run["id"] for run in card["runs"]] == [key]
    assert "Original visit" in overview.text and "Replacement visit" not in overview.text
    token = context["people"][0]["token"]
    participant, context = rendered_context(app, client, f"/dashboard/participants/v2/{token}?view=logs")
    group = context["display_groups"][0]
    assert group["session"] == snapshot and group["runs"][0]["study_session"] == snapshot
    assert "Original visit" in participant.text and "2026-10-01" in participant.text
    assert "Replacement visit" not in participant.text and "2026-10-04" not in participant.text


def test_mixed_attempt_labels_show_neutral_group_and_preserve_each_recorded_label(app):
    settings = configure(app)
    first = {**settings["sessions"][0], "name": "First visit", "theme": "Climate"}
    second = {**first, "name": "Repeated visit", "date": "2026-10-04", "theme": "Water"}
    write_dashboard_snapshot(app, first, "first", "2026/2027")
    write_dashboard_snapshot(app, second, "second", "2027/2028")
    settings["sessions"][0].update(name="Current setup", date="2026-10-05")
    state = app.extensions["research"]["state"]
    state.save_settings(settings, settings["revision"])
    client = app.test_client()
    login(client)
    _, overview = rendered_context(app, client, "/dashboard?grade=4&session=grade-4-session-1")
    assert overview["selected_session"]["name"] == overview["selected_session"]["date"] == ""
    token = overview["people"][0]["token"]
    response, context = rendered_context(app, client, f"/dashboard/participants/v2/{token}?view=logs")
    assert context["display_groups"][0]["session"]["name"] == ""
    assert "First visit" in response.text and "Repeated visit" in response.text
    assert "2026-10-01" in response.text and "2026-10-04" in response.text
    assert "Current setup" not in response.text
    _, scoped_overview = rendered_context(
        app, client, "/dashboard?grade=4&session=grade-4-session-1&school_year=2026/2027")
    assert scoped_overview["selected_session"] == first
    _, scoped_person = rendered_context(
        app, client, f"/dashboard/participants/v2/{token}?view=logs&school_year=2027/2028")
    assert scoped_person["display_groups"][0]["session"] == second


def test_session_display_labels_exclude_question_assignments():
    configured = {"id": "grade-4-session-1", "grade": "4", "number": 1, "name": "Scheduled visit",
                  "date": "2026-10-15", "question_set": {"questions": ["Future question"]},
                  "participant_questions": {"1": {"questions": ["Individual question"]}}}
    label = display_session(configured, [])
    assert set(label) == {"id", "grade", "number", "name", "date", "theme"}
    assert label["name"] == configured["name"]
    assert "Future question" not in json.dumps(label) and "Individual question" not in json.dumps(label)
