"""The live view's classroom map: its layout (rooms and the session's own copy) and each tablet's health.

Reads are GETs and never write. Every change is an explicit POST with the dashboard's CSRF token and the revision
it was based on; a stale one gets 409 and the current version back. The health feed is light enough to ask every
two seconds: the roster from the settings and one small database, no log, index or file system scan.
"""
from datetime import datetime
import json
import time

from flask import g, jsonify, request, send_file

from .live import ZURICH
from .monitor import BEAT_SECONDS, LATE_AFTER, LOST_AFTER
from .preparation_views import preparation_session
from .room_maps import CANVAS, IMAGE_BYTES, Conflict
from .study_config import roster

def _revision():
    try:
        return int(request.form.get("revision", ""))
    except ValueError:
        return None


def register_map_routes(dash, rooms, monitor):
    bp, state = dash.bp, dash.state

    def study_session(session_id):
        return preparation_session(state.settings(), session_id)

    def problem(key, code=400, **values):
        return jsonify(error=key, **values), code

    def map_reply(session_map):
        return jsonify(map=session_map, rooms=rooms.rooms(), canvas=CANVAS, csrf=g.research_auth["csrf"])

    @bp.get("/sessions/<session_id>/map.json")
    def session_map_data(session_id):
        study_session(session_id)
        return map_reply(rooms.session_map(session_id))

    @bp.post("/sessions/<session_id>/map")
    def session_map_save(session_id):
        study_session(session_id)
        revision = _revision()
        try:
            body = json.loads(request.form.get("map", ""))
        except ValueError:
            return problem("invalid_map")
        if revision is None:
            return problem("invalid_map")
        try:
            return map_reply(rooms.save_session_map(session_id, revision, body))
        except Conflict as conflict:
            return problem("map_changed", 409, map=conflict.current)
        except ValueError as error:
            return problem(str(error))

    @bp.post("/sessions/<session_id>/map/room")
    def session_map_room(session_id):
        """Start this session's map from a copy of a room: its tables and plan, none of another class's IDs."""
        study_session(session_id)
        revision = _revision()
        if revision is None:
            return problem("invalid_map")
        try:
            return map_reply(rooms.start_from_room(session_id, request.form.get("room_id", ""), revision))
        except Conflict as conflict:
            return problem("map_changed", 409, map=conflict.current)
        except ValueError as error:
            return problem(str(error))

    @bp.post("/sessions/<session_id>/map/image")
    def session_map_image(session_id):
        """A floor plan under the tables. The picture is checked by its content, never by its name."""
        study_session(session_id)
        upload = request.files.get("image")
        try:
            name = rooms.save_image(upload.read(IMAGE_BYTES + 1) if upload else b"")
        except ValueError as error:
            return problem(str(error))
        return jsonify(image=name)

    @bp.post("/rooms")
    def room_create():
        """A new reusable room from this session's tables and plan. IDs are not copied."""
        source = rooms.session_map(study_session(request.form.get("session_id", ""))["id"])
        try:
            room = rooms.create_room(request.form.get("name"), source)
        except ValueError as error:
            return problem(str(error))
        return jsonify(room=room, rooms=rooms.rooms())

    @bp.post("/rooms/<room_id>")
    def room_update(room_id):
        """Explicitly replace a room's geometry with this session's: the only way a session changes a room."""
        source = rooms.session_map(study_session(request.form.get("session_id", ""))["id"])
        revision = _revision()
        if revision is None:
            return problem("invalid_map")
        try:
            room = rooms.update_room(room_id, revision, source, name=request.form.get("name") or None)
        except Conflict as conflict:
            return problem("room_changed", 409, room=conflict.current)
        except ValueError as error:
            return problem(str(error))
        return jsonify(room=room, rooms=rooms.rooms())

    @bp.get("/room-images/<name>")
    def room_image(name):
        found = rooms.image_file(name)
        if found is None:
            return problem("not_found", 404)
        return send_file(found[0], mimetype=found[1], max_age=0)

    @bp.get("/sessions/<session_id>/health.json")
    def session_health(session_id):
        """Each tablet's colour and reasons now, by the server's clock, for the session's IDs and any other registered."""
        settings = state.settings()
        chosen = preparation_session(settings, session_id)
        now = time.time()
        ids = sorted(uid for uid, grade in roster(settings, chosen.get("school_year")).items() if grade == chosen["grade"])
        tablets = monitor.health(session_id, now=now)
        return jsonify(available=tablets is not None, now=now, clock=datetime.fromtimestamp(now, ZURICH).strftime("%H:%M:%S"),
                       roster=ids, tablets=tablets or {},
                       timing={"beat": BEAT_SECONDS, "late": LATE_AFTER, "lost": LOST_AFTER})
