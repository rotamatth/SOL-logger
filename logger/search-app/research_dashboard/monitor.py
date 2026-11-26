"""Which tablet needs an adult now: the live view's classroom map, kept apart from the study's data.

A tablet is registered when an adult chooses a valid ID, before the practice, and stays registered through the
practice, the experiment and the last page until the tablet is reset or given another ID. The registration
belongs to the study session and the participant ID (the number on the tablet's sticker), with an opaque token
in a cookie of its own, so it outlives the run's browser session that Salva clears.

Each registered tablet reports every two seconds what it can know: its page, whether the page is visible, full
screen, and saves it could not confirm. The server adds what only it sees: searches the engine refused and saves
it could not store. The colour of a circle is worked out when the dashboard asks, from the server's own clock,
so the tablets' and the researcher's clocks never matter.

Nothing here is study data: no answers, queries or app names, and no log, attempt or export reads it. It lives in
its own small database file, so a write here never waits on, or holds up, saving a log or an answer, and every
failure is swallowed: the map then knows less, and nothing else changes.
"""
from contextlib import closing
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time

# Timing, in seconds of the server's clock. Initial targets, to tune on the classroom tablets (research_dashboard.md).
BEAT_SECONDS = 2               # The tablet's signal; static/connection-watch.js has the same value.
LATE_AFTER = 4                 # Amber: the signal is late.
LOST_AFTER = 6                 # Red: no contact.
SEARCH_STALLED_AFTER = 20      # A search that has not come back in this long is shown as waiting.
TWO_TABLETS_WITHIN = 30        # Two registrations of one ID both heard from in this window.
REGISTRATION_HOURS = 16        # A registration older than this is over: a tablet left on is not monitored forever.
HISTORY_PER_SESSION = 400      # Incident starts and recoveries kept per session, newest first.
HISTORY_DAYS = 30

PAGE_MAX = 80
STAGES = ("prepared", "practice", "experiment", "recap", "finished")
CLIENT_INCIDENTS = ("save_unconfirmed",)
SERVER_INCIDENTS = ("search_failed", "save_failed")
REASONS = {  # code: severity, from the most to the least serious within each level.
    "no_contact": "red", "search_failed": "red", "save_failed": "red", "save_unconfirmed": "red",
    "contact_late": "amber", "page_hidden": "amber", "no_signal_hidden": "amber", "fullscreen_off": "amber",
    "search_waiting": "amber", "two_tablets": "amber",
}
SEVERITY = {"red": 3, "amber": 2, "green": 1, "grey": 0}
SAVE_REASONS = ("network", "conflict", "server", "unconfirmed")
TOKEN = re.compile(r"[A-Za-z0-9_-]{20,64}")


def stage_for(path):
    """The part of the visit a children's page belongs to, from its path alone."""
    path = path if isinstance(path, str) else ""
    if path.startswith("/prova"):
        return "practice"
    if path.startswith("/fine"):
        return "finished"
    if path.startswith(("/thank_you", "/recap")):
        return "recap"
    if path.startswith(("/task", "/search", "/result", "/webpage", "/task-review", "/next_task", "/first-answer")):
        return "experiment"
    return "prepared"


def _now(now):
    return time.time() if now is None else now


