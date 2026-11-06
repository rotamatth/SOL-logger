"""Prepare a fresh dashboard for the session of 10 November 2026, in one step.

Run once after the deployment, from the application container:

    docker compose exec search_app python tools/setup_session_2026_11_10.py --dry-run
    docker compose exec search_app python tools/setup_session_2026_11_10.py

It creates this year's two sessions, enrolls the children under the IDs they already had
in May, removes the IDs a fresh install pre-fills, and tells the dashboard which class each
child was in during May. May's log files are only read, never changed. Anything other than
a fresh dashboard is refused and left untouched, so it cannot overwrite real data.
"""
import argparse
from copy import deepcopy
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_dashboard import participants as identities  # noqa: E402
from research_dashboard.state import SETTING_FIELDS, State  # noqa: E402
from research_dashboard.study_config import _content_id, question_set_problem, session_readiness  # noqa: E402

SCHOOL_YEAR = "2026/2027"
MAY_SCHOOL_YEAR = "2025/2026"
SESSION_DATE = "2026-11-10"
LINK_NOTE = "May 2026 experiment, same ID"

# Same children, same IDs: this year's 4th class was the 3rd in May, this year's 5th was the 4th.
GROUP_A = [(1, 8), (17, 18)]
GROUP_B = [(9, 16), (19, 20)]

# Three questions in the order of their animations: position chooses the clip and poster.
SPAZIO_QUESTIONS = (
    ("Sistema solare Giove", "Come si chiamano i satelliti maggiori di Giove?"),
    ("Primo animale nello spazio", "Qual è stato il primo animale nello spazio e come si chiamava?"),
    ("Altre galassie", "Quali sono i nomi di altre 3 galassie oltre la nostra?"),
)
ORECCHIO_QUESTIONS = ()  # Diletta enters them in the dashboard. Until then class 5 is a draft that needs them.

# The experiment of 19 May 2026: class 4 started at 10:41 with IDs 9-16, class 3 at 14:47 with IDs 1-8, 17, 18,
# and all 18 finished. IDs 19 and 20 have no May run. Runs on other days were tests and stay out of the classes.
MAY_DAY = "2026-05-19"
MAY_PERIODS = {"3": ((MAY_DAY, MAY_DAY),), "4": ((MAY_DAY, MAY_DAY),)}
MAY_CLASSES = {"3": [(1, 8), (17, 18)], "4": [(9, 16)]}


class NotFresh(RuntimeError):
    """The dashboard already holds something this step must not overwrite."""


def ids_of(ranges):
    return [str(number) for start, end in ranges for number in range(start, end + 1)]


def question_set(theme, rows):
    if not rows:
        return {"theme": theme, "questions": [], "approved": False}
    return {"theme": theme, "approved": True,
            "questions": [{"id": _content_id({"topic": topic, "question": question}), "topic": topic, "question": question}
                          for topic, question in rows]}


def study_session(grade, name, questions):
    return {"id": f"grade-{grade}-session-1", "grade": grade, "number": 1, "date": SESSION_DATE,
            "name": name, "school_year": SCHOOL_YEAR, "question_set": questions}


def historical_rules():
    rules = []
    for grade, ranges in MAY_CLASSES.items():
        for date_from, date_to in MAY_PERIODS[grade]:
            rules.extend({"id": secrets.token_hex(12), "grade": grade, "collection": "legacy",
                          "school_year": MAY_SCHOOL_YEAR, "date_from": date_from, "date_to": date_to,
                          "start": start, "end": end, "prefix": "", "width": 0} for start, end in ranges)
    return rules


def fresh_problem(state, log_dir):
    settings = state.settings()
    if settings["current_school_year"]:
        return "a school year is already set"
    if any(item.get(key) for item in settings["sessions"] for key in ("date", "name", "question_set", "removed")):
        return "a session has already been prepared"
    with state.connect() as db:
        attempts = [row[0] for row in db.execute("SELECT metadata FROM study_attempts")]
        links = db.execute("SELECT COUNT(*) FROM participant_links").fetchone()[0]
    if any('"is_test": true' not in attempt for attempt in attempts):
        return "a child has already started a run"
    if links:
        return "historical records are already linked"
    if any(path.name.endswith((".log", ".run.json")) for path in Path(log_dir).iterdir()):
        return "the log folder already holds runs"
    return None


