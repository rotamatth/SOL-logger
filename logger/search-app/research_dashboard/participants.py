"""Permanent study identities and annual enrollment, independent of Flask/reporting.

Mutation functions receive the State transaction. They never commit independently:
identity edits, settings revisions, audit records and attempt admission share one
SQLite writer boundary. Original collection identities are never rewritten.
"""
from datetime import date, datetime, timezone
import json
import re
import uuid

GRADES = ("3", "4", "5")
SCHEMA_VERSION = 2


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def valid_school_year(value):
    return (isinstance(value, str) and bool(re.fullmatch(r"[0-9]{4}/[0-9]{4}", value))
            and 1 <= int(value[:4]) < 9999 and int(value[5:]) == int(value[:4]) + 1)


def school_year_for(study_date):
    """Return the September–August year for a known date, never for missing data."""
    try:
        day = date.fromisoformat(study_date)
        start = day.year if day.month >= 9 else day.year - 1
        value = f"{start:04d}/{start + 1:04d}"
        return value if valid_school_year(value) else None
    except (TypeError, ValueError):
        return None


def year_contains(school_year, study_date):
    if not valid_school_year(school_year) or not study_date:
        return False
    try:
        day = date.fromisoformat(study_date)
        return date(int(school_year[:4]), 9, 1) <= day <= date(int(school_year[5:]), 8, 31)
    except (TypeError, ValueError):
        return False


def range_roster(settings):
    return {rule["prefix"] + str(n).zfill(rule["width"]): rule["grade"]
            for rule in settings["ranges"] for n in range(rule["start"], rule["end"] + 1)}


def participant_sort_key(uid):
    return (not uid.isdigit(), int(uid) if uid.isdigit() else uid, uid)


def roster(settings, school_year=None):
    year = settings.get("current_school_year", "") if school_year is None else school_year
    registry = settings.get("participant_registry")
    if registry is None or not year:
        # The unassigned initial roster is visible for planning, never admission.
        return {uid: grade for uid, grade in range_roster(settings).items()
                if registry is None or registry.get(uid, {}).get("active")}
    members = settings.get("enrollments", {}).get(year, {})
    return {uid: members[uid]["grade"] for uid in sorted(members, key=participant_sort_key)
            if registry.get(uid, {}).get("active")}


def enrollment(settings, uid, school_year):
    person = settings.get("participant_registry", {}).get(uid)
    enrolled = settings.get("enrollments", {}).get(school_year, {}).get(uid)
    if not person or not person["active"] or not enrolled:
        return None
    return {"participant_id": uid, "participant_key": person["key"],
            "enrollment_id": enrolled["id"], "school_year": school_year, "grade": enrolled["grade"]}


def projection(db):
    registry = {row["id"]: {"key": row["participant_key"], "active": bool(row["active"]),
                            "created_at": row["created_at"]}
                for row in db.execute("SELECT * FROM participants ORDER BY id")}
    years = {}
    for row in db.execute("SELECT * FROM enrollments ORDER BY school_year, participant_id"):
        years.setdefault(row["school_year"], {})[row["participant_id"]] = {
            "id": row["id"], "grade": row["grade"]}
    links = [dict(row) for row in db.execute("SELECT * FROM participant_links WHERE revoked_at IS NULL ORDER BY created_at,id")]
    return {"participant_registry": registry, "enrollments": years, "participant_links": links}


