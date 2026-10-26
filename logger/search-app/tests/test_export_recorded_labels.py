"""Consumers must read each run's recorded labels when a session ID is reused."""
from copy import deepcopy
import json

from .test_research_dashboard import app, archive, configure, login, write_run


def test_export_retains_distinct_recorded_labels_and_deduplicates_session_catalog(app):
    settings = configure(app)
    snapshots = {}
    originals = {}
    for uid, suffix, name in (("1", "first", "Visit label collected first"),
                              ("2", "second", "Visit label collected later")):
        key, root, stem = write_run(app, uid=uid, suffix=suffix)
        snapshot = deepcopy(settings["sessions"][0])
        snapshot.update(name=name, theme="Recorded theme " + suffix)
        path = root / f"{stem}.run.json"
        metadata = json.loads(path.read_text())
        metadata.update(study_session_at_collection=snapshot["id"], study_session_snapshot=snapshot)
        path.write_text(json.dumps(metadata))
        snapshots[key] = snapshot
        originals[path] = path.read_bytes()
    client = app.test_client()
    login(client)
    output, manifest = archive(client.get("/dashboard/exports/grade_session?grade=4&session=grade-4-session-1"))
    assert len(manifest["runs"]) == 2
    assert len(manifest["available_sessions"]) == 1
    assert manifest["available_sessions"][0]["id"] == "grade-4-session-1"
    for run in manifest["runs"]:
        expected = snapshots[run["run_id"]]
        assert run["study_session"] == expected
        assert json.loads(output.read(run["metadata_path"]))["study_session"] == expected
    assert len({run["study_session"]["name"] for run in manifest["runs"]}) == 2
    assert all(path.read_bytes() == content for path, content in originals.items())
