"""Derived export metadata contains collected context, not today's question editor."""
import json

import pytest

from .test_research_dashboard import add_history_rule, app, archive, configure, login, write_run
from .test_study_enrollment import question_set


@pytest.mark.parametrize("collection", ["v2", "legacy"])
@pytest.mark.parametrize("scope", ["run", "task"])
def test_historical_exports_exclude_current_questions_and_other_participant_drafts(app, collection, scope):
    settings = configure(app)
    state = app.extensions["research"]["state"]
    current = settings["sessions"][0]
    current.update(question_set=question_set("CURRENT_SHARED_SETUP"),
                   participant_questions={"2": question_set("OTHER_PARTICIPANT_ASSIGNMENT")},
                   participant_question_drafts={"2": question_set("PRIVATE_FUTURE_DRAFT", approved=False)})
    state.save_settings(settings, settings["revision"])
    if collection == "legacy":
        add_history_rule(state, grade="4", school_year="2026/2027",
                         date_from="2026-09-01", date_to="2027-08-31")
    key, root, _ = write_run(app, collection=collection, metadata=collection == "v2")
    originals = {path.name: path.read_bytes() for path in root.iterdir()}
    client = app.test_client()
    login(client)
    response = client.get(f"/dashboard/exports/{scope}?collection={collection}&run={key}&task=1")
    output, manifest = archive(response)
    contents = b"".join(output.read(name) for name in output.namelist())
    assert b"CURRENT_SHARED_SETUP" not in contents
    assert b"OTHER_PARTICIPANT_ASSIGNMENT" not in contents
    assert b"PRIVATE_FUTURE_DRAFT" not in contents
    assert manifest["runs"][0]["study_session"]["id"] == current["id"]
    assert manifest["available_sessions"][0]["date"] == "2026-10-01"
    if scope == "task":
        assert b"Recorded question 2" not in contents and b"Recorded question 3" not in contents
    for source in manifest["files"]:
        assert source["included"]
        assert output.read(source["archive_name"]) == originals[source["source_name"]]
    assert all(path.read_bytes() == originals[path.name] for path in root.iterdir())


@pytest.mark.parametrize("scope", ["run", "task"])
def test_export_keeps_recorded_session_labels_when_current_setup_changes(app, scope):
    settings = configure(app)
    key, root, stem = write_run(app)
    snapshot = {**settings["sessions"][0], "name": "Original collected visit", "theme": "Climate"}
    sidecar = root / f"{stem}.run.json"
    metadata = json.loads(sidecar.read_text())
    metadata.update(study_session_at_collection=snapshot["id"], study_session_snapshot=snapshot)
    sidecar.write_text(json.dumps(metadata))
    original = sidecar.read_bytes()
    settings["sessions"][0].update(name="Replacement visit", date="2026-10-04",
                                    question_set=question_set("UNRELATED_NEW_QUESTIONS"))
    state = app.extensions["research"]["state"]
    state.save_settings(settings, settings["revision"])
    client = app.test_client()
    login(client)
    output, manifest = archive(client.get(f"/dashboard/exports/{scope}?run={key}&task=1"))
    assert manifest["runs"][0]["study_session"] == snapshot
    assert manifest["available_sessions"] == [snapshot]
    contents = b"".join(output.read(name) for name in output.namelist())
    assert b"Replacement visit" not in contents and b"UNRELATED_NEW_QUESTIONS" not in contents
    assert sidecar.read_bytes() == original
