"""Draw again the recap PDFs of one day, so that they open with the recap picture, as Salva makes them now.

The server saves a group's recap PDF when it presses "Salva l'attività". Before 22 November 2026 (#42) that PDF
had no picture page, so the PDFs of 10 November are text only. This draws them again from the answers saved in
the progress database, with the code Salva uses now. It first keeps the old PDFs in a zip file in the research
state folder, then replaces them in one transaction, each only if nobody changed it in the meantime. Test runs,
sessions whose topic has no picture and PDFs that already have one are left alone. The time of Salva stays.
It prints IDs and topics, never the children's answers.

From the application container, on the server:

    docker compose exec search_app python tools/redraw_recap_pdfs.py --date 2026-11-10          # shows, changes nothing
    docker compose exec search_app python tools/redraw_recap_pdfs.py --date 2026-11-10 --write  # backup, then replace
"""
import argparse
from contextlib import closing
from datetime import date, datetime
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from research_dashboard.permanent_test import is_test_participant  # noqa: E402

PICTURE_MARK = b"/Subtype /Image"  # The PDF with the recap picture embeds it as an image; the text-only one has none.


def saved_pdfs(db_path, day):
    """(attempt_id, participant, metadata, pdf) of every recap saved for a session on that day, test runs left out."""
    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)) as db:
        rows = db.execute("""SELECT e.attempt_id, a.participant_id, a.metadata, e.pdf FROM progress_recap_exports e
                             JOIN progress_attempts a ON a.attempt_id = e.attempt_id
                             WHERE a.is_test = 0 ORDER BY a.participant_id, e.attempt_id""").fetchall()
    found = []
    for attempt_id, participant, metadata, pdf in rows:
        metadata = json.loads(metadata)
        if (metadata.get("study_session_snapshot") or {}).get("date") == day and not is_test_participant(participant):
            found.append((attempt_id, participant, metadata, bytes(pdf)))
    return found


def plan(site, day):
    """For each saved PDF of the day: (attempt_id, participant, old PDF, new PDF or None, what happens)."""
    store = site.PROGRESS.store
    rows = []
    for attempt_id, participant, metadata, old in saved_pdfs(store.path, day):
        if PICTURE_MARK in old:
            rows.append((attempt_id, participant, old, None, "already has the picture, left alone"))
            continue
        key = site.PROGRESS.key(metadata)
        new = site.RECAP.pdf_with_picture(store.get_attempt(key, attempt_id), store.recap_columns(key, attempt_id))
        if new is None:
            rows.append((attempt_id, participant, old, None, "its topic has no picture, left alone"))
        else:
            topic = metadata.get("question_set_theme") or metadata["study_session_snapshot"].get("theme", "")
            rows.append((attempt_id, participant, old, new, f"drawn again with the picture ({topic})"))
    return rows


def replace(db_path, changes, backup_path):
    """Keep every old PDF in a new zip and check it, then replace them all in one transaction, or none."""
    with zipfile.ZipFile(backup_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for attempt_id, participant, old, _new in changes:
            archive.writestr(f"{participant}_{attempt_id}.pdf", old)
    backup_path.chmod(0o600)
    with zipfile.ZipFile(backup_path) as archive:
        if any(archive.read(f"{participant}_{attempt_id}.pdf") != old for attempt_id, participant, old, _ in changes):
            raise RuntimeError(f"The backup {backup_path} does not match; nothing was replaced.")
    with closing(sqlite3.connect(db_path, timeout=30, isolation_level=None)) as db:
        db.execute("BEGIN IMMEDIATE")
        for attempt_id, _participant, old, new in changes:
            updated = db.execute("UPDATE progress_recap_exports SET pdf = ? WHERE attempt_id = ? AND pdf = ?",
                                 (new, attempt_id, old)).rowcount
            if updated != 1:
                db.execute("ROLLBACK")
                raise RuntimeError(f"The PDF of attempt {attempt_id} changed while this ran; nothing was replaced.")
        db.execute("COMMIT")


def main(argv=None, site=None):
    parser = argparse.ArgumentParser(description="Draw again the recap PDFs of one day with the recap picture.")
    parser.add_argument("--date", required=True, help="the session's date, YYYY-MM-DD")
    parser.add_argument("--write", action="store_true", help="keep the old PDFs in a zip, then replace them")
    args = parser.parse_args(argv)
    day = date.fromisoformat(args.date).isoformat()
    if site is None:
        import search_app as site  # The app the server runs, with its own settings and databases.
    rows = plan(site, day)
    if not rows:
        print(f"No saved recap for a session on {day}.")
        return 0
    for attempt_id, participant, old, new, note in rows:
        sizes = f"{len(old) // 1024} KB" + (f" -> {len(new) // 1024} KB" if new else "")
        print(f"ID {participant:>4}  attempt {attempt_id[:8]}  {sizes:>16}  {note}")
    changes = [(attempt_id, participant, old, new) for attempt_id, participant, old, new, _ in rows if new]
    if not changes:
        print("Nothing to replace.")
        return 0
    if not args.write:
        print(f"Nothing changed. Run again with --write to replace these {len(changes)} PDF(s).")
        return 0
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = Path(site.RESEARCH_STATE.path).parent / f"recap-pdfs-before-redraw-{day}-{stamp}.zip"
    replace(site.PROGRESS.store.path, changes, backup)
    print(f"Replaced {len(changes)} PDF(s). The old ones are in {backup.name}, in the research state folder.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
