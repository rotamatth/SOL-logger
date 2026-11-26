"""The recap PDFs of a past day are drawn again with the picture; the old ones are kept and nothing else moves."""
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import zipfile
from zoneinfo import ZoneInfo

import pytest

from student_recap import render_recap_pdf
from .test_connected_first_answer import begin
from .test_editable_recap import commit, complete_today
from .test_recap_picture import LANDSCAPE, PORTRAIT, pages
from .test_study_enrollment import question_set, schedule, student_modules  # noqa: F401

TOOL_PATH = Path(__file__).resolve().parents[1] / "tools" / "redraw_recap_pdfs.py"
spec = importlib.util.spec_from_file_location("redraw_recap_pdfs", TOOL_PATH)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def today():
    return datetime.now(ZoneInfo("Europe/Zurich")).date().isoformat()


def saved_run(module, uid="1"):
    client = begin(module, uid)
    auth = complete_today(client)
    assert commit(client, auth, "finish").status_code == 200
    return auth["attempt_id"]


def exports(module):
    with sqlite3.connect(module.PROGRESS.store.path) as db:
        return {row[0]: (row[1], bytes(row[2])) for row in db.execute(
            "SELECT attempt_id, finished_at, pdf FROM progress_recap_exports")}


def make_text_only(module, attempt_id):
    """As on 10 November: the PDF saved at Salva had no picture page."""
    store = module.PROGRESS.store
    with sqlite3.connect(store.path) as db:
        metadata = db.execute("SELECT metadata FROM progress_attempts WHERE attempt_id=?", (attempt_id,)).fetchone()[0]
    key = module.PROGRESS.key(json.loads(metadata))
    old = render_recap_pdf(store.recap_columns(key, attempt_id))
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE progress_recap_exports SET pdf=? WHERE attempt_id=?", (old, attempt_id))
    return old


@pytest.fixture
def old_day(student_modules):
    module = student_modules()
    schedule(module, {**question_set(), "theme": "spazio"})
    attempt_id = saved_run(module)
    old = make_text_only(module, attempt_id)
    assert tool.PICTURE_MARK not in old
    return module, attempt_id, old


def backups(module):
    return sorted(Path(module.RESEARCH_STATE.path).parent.glob("recap-pdfs-before-redraw-*.zip"))


def test_without_write_it_only_shows_what_it_would_do(old_day, capsys):
    module, attempt_id, old = old_day
    before = exports(module)
    assert tool.main(["--date", today()], site=module) == 0
    out = capsys.readouterr().out
    assert "ID    1" in out and "drawn again with the picture (spazio)" in out and "--write" in out
    assert exports(module) == before and backups(module) == []


def test_with_write_the_pdf_opens_with_the_picture_and_the_old_one_is_kept(old_day, capsys):
    module, attempt_id, old = old_day
    finished_at = exports(module)[attempt_id][0]
    assert tool.main(["--date", today(), "--write"], site=module) == 0
    saved_at, new = exports(module)[attempt_id]
    assert saved_at == finished_at, "the time of Salva stays"
    # As Salva makes it now: the landscape picture page, then the text pages with every answer in full.
    assert tool.PICTURE_MARK in new and re.search(LANDSCAPE, new) and re.search(PORTRAIT, new)
    assert pages(new) == pages(old) + 1
    [backup] = backups(module)
    assert oct(backup.stat().st_mode & 0o777) == "0o600"
    with zipfile.ZipFile(backup) as archive:
        assert archive.namelist() == [f"1_{attempt_id}.pdf"] and archive.read(f"1_{attempt_id}.pdf") == old
    assert "Replaced 1 PDF(s)" in capsys.readouterr().out


def test_a_second_run_leaves_the_redrawn_pdf_alone(old_day, capsys):
    module, attempt_id, _ = old_day
    tool.main(["--date", today(), "--write"], site=module)
    redrawn = exports(module)[attempt_id]
    capsys.readouterr()
    assert tool.main(["--date", today(), "--write"], site=module) == 0
    assert "already has the picture" in capsys.readouterr().out
    assert exports(module)[attempt_id] == redrawn and len(backups(module)) == 1


def test_another_day_is_not_touched(old_day, capsys):
    module, _, _ = old_day
    before = exports(module)
    assert tool.main(["--date", "2026-11-10", "--write"], site=module) == 0
    assert "No saved recap for a session on 2026-11-10." in capsys.readouterr().out
    assert exports(module) == before


def test_a_pdf_changed_meanwhile_stops_everything(old_day):
    module, attempt_id, _ = old_day
    changes = [(a, p, old, new) for a, p, old, new, _ in tool.plan(module, today()) if new]
    with sqlite3.connect(module.PROGRESS.store.path) as db:
        db.execute("UPDATE progress_recap_exports SET pdf=? WHERE attempt_id=?", (b"%PDF- changed", attempt_id))
    with pytest.raises(RuntimeError, match="nothing was replaced"):
        tool.replace(module.PROGRESS.store.path, changes, Path(module.RESEARCH_STATE.path).parent / "backup.zip")
    assert exports(module)[attempt_id][1] == b"%PDF- changed"


def test_test_runs_are_left_out(student_modules):
    module = student_modules()
    schedule(module, {**question_set(), "theme": "spazio"})
    saved_run(module, "TEST-spazio")
    assert tool.saved_pdfs(module.PROGRESS.store.path, today()) == []


def test_a_topic_without_a_picture_is_left_alone(student_modules, capsys):
    module = student_modules()
    schedule(module)  # "Today theme" is no topic the app knows, so there is no recap picture.
    attempt_id = saved_run(module)
    before = exports(module)
    assert tool.main(["--date", today(), "--write"], site=module) == 0
    out = capsys.readouterr().out
    assert "its topic has no picture, left alone" in out and "Nothing to replace." in out
    assert exports(module) == before and attempt_id in before
