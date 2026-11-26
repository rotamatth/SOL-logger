"""Classroom layouts for the live view's map: reusable rooms, and each session's own copy with its IDs placed.

A room is geometry only (tables and an optional floor plan), named and shared by every researcher, so the
morning's and the afternoon's classrooms can each be reused and edited. A session's map starts as a copy of a
room: moving its tables or placing its IDs changes that session only, until a researcher explicitly saves the
geometry back into a room. Rooms never carry participant IDs, so reusing one never brings another class along.

Placing an ID is a display choice for the map, never an admission or attendance rule. Every save carries the
revision it was based on, so two open dashboards cannot silently overwrite each other. Coordinates are in a
fixed logical canvas, so a layout looks the same at any window size. Nothing here is study data.
"""
from contextlib import closing
from io import BytesIO
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time

from PIL import Image, UnidentifiedImageError

CANVAS = (1000, 700)
MAX_TABLES = 80
MAX_PLACEMENTS = 200
TABLE_SIZE = ((20, 600), (20, 500))
NAME_MAX = 80
IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_PIXELS = 25_000_000
IMAGE_FORMATS = {"PNG": ("png", "image/png"), "JPEG": ("jpg", "image/jpeg"), "WEBP": ("webp", "image/webp")}
IMAGE_NAME = re.compile(r"[0-9a-f]{32}\.(png|jpg|webp)")
OBJECT_ID = re.compile(r"[A-Za-z0-9_-]{1,40}")


class Conflict(Exception):
    """Someone saved since this copy was loaded: the caller gets the current one back."""

    def __init__(self, current):
        super().__init__("changed")
        self.current = current


def _number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError("invalid_map")
    return round(float(value), 1)


def _participant(value):
    if not isinstance(value, str) or not 0 < len(value) <= 40 or any(ord(char) < 32 for char in value):
        raise ValueError("invalid_map")
    return value


def validate_geometry(body, images):
    """Tables and the floor plan, normalized. Raises ValueError("invalid_map")."""
    if not isinstance(body, dict) or not isinstance(body.get("tables", []), list) or len(body.get("tables", [])) > MAX_TABLES:
        raise ValueError("invalid_map")
    tables, seen = [], set()
    for table in body.get("tables", []):
        if not isinstance(table, dict) or not isinstance(table.get("id"), str) or not OBJECT_ID.fullmatch(table["id"]):
            raise ValueError("invalid_map")
        if table["id"] in seen:
            raise ValueError("invalid_map")
        seen.add(table["id"])
        rotation = table.get("rotation", 0)
        if isinstance(rotation, bool) or not isinstance(rotation, (int, float)):
            raise ValueError("invalid_map")
        tables.append({"id": table["id"], "x": _number(table.get("x"), 0, CANVAS[0]), "y": _number(table.get("y"), 0, CANVAS[1]),
                       "w": _number(table.get("w"), *TABLE_SIZE[0]), "h": _number(table.get("h"), *TABLE_SIZE[1]),
                       "rotation": int(rotation) % 360})
    image = body.get("image")
    if image is not None and not (isinstance(image, str) and IMAGE_NAME.fullmatch(image) and (images / image).is_file()):
        raise ValueError("invalid_map")
    return {"tables": tables, "image": image}


def validate_session_map(body, images):
    """A session's map: its geometry and where each ID sits, on a table or anywhere on the canvas."""
    geometry = validate_geometry(body, images)
    placements = body.get("placements", {})
    if not isinstance(placements, dict) or len(placements) > MAX_PLACEMENTS:
        raise ValueError("invalid_map")
    tables = {table["id"] for table in geometry["tables"]}
    placed = {}
    for participant, place in placements.items():
        participant = _participant(participant)
        if isinstance(place, dict) and set(place) == {"table"} and place["table"] in tables:
            placed[participant] = {"table": place["table"]}
        elif isinstance(place, dict) and set(place) == {"x", "y"}:
            placed[participant] = {"x": _number(place["x"], 0, CANVAS[0]), "y": _number(place["y"], 0, CANVAS[1])}
        else:
            raise ValueError("invalid_map")
    room = body.get("room_id")
    if room is not None and not (isinstance(room, str) and OBJECT_ID.fullmatch(room)):
        raise ValueError("invalid_map")
    return {**geometry, "placements": placed, "room_id": room}


