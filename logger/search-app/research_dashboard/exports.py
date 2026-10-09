"""One disk-backed ZIP exporter for every scope, preserving original source bytes."""
from hashlib import sha256
import json
import os
import re
import shutil
import tempfile
import zipfile

from .index import safe_open
from .state import identity, utc_now


def component(value):
    text = str(value) if value is not None else "unknown"
    label = re.sub(r"[^A-Za-z0-9_-]", "_", text)[:40] or "unknown"
    return f"{label}-{identity(text)[:12]}"


def build_export(index, selected, settings, scope, task=None, selection=None):
    """Capture file lengths first; stream those byte prefixes to a private temporary ZIP.

    This is a per-file snapshot, not a transaction across concurrently written logs.
    Partial final lines are preserved byte-for-byte and reported in the manifest.
    """
    manifest = {
        "schema_version": 1, "exported_at": utc_now(), "scope": scope,
        "settings_revision": settings["revision"], "format": "ZIP; .log files contain JSON Lines",
        "selection": selection or {},
        "study_ids": sorted({run["study_id"] or "unknown" for run in selected}),
        "includes_incomplete_runs": True, "includes_repeated_runs": True,
        "duplicate_events": "Full and per-task logs can contain the same events. Use the full log once, or the task logs, not both.",
        "snapshot": "Export uses each source byte prefix captured by the refreshed index. Later appends are excluded. This is not an atomic snapshot across files. Prefix hashes are verified; changed, truncated, unreadable and partial files are reported.",
        "completion_rule": "All three presented tasks have a TaskEnded event with a string answer (including an explicitly empty string). Final-save confirmation is separate.",
        "diagram_generation": "Not implemented; no diagram artifacts exist in this release.",
        "available_sessions": [], "runs": [], "files": [], "problems": [],
    }
    output = tempfile.TemporaryFile(mode="w+b")
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            plans = _prepare(index, selected, settings, task, manifest, archive)
            _copy_sources(index, plans, manifest, archive)
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        output.seek(0)
        return output
    except BaseException:
        output.close()
        raise


def _prepare(index, selected, settings, task, manifest, archive):
    plans, session_ids = [], set()
    # Write each run's derived metadata immediately; do not hold a class's answers in RAM.
    for summary in selected:
        run = index.run(summary["id"], settings)
        if not run:
            manifest["problems"].append({"run_id": summary["id"], "code": "run_unavailable"})
            continue
        if any(run[key] != summary[key] for key in ("study_id", "participant_id", "collection", "grade", "study_session", "school_year", "historical_assignment_id")):
            manifest["problems"].append({"run_id": summary["id"], "code": "run_classification_changed_retry_export"})
            continue
        session = run["study_session"]
        if session and session["id"] not in session_ids:
            manifest["available_sessions"].append(session)
            session_ids.add(session["id"])
        folder = "/".join((component(run["study_id"] or "unknown"), run["collection"], f"grade-{run['grade'] or 'unknown'}",
                           component(run["participant_id"]),
                           session["id"] if session else "unassigned", run["id"]))
        relevant = [f for f in run["files"] if task is None or (f["kind"] == "task" and f["position"] == task)]
        if task is not None and not relevant:
            manifest["problems"].append({"run_id": run["id"], "task": task, "code": "original_task_file_missing"})
        for f in relevant:
            plan = {"run_id": run["id"], "collection": run["collection"], "file_id": f["id"],
                    "source_name": f["name"], "archive_name": f"{folder}/sources/{component(f['id'])}{'.run.json' if f['kind'] == 'metadata' else '.log'}"}
            if task is not None and any(number != task for number in f["tasks"]):
                plan["problem"] = "task_file_contains_other_tasks"
            try:
                with safe_open(index.roots[run["collection"]], f["name"]) as source:
                    s = os.fstat(source.fileno())
                    if s.st_ino != f["inode"] or s.st_size < f["size"]:
                        plan["problem"] = "source_replaced_or_truncated"
                    plan.update(size=f["size"], inode=f["inode"], mtime_ns=f["mtime_ns"],
                                indexed_sha256=f.get("sha256"))
                    if not f.get("sha256"):
                        plan["problem"] = "source_not_fully_indexed"
            except (OSError, KeyError):
                plan["problem"] = "source_unavailable"
            plans.append(plan)
        tasks = {k: v for k, v in run["tasks"].items() if task is None or k == task}
        entry = {
            "run_id": run["id"], "study_id": run["study_id"],
            "participant_id": run["participant_id"], "grade": run["grade"],
            "school_year": run["school_year"], "grade_source": run["grade_source"],
            "school_year_source": run["school_year_source"],
            "historical_assignment_id": run["historical_assignment_id"], "current_grade": run["current_grade"],
            "collection": run["collection"], "technical_session_ids": run["technical_session_ids"],
            "log_id": run["log_id"], "log_id_source": run["log_id_source"],
            "study_session": session, "experiment_date": run["date"],
            "app_version": run["app_version"], "git_commit": run["git_commit"],
            "metadata_path": f"{folder}/metadata.json", "status": run["status"],
            "task_statuses": {k: t["status"] for k, t in tasks.items()},
            "missing_answers": [k for k, t in tasks.items() if not any(a["present"] for a in t["answers"])],
            "missing_task_files": [k for k in tasks if not any(f["kind"] == "task" and f["position"] == k for f in run["files"])],
            "final_save_confirmed": run["finished"], "issues": run["issues"],
        }
        manifest["runs"].append(entry)
        metadata = {**entry, "tasks": tasks, "settings_revision": settings["revision"], "diagram_artifacts": []}
        archive.writestr(entry["metadata_path"], json.dumps(metadata, ensure_ascii=False, indent=2))
    return plans


