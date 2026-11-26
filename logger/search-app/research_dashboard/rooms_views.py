"""The Rooms page: classrooms drawn to scale, shared by every researcher and reused by sessions' live maps.

Reads are GETs and never write. Every change is an explicit POST with the dashboard's CSRF token; changing or
deleting a room carries the revision it was based on, and a stale one gets 409 with the current version back.
"""
import json

from flask import g, jsonify, request

from .i18n import translate
from .rooms import (DEFAULT_ROOM_CM, DESK_CM, GRID_CM, ISLAND_DESKS, LANDMARKS_CM, ROOM_CM, SEAT_CM, SNAP_CM,
                    Conflict)
from .rooms_i18n import ROOMS_TEXT


def room_config():
    """The sizes the drawings need, from the one place that defines them (rooms.py)."""
    return {"grid": GRID_CM, "snap": SNAP_CM, "room": ROOM_CM, "default": DEFAULT_ROOM_CM, "desk": DESK_CM,
            "seat": SEAT_CM, "islands": {str(count): spots for count, spots in ISLAND_DESKS.items()},
            "landmarks": LANDMARKS_CM}


def room_strings():
    language = g.get("research_lang", "en")
    return {key: translate(key, language) for key in ROOMS_TEXT}


def _revision():
    try:
        return int(request.form.get("revision", ""))
    except ValueError:
        return None


def _geometry():
    try:
        return json.loads(request.form.get("room", ""))
    except ValueError:
        return None


def register_room_routes(dash, rooms):
    bp = dash.bp

    def problem(key, code=400, **values):
        return jsonify(error=key, **values), code

    def reply(room=None):
        return jsonify(room=room, rooms=rooms.rooms(), csrf=g.research_auth["csrf"])

    @bp.get("/classrooms")
    def rooms_page():
        return dash.page("rooms", research_area="rooms", room_config=room_config(), room_strings=room_strings())

    @bp.get("/classrooms.json")
    def rooms_data():
        return reply()

    @bp.get("/classrooms/<room_id>.json")
    def room_data(room_id):
        room = rooms.room(room_id)
        return reply(room) if room else problem("room_missing", 404)

    @bp.post("/classrooms")
    def room_new():
        try:
            return reply(rooms.create_room(request.form.get("name"), _geometry()))
        except ValueError as error:
            return problem(str(error))

    @bp.post("/classrooms/<room_id>")
    def room_save(room_id):
        revision = _revision()
        if revision is None:
            return problem("invalid_room")
        try:
            return reply(rooms.update_room(room_id, revision, _geometry(), name=request.form.get("name")))
        except Conflict as conflict:
            return problem("room_changed", 409, room=conflict.current)
        except ValueError as error:
            return problem(str(error), 404 if str(error) == "room_missing" else 400)

    @bp.post("/classrooms/<room_id>/delete")
    def room_remove(room_id):
        revision = _revision()
        if revision is None:
            return problem("invalid_room")
        try:
            rooms.delete_room(room_id, revision)
        except Conflict as conflict:
            return problem("room_changed", 409, room=conflict.current)
        except ValueError as error:
            return problem(str(error), 404)
        return reply()
