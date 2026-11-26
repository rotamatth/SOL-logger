"""Classrooms drawn to scale for the live view's map, and each session's copy with its IDs placed on desks.

A room is drawn once on the dashboard's Rooms page, in centimetres: its width and depth, its double desks, alone
or pushed together face to face into islands of 2 or 4, and landmarks to find one's way (the teacher's desk, the
board, doors and windows). Every desk has one tablet spot, or two once there is a device per child. Rooms are shared
by every researcher and never carry participant IDs, so reusing one never brings another class along.

A session's map is a copy of a room plus the spot where each ID sits. The live view only places IDs: the room's
shape changes on the Rooms page, and reaches a session only when a researcher brings the new version in, keeping
every ID whose spot still exists. Placing an ID is a display choice for the map, never an admission or attendance
rule. Room saves carry the revision they were based on, so two dashboards cannot silently overwrite each other;
placing an ID is a single change applied to the current map. Nothing here is study data.
"""
from contextlib import closing
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time

GRID_CM = 50
ROOM_CM = (200, 3000)
DESK_CM = (130, 50)
SEAT_CM = 32                       # each of a desk's two tablet spots, from its centre along its length
ISLAND_DESKS = {2: ((0, -25), (0, 25)), 4: ((-65, -25), (65, -25), (-65, 25), (65, 25))}
LANDMARKS_CM = {"teacher": (150, 70), "board": (300, 12), "door": (90, 12), "window": (120, 12)}
KINDS = ("desk", "island", *LANDMARKS_CM)
MAX_PIECES = 120
MAX_PLACEMENTS = 200
NAME_MAX = 80
OBJECT_ID = re.compile(r"[A-Za-z0-9_-]{1,40}")


class Conflict(Exception):
    """Someone changed it since this copy was loaded: the caller gets the current version back."""

    def __init__(self, current):
        super().__init__("changed")
        self.current = current


def _number(value, low, high, error="invalid_room"):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError(error)
    return round(float(value), 1)


def _participant(value):
    if not isinstance(value, str) or not 0 < len(value) <= 40 or any(ord(char) < 32 for char in value):
        raise ValueError("invalid_placement")
    return value


def desks(piece):
    """Where a piece's desks sit, from its centre and before it turns: one for a desk, 2 or 4 for an island."""
    if piece["kind"] == "desk":
        return ((0, 0),)
    if piece["kind"] == "island":
        return ISLAND_DESKS[piece["desks"]]
    return ()


def spot_ids(geometry):
    """Every tablet spot in the room, named piece.desk.seat so that it survives the room's later edits."""
    return [f"{piece['id']}.{desk}.{seat}" for piece in geometry["pieces"]
            for desk in range(len(desks(piece))) for seat in range(piece.get("tablets", 0))]


def validate_geometry(body):
    """A room's size and pieces, normalized. Raises ValueError("invalid_room")."""
    if not isinstance(body, dict) or not isinstance(body.get("pieces", []), list) or len(body.get("pieces", [])) > MAX_PIECES:
        raise ValueError("invalid_room")
    width, depth = _number(body.get("width"), *ROOM_CM), _number(body.get("depth"), *ROOM_CM)
    pieces, seen = [], set()
    for piece in body.get("pieces", []):
        if not isinstance(piece, dict) or piece.get("kind") not in KINDS:
            raise ValueError("invalid_room")
        if not isinstance(piece.get("id"), str) or not OBJECT_ID.fullmatch(piece["id"]) or piece["id"] in seen:
            raise ValueError("invalid_room")
        seen.add(piece["id"])
        rotation = _number(piece.get("rotation", 0), -3600, 3600)
        clean = {"id": piece["id"], "kind": piece["kind"], "x": _number(piece.get("x"), 0, width),
                 "y": _number(piece.get("y"), 0, depth), "rotation": round(rotation % 360, 1)}
        if piece["kind"] in ("desk", "island"):
            if piece.get("tablets", 1) not in (1, 2) or isinstance(piece.get("tablets"), bool):
                raise ValueError("invalid_room")
            clean["tablets"] = piece.get("tablets", 1)
        if piece["kind"] == "island":
            if piece.get("desks") not in ISLAND_DESKS or isinstance(piece.get("desks"), bool):
                raise ValueError("invalid_room")
            clean["desks"] = piece["desks"]
        pieces.append(clean)
    return {"width": width, "depth": depth, "pieces": pieces}


def validate_placements(placements, geometry):
    """Each ID on one existing spot, and at most one ID per spot."""
    if not isinstance(placements, dict) or len(placements) > MAX_PLACEMENTS:
        raise ValueError("invalid_placement")
    spots, taken, clean = set(spot_ids(geometry)), set(), {}
    for participant, spot in placements.items():
        if spot not in spots or spot in taken:
            raise ValueError("invalid_placement")
        taken.add(spot)
        clean[_participant(participant)] = spot
    return clean