class SourceSnapshotError(Exception):
    """An original source could not be captured safely at its indexed revision."""


def capture_source(index, plan):
    """Stage and verify an indexed byte prefix for ZIP and individual-log downloads."""
    if not plan.get("indexed_sha256"):
        raise SourceSnapshotError("source_not_fully_indexed")
    staged = tempfile.TemporaryFile(mode="w+b")
    digest, last_byte = sha256(), None
    try:
        with safe_open(index.roots[plan["collection"]], plan["source_name"]) as source:
            start = os.fstat(source.fileno())
            if start.st_ino != plan["inode"] or start.st_size < plan["size"]:
                raise SourceSnapshotError("source_replaced_or_truncated")
            remaining = plan["size"]
            while remaining:
                data = source.read(min(65536, remaining))
                if not data:
                    raise SourceSnapshotError("source_truncated_during_export")
                staged.write(data)
                digest.update(data)
                last_byte = data[-1:]
                remaining -= len(data)
            end = os.fstat(source.fileno())
        if digest.hexdigest() != plan["indexed_sha256"]:
            raise SourceSnapshotError("source_modified_since_index")
        staged.seek(0)
        return staged, {
            "changed_during_export": (end.st_size, end.st_mtime_ns) != (plan["size"], plan["mtime_ns"]),
            "partial_final_line": plan["source_name"].endswith(".log") and last_byte not in (None, b"\n"),
            "prefix_matches_index": True, "sha256": digest.hexdigest(),
        }
    except BaseException as exc:
        staged.close()
        if isinstance(exc, (OSError, KeyError)):
            raise SourceSnapshotError("source_read_failed") from exc
        raise


def capture_log(index, run, source):
    return capture_source(index, {
        "collection": run["collection"], "source_name": source["name"],
        "inode": source.get("inode"), "size": source["size"],
        "mtime_ns": source.get("mtime_ns"), "indexed_sha256": source.get("sha256"),
    })


def _copy_sources(index, plans, manifest, archive):
    for plan in plans:
        record = {k: v for k, v in plan.items() if k not in ("inode", "mtime_ns", "collection")}
        record.update(included=False, bytes_copied=0)
        manifest["files"].append(record)
        if plan.get("problem"):
            continue
        try:
            staged, details = capture_source(index, plan)
            with staged:
                record.update(details)
                with archive.open(plan["archive_name"], "w", force_zip64=True) as target:
                    shutil.copyfileobj(staged, target, length=65536)
                record["included"] = True
                record["bytes_copied"] = plan["size"]
        except SourceSnapshotError as exc:
            record["problem"] = str(exc)
        except OSError:
            record["problem"] = "source_read_failed"