def migrate(db, settings):
    """Reserve every previously configured V2 ID; never guess legacy identity."""
    db.execute("""CREATE TABLE IF NOT EXISTS participants (
        id TEXT PRIMARY KEY, participant_key TEXT NOT NULL UNIQUE,
        active INTEGER NOT NULL CHECK(active IN (0,1)), created_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS enrollments (
        id TEXT PRIMARY KEY, participant_id TEXT NOT NULL REFERENCES participants(id),
        school_year TEXT NOT NULL, grade TEXT NOT NULL CHECK(grade IN ('3','4','5')),
        UNIQUE(participant_id,school_year))""")
    db.execute("CREATE INDEX IF NOT EXISTS enrollment_year_grade ON enrollments(school_year,grade)")
    db.execute("""CREATE TABLE IF NOT EXISTS participant_links (
        id TEXT PRIMARY KEY, source_collection TEXT NOT NULL CHECK(source_collection='legacy'),
        source_id TEXT NOT NULL, date_from TEXT NOT NULL, date_to TEXT NOT NULL,
        participant_id TEXT NOT NULL REFERENCES participants(id), note TEXT NOT NULL,
        created_at TEXT NOT NULL, revision INTEGER NOT NULL, revoked_at TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS participant_link_source ON participant_links(source_collection,source_id,date_from,date_to)")
    db.execute("""CREATE TABLE IF NOT EXISTS participant_audit (
        id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, at TEXT NOT NULL,
        operation TEXT NOT NULL, details TEXT NOT NULL)""")
    current, reserved = range_roster(settings), set()
    for row in db.execute("SELECT body FROM settings"):
        reserved.update(range_roster(json.loads(row[0])))
    reserved.update(row[0] for row in db.execute("SELECT DISTINCT participant_id FROM study_attempts"))
    for uid in sorted(reserved):
        db.execute("INSERT OR IGNORE INTO participants VALUES (?,?,?,?)",
                   (uid, uuid.uuid4().hex, int(uid in current), now()))
    year = settings.get("current_school_year")
    if valid_school_year(year):
        for uid, grade in current.items():
            put_enrollment(db, uid, year, grade)
    audit(db, 0, "migration", {"reserved_ids": sorted(reserved), "current_school_year": year or None})


def audit(db, revision, operation, details):
    db.execute("INSERT INTO participant_audit(revision,at,operation,details) VALUES (?,?,?,?)",
               (revision, now(), operation, json.dumps(details, ensure_ascii=False)))


def put_enrollment(db, uid, year, grade):
    if not valid_school_year(year):
        raise ValueError("school_year_required")
    if grade not in GRADES:
        raise ValueError("invalid_enrollment")
    db.execute("""INSERT INTO enrollments VALUES (?,?,?,?)
               ON CONFLICT(participant_id,school_year) DO UPDATE SET grade=excluded.grade""",
               (uuid.uuid4().hex, uid, year, grade))


def sync_range_edits(db, previous, updated, revision):
    """Compatibility boundary for the original bulk roster editor.

    Only changed range members are affected. Individual enrollment changes remain
    intact when unrelated settings or an unchanged range template are saved.
    """
    before, after = range_roster(previous), range_roster(updated)
    year = updated.get("current_school_year")
    changes = []
    if before != after and db.execute("SELECT COUNT(DISTINCT school_year) FROM enrollments").fetchone()[0] > 1:
        raise ValueError("range_editor_retired")
    for uid in sorted(before.keys() | after.keys()):
        if before.get(uid) == after.get(uid):
            continue
        person = db.execute("SELECT active FROM participants WHERE id=?", (uid,)).fetchone()
        if uid in after:
            if person and not person[0]:
                raise ValueError("participant_inactive")
            if not person:
                db.execute("INSERT INTO participants VALUES (?,?,1,?)", (uid, uuid.uuid4().hex, now()))
            if year:
                put_enrollment(db, uid, year, after[uid])
        else:
            db.execute("UPDATE participants SET active=0 WHERE id=?", (uid,))
        changes.append({"id": uid, "before": before.get(uid), "after": after.get(uid)})
    if year and not previous.get("current_school_year"):
        # Explicit initial school-year confirmation enrolls the visible initial roster.
        for uid, grade in after.items():
            if db.execute("SELECT active FROM participants WHERE id=?", (uid,)).fetchone()[0]:
                put_enrollment(db, uid, year, grade)
        audit(db, revision, "initial_enrollment", {"school_year": year, "ids": sorted(after)})
    if changes:
        audit(db, revision, "range_edit", {"school_year": year, "changes": changes})


def parse_ids(text):
    if not isinstance(text, str) or len(text) > 32000:
        raise ValueError("invalid_participant_ids")
    ids = [uid for uid in re.split(r"[\s,;]+", text.strip()) if uid]
    if (not ids or len(ids) > 1000 or len(ids) != len(set(ids))
            or any(not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", uid) for uid in ids)):
        raise ValueError("invalid_participant_ids")
    return ids


def add_participants(db, ids, year, grade):
    if (not isinstance(ids, list) or any(not isinstance(uid, str) for uid in ids)
            or parse_ids("\n".join(ids)) != ids):
        raise ValueError("invalid_participant_ids")
    if not valid_school_year(year):
        raise ValueError("school_year_required")
    for uid in ids:
        if db.execute("SELECT 1 FROM participants WHERE id=?", (uid,)).fetchone():
            raise ValueError("participant_id_reserved")
        db.execute("INSERT INTO participants VALUES (?,?,1,?)", (uid, uuid.uuid4().hex, now()))
        put_enrollment(db, uid, year, grade)
    return {"ids": ids, "school_year": year, "grade": grade}


def update_participant(db, uid, year, grade, active):
    before = db.execute("SELECT * FROM participants WHERE id=?", (uid,)).fetchone()
    if not isinstance(uid, str) or not before or type(active) is not bool or not valid_school_year(year):
        raise ValueError("invalid_enrollment")
    old = db.execute("SELECT grade FROM enrollments WHERE participant_id=? AND school_year=?", (uid, year)).fetchone()
    if active:
        put_enrollment(db, uid, year, grade)
    db.execute("UPDATE participants SET active=? WHERE id=?", (int(active), uid))
    return {"id": uid, "school_year": year, "before": {"active": bool(before["active"]), "grade": old[0] if old else None},
            "after": {"active": active, "grade": grade if active else (old[0] if old else None)}}


def enroll_participants(db, ids, year, grade):
    """Assign known active children to a year, retaining their permanent keys."""
    if (not isinstance(ids, list) or any(not isinstance(uid, str) for uid in ids)
            or parse_ids("\n".join(ids)) != ids):
        raise ValueError("invalid_participant_ids")
    changes = []
    for uid in ids:
        person = db.execute("SELECT active FROM participants WHERE id=?", (uid,)).fetchone()
        if not person:
            raise ValueError("participant_not_registered")
        if not person["active"]:
            raise ValueError("participant_inactive")
        before = db.execute("SELECT grade FROM enrollments WHERE participant_id=? AND school_year=?", (uid, year)).fetchone()
        put_enrollment(db, uid, year, grade)
        changes.append({"id": uid, "before_grade": before[0] if before else None, "grade": grade})
    return {"ids": ids, "school_year": year, "grade": grade, "changes": changes}


def promotion_plan(settings, source_year, target_year):
    if (not valid_school_year(source_year) or not valid_school_year(target_year)
            or int(target_year[:4]) != int(source_year[:4]) + 1):
        raise ValueError("invalid_promotion_year")
    plan = []
    for uid, grade in roster(settings, source_year).items():
        target = str(int(grade) + 1) if grade != GRADES[-1] else None
        existing = settings.get("enrollments", {}).get(target_year, {}).get(uid)
        if existing and existing["grade"] != target:
            raise ValueError("enrollment_conflict")
        plan.append({"id": uid, "from_grade": grade, "to_grade": target})
    if not plan:
        raise ValueError("empty_promotion")
    return sorted(plan, key=lambda row: (row["from_grade"], participant_sort_key(row["id"])))


def promote(db, settings, source_year, target_year):
    plan = promotion_plan(settings, source_year, target_year)
    for item in plan:
        if item["to_grade"]:
            put_enrollment(db, item["id"], target_year, item["to_grade"])
    return {"source_year": source_year, "target_year": target_year, "participants": plan}


def link_legacy(db, source_id, uid, date_from, date_to, note, revision):
    if (not isinstance(source_id, str) or not 1 <= len(source_id) <= 128
            or not isinstance(uid, str)
            or not db.execute("SELECT 1 FROM participants WHERE id=?", (uid,)).fetchone()
            or not isinstance(note, str) or not 1 <= len(note.strip()) <= 300):
        raise ValueError("invalid_identity_link")
    try:
        if (date.fromisoformat(date_from).isoformat() != date_from
                or date.fromisoformat(date_to).isoformat() != date_to or date_from > date_to):
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError("invalid_identity_link") from None
    if db.execute("""SELECT 1 FROM participant_links WHERE source_collection='legacy'
                     AND source_id=? AND revoked_at IS NULL AND date_from<=? AND date_to>=?""",
                  (source_id, date_to, date_from)).fetchone():
        raise ValueError("identity_link_conflict")
    key = uuid.uuid4().hex
    db.execute("INSERT INTO participant_links VALUES (?,'legacy',?,?,?,?,?,?,?,NULL)",
               (key, source_id, date_from, date_to, uid, note.strip(), now(), revision))
    return {"id": key, "source_id": source_id, "participant_id": uid,
            "date_from": date_from, "date_to": date_to, "note": note.strip()}


def resolve_identity(settings, collection, uid, study_date):
    if collection == "v2" and uid in settings.get("participant_registry", {}):
        return {"id": uid, "key": settings["participant_registry"][uid]["key"], "source": "registry", "link_id": None}
    if collection == "legacy" and study_date:
        for link in settings.get("participant_links", []):
            if link["source_id"] == uid and link["date_from"] <= study_date <= link["date_to"]:
                person = settings["participant_registry"][link["participant_id"]]
                return {"id": link["participant_id"], "key": person["key"], "source": "confirmed_link",
                        "link_id": link["id"], "link_revision": link["revision"]}
    return None
