"""Read models for the history views and exports: runs, participants and labels."""
from copy import deepcopy
import json

from flask import g

from .participants import GRADES
from .state import DEFAULT_STUDY_ID, identity, roster

SESSION_LABEL_FIELDS = ("id", "grade", "number", "name", "date", "theme", "school_year")


def display_session(configured_session, runs):
    """Label collected sessions with their recorded names and dates."""
    def label(study_session):
        return {key: deepcopy(study_session.get(key, "")) for key in SESSION_LABEL_FIELDS}

    snapshots = [label(run["study_session"]) for run in runs
                 if run.get("study_session")
                 and run["study_session"]["id"] == configured_session["id"]]
    if not snapshots:
        return label(configured_session)
    if len({json.dumps(snapshot, sort_keys=True) for snapshot in snapshots}) == 1:
        return snapshots[0]
    # Repeated attempts can have different recorded labels for the same ID.
    # Their individual rows show those labels; the common group stays neutral.
    return {**label(configured_session), "name": "", "date": "", "theme": ""}


def collection_runs(state, summaries, collection):
    """Runs of one collection ("v2", "legacy" or the combined "study"), excluding the trash."""
    if "research_trashed_run_ids" not in g:
        g.research_trashed_run_ids = state.trashed_run_ids()
    return [run for run in summaries if run["id"] not in g.research_trashed_run_ids
            and run["study_id"] in (DEFAULT_STUDY_ID, None) and (
                run["collection"] == collection or collection == "study" and (
                    run["collection"] == "v2" or run["grade"] in GRADES or run.get("study_participant_id")))]


def _participant_sort_key(person):
    uid = person["id"]
    return (not uid.isdigit(), int(uid) if uid.isdigit() else uid, uid)


def collect_participants(state, settings, summaries, collection):
    """One entry per participant identity with their runs and known grades."""
    people = {}
    current_roster = roster(settings)
    enrollment_grades = {}
    for members in settings["enrollments"].values():
        for uid, item in members.items():
            enrollment_grades.setdefault(uid, set()).add(item["grade"])
    if collection in ("v2", "study"):
        for uid in settings["participant_registry"]:
            grades = set(enrollment_grades.get(uid, ()))
            if not grades and uid in current_roster:
                grades.add(current_roster[uid])
            people[(collection, uid)] = {"id": uid, "token": identity(uid), "collection": collection,
                                         "grades": grades, "runs": []}
    for run in collection_runs(state, summaries, collection):
        if run["participant_id"] is None:
            continue
        linked = collection == "study" and run.get("study_participant_id")
        uid = run["study_participant_id"] if linked else run["participant_id"]
        source = "study" if linked else run["collection"]
        # Unlinked sources retain separate namespaces even when numbers match.
        person = people.setdefault((source, uid), {"id": uid, "token": identity(uid),
                                                   "collection": source, "grades": set(), "runs": []})
        if run["grade"]:
            person["grades"].add(run["grade"])
        person["runs"].append(run)
    return sorted(people.values(), key=_participant_sort_key)


def scoped_people(state, settings, summaries, collection, grade, selected_year=None, selected_session=None):
    """Participants visible in a grade/year/session view, with the runs in that scope."""
    people = collect_participants(state, settings, summaries, collection)
    if grade not in ("all", "legacy"):
        people = [p for p in people if grade in p["grades"] or (grade == "unassigned" and (
            not p["grades"] or any(not r["study_session"] for r in p["runs"])))]
    current_roster = roster(settings)
    for p in people:
        p["visible_runs"] = [r for r in p["runs"] if (grade not in GRADES or r["grade"] == grade)
                             and (not selected_year or r["school_year"] == selected_year)
                             and (not selected_session or r["study_session"]
                                  and r["study_session"]["id"] == selected_session["id"])]
        p["has_downloadable_logs"] = any(r.get("log_file_count", r["event_count"]) for r in p["visible_runs"])
        p["dashboard_status"] = (
            "no_data" if not p["visible_runs"] else
            "completed" if all(run["status"] == "completed" for run in p["visible_runs"]) else "incomplete")
        p["recorded_grades"] = sorted({run["grade"] for run in p["visible_runs"] if run["grade"]})
        p["school_years"] = sorted({run["school_year"] for run in p["visible_runs"] if run["school_year"]},
                                   reverse=True)
        p["current_grade"] = current_roster.get(p["id"]) if p["collection"] in ("v2", "study") else None
    return [person for person in people if person["visible_runs"]] if selected_year else people


def has_logs(run):
    return bool(run.get("log_file_count", run["event_count"]))
