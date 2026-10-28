"""Malformed synthetic collection data remains inspectable in the dashboard."""
import json

import pytest

from .test_dashboard_filters import rendered_context
from .test_research_dashboard import app, configure, identity, login, write_run


@pytest.mark.parametrize("started_at", [{"unexpected": "object"}, ["unexpected"], 42, True])
def test_invalid_recorded_start_time_keeps_same_day_participant_history_available(app, started_at):
    configure(app)
    malformed, root, stem = write_run(app, suffix="malformed")
    valid, _, _ = write_run(app, suffix="valid")
    sidecar = root / f"{stem}.run.json"
    metadata = json.loads(sidecar.read_text())
    metadata["started_at"] = started_at
    sidecar.write_text(json.dumps(metadata))
    original = sidecar.read_bytes()

    client = app.test_client()
    login(client)
    response = client.get(f"/dashboard/participants/study/{identity('1')}")
    assert response.status_code == 200

    state, index = (app.extensions["research"][name] for name in ("state", "index"))
    summaries = {run["id"]: run for run in index.summaries(state.settings())}
    assert {malformed, valid} <= summaries.keys()
    assert summaries[malformed]["started_at"] is None
    assert summaries[malformed]["date"] == "2026-10-01"
    assert "invalid_recorded_started_at" in summaries[malformed]["issues"]
    run = index.run(malformed, state.settings())
    assert run["started_at"] is None
    assert run["metadata"]["started_at"] == started_at
    assert sidecar.read_bytes() == original


def test_cached_invalid_start_time_is_validated_without_reindexing(app):
    configure(app)
    key, _, _ = write_run(app)
    state, index = (app.extensions["research"][name] for name in ("state", "index"))
    index.refresh()
    with index.connect() as db:
        row = db.execute("SELECT summary, detail FROM runs WHERE id = ?", (key,)).fetchone()
        summary, detail = (json.loads(row[name]) for name in ("summary", "detail"))
        summary["started_at"] = detail["started_at"] = {"cached": "invalid"}
        db.execute("UPDATE runs SET summary = ?, detail = ? WHERE id = ?",
                   (json.dumps(summary), json.dumps(detail), key))
    assert index.summaries(state.settings())[0]["started_at"] is None
    assert index.run(key, state.settings())["started_at"] is None


def test_legacy_nondecimal_digit_identity_does_not_break_participant_listing(app):
    for uid in ("10", "2", "1", "P2", "²"):
        write_run(app, collection="legacy", uid=uid, metadata=False)
    client = app.test_client()
    login(client)
    with rendered_context(app) as contexts:
        response = client.get("/dashboard?collection=legacy&grade=legacy")
    assert response.status_code == 200
    assert [person["id"] for person in contexts[-1]["people"]] == ["1", "2", "10", "P2", "²"]
    assert client.get(f"/dashboard/participants/legacy/{identity('²')}").status_code == 200
