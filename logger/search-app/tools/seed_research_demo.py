"""Add clearly marked synthetic logs to the isolated local SOL UI preview."""
import argparse
from datetime import date, datetime, time, timedelta
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

APP_ROOT = Path(__file__).resolve().parents[1] if __file__ != "<stdin>" else Path.cwd()
sys.path.insert(0, str(APP_ROOT))

from research_dashboard.state import DEFAULT_STUDY_ID, GRADES, State, roster

DATASET = "sol-ui-demo-v1"
MANIFEST = ".sol-ui-demo.json"
TOPICS = (
    ("3", "DEMO — Perché la Luna sembra cambiare forma?", "fasi della luna",
     "DEMO — Vediamo parti diverse del lato illuminato della Luna."),
    ("1", "DEMO — Come fanno le api a produrre il miele?", "api miele",
     "DEMO — Le api raccolgono il nettare e lo trasformano nel miele."),
    ("2", "DEMO — A che cosa servono le radici di una pianta?", "radici piante",
     "DEMO — Le radici assorbono acqua e tengono la pianta nel terreno."),
)
SCENARIOS = (
    ("completed", 3, True), ("completed-without-final-save", 3, False),
    ("one-answer", 1, False), ("two-answers", 2, False),
    ("empty-answer", 3, True), ("started-only", 0, False),
)


def demo_files(settings, today):
    """Use the saved roster and dated sessions; never alter study settings."""
    files, runs = {}, []
    for grade in GRADES:
        ids = [uid for uid, value in roster(settings).items() if value == grade][:6]
        session = next((s for s in settings["sessions"] if s["grade"] == grade and s["number"] == 1), None)
        study_date = date.fromisoformat(session["date"]) if session and session["date"] else today
        year_start = study_date.year if study_date.month >= 8 else study_date.year - 1
        school_year = settings.get("current_school_year") or f"{year_start}/{year_start + 1}"
        examples = [(uid, *SCENARIOS[n], n) for n, uid in enumerate(ids)]
        if ids:
            examples.append((ids[0], "repeat", 1, False, 6))
        for uid, scenario, answers, finish, slot in examples:
            safe_uid = re.sub(r"[^A-Za-z0-9._-]", "_", uid)[:64]
            stem = f"{safe_uid}_{DATASET}_{scenario}"
            started = datetime.combine(study_date, time(9), ZoneInfo("Europe/Zurich")) + timedelta(minutes=slot * 15)
            session_id = f"{DATASET}-grade-{grade}-{uid}-{scenario}"
            order = [topic[0] for topic in TOPICS]
            metadata = {
                "schema_version": 1, "collection": "v2", "synthetic_fixture": DATASET,
                "study_id_at_collection": DEFAULT_STUDY_ID, "participant_id": uid,
                "technical_session_id": session_id, "log_id": f"{DATASET}-{scenario}",
                "started_at": started.isoformat(), "experiment_date": study_date.isoformat(),
                "timezone": "Europe/Zurich", "grade_at_collection": grade,
                "school_year_at_collection": school_year,
                "settings_revision_at_collection": settings["revision"],
                "app_version": DATASET, "git_commit": "synthetic-test-data", "task_order": order,
                "tasks": [{"presented_number": n, "topic_id": topic, "question": question}
                          for n, (topic, question, _, _) in enumerate(TOPICS, 1)],
            }
            files[f"{stem}.run.json"] = (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode()
            full = []
            for number, (topic, question, query, answer) in enumerate(TOPICS[:min(answers + 1, 3)], 1):
                task_start = started + timedelta(minutes=(number - 1) * 3)
                common = {"uid": uid, "sessionID": session_id, "task_number": number,
                          "actual_topic_number": topic, "task_order": order,
                          "task_question": question, "synthetic_fixture": DATASET}
                events = []
                for seconds, kind, extra in (
                    (0, "TaskStarted", {}),
                    (12, "querySubmitted", {"query": query, "queryID": f"demo-query-{number}"}),
                    (13, "searchResultGenerated", {"query": query, "result_count": 3}),
                    (25, "clickedResult", {"query": query, "url": "https://example.invalid/demo", "rank": 1}),
                ):
                    events.append({**common, "type": kind,
                                   "timestamp": (task_start + timedelta(seconds=seconds)).isoformat(), **extra})
                if number <= answers:
                    events.append({**common, "type": "TaskEnded",
                                   "timestamp": (task_start + timedelta(minutes=2)).isoformat(),
                                   "answer": "" if scenario == "empty-answer" and number == 2 else answer})
                if finish and number == 3:
                    events.append({**common, "type": "experimentFinished",
                                   "timestamp": (task_start + timedelta(minutes=2, seconds=10)).isoformat()})
                full.extend(events)
                files[f"{stem}_task{number}_topic{topic}.log"] = json_lines(events)
            files[f"{stem}_FULL.log"] = json_lines(full)
            runs.append({"participant_id": uid, "grade": grade, "scenario": scenario,
                         "stem": stem, "completed": answers == 3})
    return files, {"dataset": DATASET, "synthetic": True, "runs": runs,
                   "participants": sorted({r["participant_id"] for r in runs}),
                   "files": {name: sha256(body).hexdigest() for name, body in files.items()}}


def json_lines(events):
    return "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events).encode()


def seed(output, settings, today):
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / MANIFEST
    if manifest.exists():
        report = json.loads(manifest.read_text())
        if report.get("dataset") != DATASET or report.get("synthetic") is not True:
            raise ValueError("Unexpected demo manifest; no files were changed.")
        for name, digest in report["files"].items():
            if Path(name).name != name or DATASET not in name or sha256((output / name).read_bytes()).hexdigest() != digest:
                raise ValueError("Demo files have changed or are missing; no files were overwritten.")
        return report, False
    files, report = demo_files(settings, today)
    if not files:
        raise ValueError("No participant IDs are configured in the local preview.")
    if any((output / name).exists() or (output / name).is_symlink() for name in files):
        raise ValueError("A demo filename already exists; no files were overwritten.")
    created = []
    try:
        for name, body in files.items():
            with (output / name).open("xb") as target:
                created.append(output / name)
                target.write(body)
        with manifest.open("x") as target:
            created.append(manifest)
            json.dump(report, target, indent=2)
            target.write("\n")
    except BaseException:
        for path in reversed(created):
            path.unlink()
        raise
    return report, True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-preview", action="store_true", required=True,
                        help="Explicitly identify the isolated local preview")
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    settings = State(args.state_dir).settings()
    report, created = seed(args.log_dir, settings, datetime.now(ZoneInfo("Europe/Zurich")).date())
    print(f"{'Created' if created else 'Already present'}: {len(report['participants'])} synthetic participants, "
          f"{len(report['runs'])} runs, {len(report['files'])} files.")
    for grade in GRADES:
        ids = sorted({r["participant_id"] for r in report["runs"] if r["grade"] == grade})
        if ids:
            print(f"Grade {grade}: {', '.join(ids)}")
    print("Study settings unchanged. All fixture files contain the sol-ui-demo-v1 marker.")


if __name__ == "__main__":
    main()