class Monitor:
    def __init__(self, directory):
        self.path = Path(directory) / "monitor.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(self._connect()) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS registrations (
                    token TEXT PRIMARY KEY, study_session_id TEXT NOT NULL, participant_id TEXT NOT NULL,
                    created REAL NOT NULL, retired REAL,
                    last_seen REAL, client_order REAL NOT NULL DEFAULT 0, page TEXT NOT NULL DEFAULT '',
                    visible INTEGER, visible_since REAL, fullscreen_capable INTEGER, fullscreen_active INTEGER,
                    search_pending_since REAL, client_incidents TEXT NOT NULL DEFAULT '{}',
                    server_incidents TEXT NOT NULL DEFAULT '{}', last_save REAL);
                CREATE INDEX IF NOT EXISTS registrations_by_session ON registrations(study_session_id, participant_id);
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, study_session_id TEXT NOT NULL, participant_id TEXT NOT NULL,
                    at REAL NOT NULL, code TEXT NOT NULL, event TEXT NOT NULL CHECK(event IN ('start', 'recovered')),
                    seconds INTEGER);
                CREATE INDEX IF NOT EXISTS history_by_session ON history(study_session_id, id);
            """)
        self.path.chmod(0o600)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=0.5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=NORMAL")
        return db

    # -- Registrations --------------------------------------------------------------------------------------------

    def active(self, token, now=None):
        """The registration behind a cookie, or None: unknown, retired, or too old."""
        if not (isinstance(token, str) and TOKEN.fullmatch(token)):
            return None
        try:
            with closing(self._connect()) as db:
                row = db.execute("SELECT * FROM registrations WHERE token=?", (token,)).fetchone()
        except sqlite3.Error:
            return None
        if row is None or row["retired"] is not None or row["created"] < _now(now) - REGISTRATION_HOURS * 3600:
            return None
        return dict(row)

    def register(self, study_session_id, participant_id, current_token=None, now=None):
        """The token for this tablet's study session and ID: the current one if it already matches, else a new one.

        A different current registration (the tablet's previous ID or class) is retired, so preparing a tablet for
        the afternoon never keeps updating the morning's circle. Returns None if the database is unavailable.
        """
        if not (isinstance(study_session_id, str) and isinstance(participant_id, str)
                and study_session_id and participant_id):
            return None
        current = self.active(current_token, now)
        if current and current["study_session_id"] == study_session_id and current["participant_id"] == participant_id:
            return current["token"]
        token = secrets.token_urlsafe(24)
        try:
            with closing(self._connect()) as db, db:
                if current:
                    db.execute("UPDATE registrations SET retired=? WHERE token=?", (_now(now), current["token"]))
                db.execute("INSERT INTO registrations(token, study_session_id, participant_id, created) VALUES (?,?,?,?)",
                           (token, study_session_id, participant_id, _now(now)))
            return token
        except sqlite3.Error:
            return None

    def retire(self, token, now=None):
        if not (isinstance(token, str) and TOKEN.fullmatch(token)):
            return False
        try:
            with closing(self._connect()) as db, db:
                db.execute("UPDATE registrations SET retired=? WHERE token=? AND retired IS NULL", (_now(now), token))
            return True
        except sqlite3.Error:
            return False

    # -- Reports ----------------------------------------------------------------------------------------------------

    def beat(self, token, report, now=None):
        """Store a tablet's report. False when it is not stored: unknown token, a report older than one already
        stored (`order`, the tablet's own counter, never goes back), a bad report, or an unavailable database."""
        now = _now(now)
        current = self.active(token, now)
        if current is None or not isinstance(report, dict):
            return False
        order = report.get("order")
        if not isinstance(order, (int, float)) or isinstance(order, bool) or order <= current["client_order"]:
            return False
        page = report.get("page") if isinstance(report.get("page"), str) else ""
        visible = report.get("visible") is not False
        fullscreen = report.get("fullscreen") if isinstance(report.get("fullscreen"), dict) else {}
        capable, active = fullscreen.get("capable"), fullscreen.get("active")
        pending = _seconds(report.get("searchPendingFor"))
        incidents = {}
        for item in report.get("incidents") if isinstance(report.get("incidents"), list) else []:
            if (isinstance(item, dict) and item.get("code") in CLIENT_INCIDENTS and len(incidents) < len(CLIENT_INCIDENTS)):
                reason = item.get("reason") if item.get("reason") in SAVE_REASONS else "unconfirmed"
                incidents[item["code"]] = {"since": now - (_seconds(item.get("for")) or 0), "reason": reason}
        saved_for = _seconds(report.get("lastSaveFor"))
        previous_incidents = _load(current["client_incidents"])
        for code, value in incidents.items():  # An incident keeps its first start, whatever later reports say.
            if code in previous_incidents:
                value["since"] = previous_incidents[code]["since"]
        visible_since = current["visible_since"] if current["visible"] == int(visible) and current["visible_since"] else now
        try:
            with closing(self._connect()) as db, db:
                db.execute("""UPDATE registrations SET last_seen=?, client_order=?, page=?, visible=?, visible_since=?,
                    fullscreen_capable=?, fullscreen_active=?, search_pending_since=?, client_incidents=?,
                    last_save=COALESCE(?, last_save) WHERE token=?""",
                           (now, float(order), page[:PAGE_MAX], int(visible), visible_since, _flag(capable), _flag(active),
                            now - pending if pending is not None else None, json.dumps(incidents),
                            now - saved_for if saved_for is not None else None, token))
                self._record(db, current, previous_incidents, incidents, now)
                if current["last_seen"] is not None and now - current["last_seen"] >= LOST_AFTER:
                    # A silence is only known once it ends: its start and its recovery are written together.
                    gap, code = int(now - current["last_seen"]), "no_signal_hidden" if current["visible"] == 0 else "no_contact"
                    self._history(db, current, current["last_seen"] + LOST_AFTER, code, "start", None)
                    self._history(db, current, now, code, "recovered", gap)
            return True
        except sqlite3.Error:
            return False

    def server_incident(self, token, code, active, reason=None, now=None):
        """What only the server sees: a search the engine refused, a save it could not store, and their recovery."""
        now = _now(now)
        current = self.active(token, now)
        if current is None or code not in SERVER_INCIDENTS:
            return False
        incidents = _load(current["server_incidents"])
        before = dict(incidents)
        if active and code not in incidents:
            incidents[code] = {"since": now, "reason": reason if reason in SAVE_REASONS else "server"}
        elif not active:
            incidents.pop(code, None)
        if incidents == before:
            return True
        try:
            with closing(self._connect()) as db, db:
                db.execute("UPDATE registrations SET server_incidents=?, last_save=CASE WHEN ? THEN ? ELSE last_save END "
                           "WHERE token=?", (json.dumps(incidents), int(code == "save_failed" and not active), now, token))
                self._record(db, current, before, incidents, now)
            return True
        except sqlite3.Error:
            return False

    def _record(self, db, registration, before, after, now):
        for code in after.keys() - before.keys():
            self._history(db, registration, after[code]["since"], code, "start", None)
        for code in before.keys() - after.keys():
            self._history(db, registration, now, code, "recovered", int(now - before[code]["since"]))

    @staticmethod
    def _history(db, registration, at, code, event, seconds):
        session_id = registration["study_session_id"]
        db.execute("INSERT INTO history(study_session_id, participant_id, at, code, event, seconds) VALUES (?,?,?,?,?,?)",
                   (session_id, registration["participant_id"], at, code, event, seconds))
        db.execute("""DELETE FROM history WHERE study_session_id=? AND id NOT IN
                      (SELECT id FROM history WHERE study_session_id=? ORDER BY id DESC LIMIT ?)""",
                   (session_id, session_id, HISTORY_PER_SESSION))
        db.execute("DELETE FROM history WHERE at < ?", (time.time() - HISTORY_DAYS * 86400,))

    # -- The dashboard's view ---------------------------------------------------------------------------------------

    def health(self, study_session_id, now=None):
        """{participant_id: tablet} for every ID registered in this session, worked out at `now`, or None when the
        database cannot be read (the map then says that monitoring is unavailable, instead of blaming tablets)."""
        now = _now(now)
        try:
            with closing(self._connect()) as db:
                rows = db.execute("""SELECT * FROM registrations WHERE study_session_id=? AND retired IS NULL
                                     AND created >= ? ORDER BY created""",
                                  (study_session_id, now - REGISTRATION_HOURS * 3600)).fetchall()
                history = db.execute("""SELECT participant_id, at, code, event, seconds FROM history
                                        WHERE study_session_id=? ORDER BY id DESC LIMIT ?""",
                                     (study_session_id, HISTORY_PER_SESSION)).fetchall()
        except sqlite3.Error:
            return None
        by_id = {}
        for row in rows:
            by_id.setdefault(row["participant_id"], []).append(dict(row))
        tablets = {}
        for participant_id, registrations in by_id.items():
            heard = [item for item in registrations if item["last_seen"] is not None]
            latest = max(heard, key=lambda item: item["last_seen"]) if heard else registrations[-1]
            tablet = _tablet(latest, now)
            recent = [item for item in heard if now - item["last_seen"] < TWO_TABLETS_WITHIN]
            if len(recent) > 1:
                tablet["reasons"].append({"code": "two_tablets", "severity": "amber", "since": None})
                tablet["status"] = _worst(tablet)
            tablet["history"] = []
            tablets[participant_id] = tablet
        for participant_id, at, code, event, seconds in history:
            tablet = tablets.get(participant_id)
            if tablet is not None and len(tablet["history"]) < 10:
                tablet["history"].append({"at": at, "code": code, "event": event, "seconds": seconds})
        return tablets


def _tablet(row, now):
    """One tablet's colour and reasons, from its latest registration, at the server's `now`."""
    tablet = {"stage": stage_for(row["page"]) if row["last_seen"] is not None else "prepared",
              "connected": row["last_seen"] is not None,
              "age": None if row["last_seen"] is None else max(0.0, round(now - row["last_seen"], 1)),
              "visible": None if row["visible"] is None else bool(row["visible"]),
              "visible_since": row["visible_since"],
              "fullscreen": {"capable": _bool(row["fullscreen_capable"]), "active": _bool(row["fullscreen_active"])},
              "last_save": row["last_save"], "registered": row["created"], "reasons": []}
    reasons = tablet["reasons"]
    if row["last_seen"] is None:
        tablet["status"] = "grey"  # Registered, but nothing heard yet: not connected yet, not lost.
        return tablet
    age = now - row["last_seen"]
    if row["visible"] == 0:
        reasons.append({"code": "page_hidden", "severity": "amber", "since": row["visible_since"]})
        if age >= LOST_AFTER:  # Timers sleep in a hidden page: silence then proves nothing about the network.
            reasons.append({"code": "no_signal_hidden", "severity": "amber", "since": row["last_seen"]})
    elif age >= LOST_AFTER:
        reasons.append({"code": "no_contact", "severity": "red", "since": row["last_seen"]})
    elif age >= LATE_AFTER:
        reasons.append({"code": "contact_late", "severity": "amber", "since": row["last_seen"]})
    for code, value in {**_load(row["client_incidents"]), **_load(row["server_incidents"])}.items():
        if code in REASONS:
            reasons.append({"code": code, "severity": REASONS[code], "since": value.get("since"),
                            "reason": value.get("reason")})
    if (row["fullscreen_capable"] == 1 and row["fullscreen_active"] == 0 and row["visible"] != 0
            and tablet["stage"] in ("practice", "experiment", "recap")):
        reasons.append({"code": "fullscreen_off", "severity": "amber", "since": None})
    if row["search_pending_since"] is not None and now - row["search_pending_since"] >= SEARCH_STALLED_AFTER:
        reasons.append({"code": "search_waiting", "severity": "amber", "since": row["search_pending_since"]})
    reasons.sort(key=lambda item: (-SEVERITY[item["severity"]], list(REASONS).index(item["code"])))
    tablet["status"] = _worst(tablet)
    return tablet


def _worst(tablet):
    reasons = tablet["reasons"]
    return max((item["severity"] for item in reasons), key=SEVERITY.get) if reasons else "green"


def _seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value < 86400:
        return None
    return float(value)


def _flag(value):
    return None if value is None else int(value is True)


def _bool(value):
    return None if value is None else bool(value)


def _load(text):
    try:
        value = json.loads(text or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}
