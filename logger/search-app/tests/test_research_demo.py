"""Synthetic demo fixtures exercise the real index without using study logs."""
from datetime import date
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_dashboard.index import Index
from research_dashboard.state import State
from tools.seed_research_demo import demo_files, seed


def test_demo_runs_index_as_completed_incomplete_and_repeated_without_changing_settings(tmp_path):
    state = State(tmp_path / "state")
    settings = state.settings()
    settings["ranges"][1].update(start=35, end=40, prefix="P-", width=3)
    settings["sessions"][0]["date"] = "2026-05-25"
    state.save_settings(settings, settings["revision"])
    saved = state.settings()
    report, created = seed(tmp_path / "logs", saved, date(2026, 10, 5))
    assert created and state.settings() == saved
    assert set(report["participants"]) == {str(n) for n in range(1, 7)} | {f"P-{n:03}" for n in range(35, 41)}
    assert len(report["runs"]) == 14
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    index = Index(tmp_path / "state", {"v2": tmp_path / "logs", "legacy": legacy})
    index.refresh(force=True)
    runs = index.summaries(saved)
    assert len(runs) == 14
    assert sum(r["status"] == "completed" for r in runs) == 6
    assert sum(r["status"] == "incomplete" for r in runs) == 8
    assert sum(r["participant_id"] == "1" for r in runs) == 2
    assert {r["study_session"]["id"] for r in runs if r["grade"] == "4"} == {"grade-4-session-1"}
    assert {r["school_year"] for r in runs} == {"2025/2026", "2026/2027"}
    assert all(r["log_file_count"] > 0 for r in runs)
    assert all(not r["issues"] for r in runs)
    empty = next(r for r in runs if r["participant_id"] == "5")
    detail = index.run(empty["id"], saved)
    assert detail["tasks"]["2"]["answers"][0]["value"] == ""
    assert detail["status"] == "completed"


def test_seed_is_repeatable_and_preserves_other_files(tmp_path):
    settings = State(tmp_path / "state").settings()
    logs = tmp_path / "logs"
    logs.mkdir()
    real = logs / "existing_FULL.log"
    real.write_text("existing local test data\n")
    first, created = seed(logs, settings, date(2026, 10, 5))
    before = {p.name: p.read_bytes() for p in logs.iterdir()}
    second, created_again = seed(logs, settings, date(2026, 10, 6))
    assert created and not created_again and first == second
    assert {p.name: p.read_bytes() for p in logs.iterdir()} == before


def test_seed_rejects_filename_collisions_without_overwriting(tmp_path):
    settings = State(tmp_path / "state").settings()
    files, _ = demo_files(settings, date(2026, 10, 5))
    logs = tmp_path / "logs"
    logs.mkdir()
    existing = logs / next(iter(files))
    existing.write_text("keep this file")
    with pytest.raises(ValueError, match="already exists"):
        seed(logs, settings, date(2026, 10, 5))
    assert list(logs.iterdir()) == [existing]
    assert existing.read_text() == "keep this file"