def apply(state, log_dir, spazio=SPAZIO_QUESTIONS, orecchio=ORECCHIO_QUESTIONS):
    """Every step goes through the dashboard's own validated writes."""
    problem = fresh_problem(state, log_dir)
    if problem:
        raise NotFresh(problem)
    current = state.settings()
    updated = deepcopy({key: current[key] for key in SETTING_FIELDS})
    updated.update(
        current_school_year=SCHOOL_YEAR,
        # Whole ranges only; 17 to 20 are added next, since each class has two runs of IDs.
        ranges=[{"grade": "4", "start": 1, "end": 8, "prefix": "", "width": 0},
                {"grade": "5", "start": 9, "end": 16, "prefix": "", "width": 0}],
        sessions=[study_session("4", "4a spazio", question_set("spazio", spazio)),
                  study_session("5", "5a orecchio", question_set("orecchio", orecchio))],
        historical_grades=historical_rules())
    state.save_settings(updated, current["revision"])

    def change(operation, **arguments):
        state.change_participants(operation, arguments, state.settings()["revision"])

    for uid, grade in (("17", "4"), ("18", "4"), ("19", "5"), ("20", "5")):
        change("update", uid=uid, year=SCHOOL_YEAR, grade=grade, active=True)
    with state.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        unused = [str(number) for number in range(21, 41)]
        if db.execute(f"SELECT 1 FROM enrollments WHERE participant_id IN ({','.join('?' * len(unused))}) LIMIT 1",
                      unused).fetchone():
            raise NotFresh("a pre-filled ID has an enrollment")
        db.executemany("DELETE FROM participants WHERE id=?", [(uid,) for uid in unused])
        revision = db.execute("SELECT MAX(revision) FROM settings").fetchone()[0]
        identities.audit(db, revision, "setup_removed_unused_ids", {"ids": unused})
    for grade, ranges in MAY_CLASSES.items():
        change("enroll", ids=ids_of(ranges), year=MAY_SCHOOL_YEAR, grade=grade)
        for uid in ids_of(ranges):
            for date_from, date_to in MAY_PERIODS[grade]:
                change("link", source_id=uid, uid=uid, date_from=date_from, date_to=date_to, note=LINK_NOTE)


def report(state):
    settings = state.settings()
    for item in settings["sessions"]:
        readiness = session_readiness(settings, item)
        problem = question_set_problem(item.get("question_set"))
        ids = ", ".join(person["id"] for person in readiness["participants"])
        print(f"{item['name']}: {item['date']}, Session {item['number']}, IDs {ids}")
        print(f"  theme {item['question_set']['theme']}, "
              + ("questions approved" if not problem else "STILL NEEDS ITS QUESTIONS: add them in the dashboard"))
    for year, members in sorted(settings["enrollments"].items()):
        classes = {}
        for uid, member in members.items():
            classes.setdefault(member["grade"], []).append(uid)
        print(year + ": " + "; ".join(f"class {grade}: {len(ids)} children" for grade, ids in sorted(classes.items())))
    print(f"Classes classified for May: {len(settings['historical_grades'])} rules, "
          f"{len(settings['participant_links'])} children linked to their May records.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state", default=os.getenv("RESEARCH_STATE_DIR", "research_state"))
    parser.add_argument("--logs", default=os.getenv("SOL_LOG_DIR", "logs_v2"))
    parser.add_argument("--dry-run", action="store_true", help="Apply to a temporary copy and show the result")
    args = parser.parse_args()
    if args.dry_run:
        with tempfile.TemporaryDirectory() as copy:
            source = Path(args.state) / "research.sqlite3"
            if source.exists():
                shutil.copy2(source, Path(copy) / "research.sqlite3")
            state = State(copy)
            return run(state, args.logs, "Dry run, nothing was saved. It would give:")
    return run(State(args.state), args.logs, "Saved:")


def run(state, log_dir, heading):
    try:
        apply(state, log_dir)
    except NotFresh as error:
        print(f"Nothing changed: {error}.")
        return 1
    print(heading)
    report(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