class Rooms:
    def __init__(self, directory):
        self.path = Path(directory) / "rooms.sqlite3"
        with closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS room_plans (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL,
                    updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS session_rooms (
                    session_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL, updated REAL NOT NULL);
            """)
        self.path.chmod(0o600)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    # -- Rooms --------------------------------------------------------------------------------------------------

    @staticmethod
    def _summary(item, name, revision, updated, body):
        return {"id": item, "name": name, "revision": revision, "updated": updated, "width": body["width"],
                "depth": body["depth"], "desks": sum(len(desks(piece)) for piece in body["pieces"]),
                "spots": len(spot_ids(body))}

    def rooms(self):
        with closing(self._connect()) as db:
            rows = db.execute("SELECT id, name, revision, updated, body FROM room_plans ORDER BY name COLLATE NOCASE, id").fetchall()
        return [self._summary(item, name, revision, updated, json.loads(body)) for item, name, revision, updated, body in rows]

    def room(self, room_id):
        with closing(self._connect()) as db:
            row = db.execute("SELECT id, name, revision, body, updated FROM room_plans WHERE id=?", (room_id,)).fetchone()
        if row is None:
            return None
        return {"id": row[0], "name": row[1], "revision": row[2], "updated": row[4], **json.loads(row[3])}

    @staticmethod
    def _name(name):
        name = name.strip() if isinstance(name, str) else ""
        if not 0 < len(name) <= NAME_MAX or any(ord(char) < 32 for char in name):
            raise ValueError("invalid_room_name")
        return name

    def create_room(self, name, geometry):
        name, body = self._name(name), validate_geometry(geometry)
        room_id = secrets.token_hex(8)
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO room_plans VALUES (?, ?, 1, ?, ?)", (room_id, name, json.dumps(body), time.time()))
        return self.room(room_id)

    def update_room(self, room_id, expected_revision, geometry, name=None):
        body = validate_geometry(geometry)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision, name FROM room_plans WHERE id=?", (room_id,)).fetchone()
            if row is None:
                raise ValueError("room_missing")
            if row[0] != expected_revision:
                raise Conflict(self.room(room_id))
            db.execute("UPDATE room_plans SET name=?, revision=?, body=?, updated=? WHERE id=?",
                       (self._name(name) if name is not None else row[1], row[0] + 1, json.dumps(body), time.time(), room_id))
        return self.room(room_id)

    def delete_room(self, room_id, expected_revision):
        """Remove a room from the list. Sessions keep their own copy, so their maps stay as they were."""
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision FROM room_plans WHERE id=?", (room_id,)).fetchone()
            if row is None:
                raise ValueError("room_missing")
            if row[0] != expected_revision:
                raise Conflict(self.room(room_id))
            db.execute("DELETE FROM room_plans WHERE id=?", (room_id,))

    # -- Sessions' maps -----------------------------------------------------------------------------------------

    @staticmethod
    def _empty():
        return {"revision": 0, "updated": None, "width": None, "depth": None, "pieces": [], "placements": {},
                "room_id": None, "room_revision": None}

    def session_map(self, session_id):
        """The session's copy of its room and where each ID sits; no room yet at revision 0."""
        with closing(self._connect()) as db:
            row = db.execute("SELECT revision, body, updated FROM session_rooms WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            return self._empty()
        return {**self._empty(), "revision": row[0], "updated": row[2], **json.loads(row[1])}

    def _write(self, db, session_id, revision, body):
        db.execute("INSERT OR REPLACE INTO session_rooms VALUES (?, ?, ?, ?)", (session_id, revision, json.dumps(body), time.time()))

    def use_room(self, session_id, room_id, expected_revision):
        """Copy the room's current version into the session. IDs stay on their spots when those still exist."""
        room = self.room(room_id)
        if room is None:
            raise ValueError("room_missing")
        geometry = validate_geometry(room)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            current = self.session_map(session_id)
            if current["revision"] != expected_revision:
                raise Conflict(current)
            spots = set(spot_ids(geometry))
            kept = {participant: spot for participant, spot in current["placements"].items() if spot in spots}
            self._write(db, session_id, current["revision"] + 1,
                        {**geometry, "placements": kept, "room_id": room["id"], "room_revision": room["revision"]})
        return self.session_map(session_id)

    def place(self, session_id, participant, spot):
        """Put one ID on a spot, or off the map with no spot. A spot another ID took meanwhile is refused."""
        participant = _participant(participant)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            current = self.session_map(session_id)
            if current["revision"] == 0:
                raise ValueError("no_room")
            placements = {key: value for key, value in current["placements"].items() if key != participant}
            if spot:
                if spot not in spot_ids(current):
                    raise ValueError("spot_missing")
                if spot in placements.values():
                    raise Conflict(current)
                placements[participant] = spot
            body = {key: current[key] for key in ("width", "depth", "pieces", "room_id", "room_revision")}
            body["placements"] = validate_placements(placements, current)
            self._write(db, session_id, current["revision"] + 1, body)
        return self.session_map(session_id)