class RoomMaps:
    def __init__(self, directory):
        self.path = Path(directory) / "rooms.sqlite3"
        self.images = Path(directory) / "room-images"
        self.images.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS rooms (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL,
                    updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS session_maps (
                    session_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL, updated REAL NOT NULL);
            """)
        self.path.chmod(0o600)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    # -- Rooms --------------------------------------------------------------------------------------------------

    def rooms(self):
        with closing(self._connect()) as db:
            rows = db.execute("SELECT id, name, revision, updated FROM rooms ORDER BY name COLLATE NOCASE, id").fetchall()
        return [{"id": item, "name": name, "revision": revision, "updated": updated} for item, name, revision, updated in rows]

    def room(self, room_id):
        with closing(self._connect()) as db:
            row = db.execute("SELECT id, name, revision, body, updated FROM rooms WHERE id=?", (room_id,)).fetchone()
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
        name, body = self._name(name), validate_geometry(geometry, self.images)
        room_id = secrets.token_hex(8)
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO rooms VALUES (?, ?, 1, ?, ?)", (room_id, name, json.dumps(body), time.time()))
        return self.room(room_id)

    def update_room(self, room_id, expected_revision, geometry, name=None):
        body = validate_geometry(geometry, self.images)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision, name FROM rooms WHERE id=?", (room_id,)).fetchone()
            if row is None:
                raise ValueError("room_missing")
            if row[0] != expected_revision:
                raise Conflict(self.room(room_id))
            db.execute("UPDATE rooms SET name=?, revision=?, body=?, updated=? WHERE id=?",
                       (self._name(name) if name is not None else row[1], row[0] + 1, json.dumps(body), time.time(), room_id))
        return self.room(room_id)

    # -- Sessions' maps -----------------------------------------------------------------------------------------

    def session_map(self, session_id):
        """The session's map, or an empty canvas at revision 0 before the first save."""
        with closing(self._connect()) as db:
            row = db.execute("SELECT revision, body, updated FROM session_maps WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            return {"revision": 0, "updated": None, "tables": [], "image": None, "placements": {}, "room_id": None}
        return {"revision": row[0], "updated": row[2], **json.loads(row[1])}

    def save_session_map(self, session_id, expected_revision, body):
        body = validate_session_map(body, self.images)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision FROM session_maps WHERE session_id=?", (session_id,)).fetchone()
            current = row[0] if row else 0
            if current != expected_revision:
                raise Conflict(self.session_map(session_id))
            db.execute("INSERT OR REPLACE INTO session_maps VALUES (?, ?, ?, ?)",
                       (session_id, current + 1, json.dumps(body), time.time()))
        return self.session_map(session_id)

    def start_from_room(self, session_id, room_id, expected_revision):
        """A copy of the room's geometry for this session, with no ID placed: another class's places never come along."""
        room = self.room(room_id)
        if room is None:
            raise ValueError("room_missing")
        return self.save_session_map(session_id, expected_revision,
                                     {"tables": room["tables"], "image": room["image"], "placements": {}, "room_id": room_id})

    # -- Floor plans --------------------------------------------------------------------------------------------

    def save_image(self, data):
        """Keep an uploaded floor plan if it really is a PNG, JPEG or WebP picture of a sane size. Returns its name."""
        if not isinstance(data, bytes) or not 0 < len(data) <= IMAGE_BYTES:
            raise ValueError("invalid_image")
        try:
            with Image.open(BytesIO(data)) as probe:
                probe.verify()
            with Image.open(BytesIO(data)) as picture:
                kind, width, height = picture.format, picture.width, picture.height
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
            raise ValueError("invalid_image") from error
        if kind not in IMAGE_FORMATS or width * height > IMAGE_PIXELS:
            raise ValueError("invalid_image")
        name = f"{secrets.token_hex(16)}.{IMAGE_FORMATS[kind][0]}"
        path = self.images / name
        path.write_bytes(data)
        path.chmod(0o600)
        return name

    def image_file(self, name):
        """(path, media type) of a stored floor plan, or None."""
        if not (isinstance(name, str) and IMAGE_NAME.fullmatch(name)):
            return None
        path = self.images / name
        media = {extension: media for extension, media in IMAGE_FORMATS.values()}[name.rsplit(".", 1)[1]]
        return (path, media) if path.is_file() else None
