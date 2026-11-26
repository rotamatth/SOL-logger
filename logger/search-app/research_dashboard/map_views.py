"""The live view's classroom map: the session's copy of a room, where each ID sits, and each tablet's health.

Reads are GETs and never write. Choosing or refreshing the room and placing an ID are explicit POSTs with the
dashboard's CSRF token: the room copy carries the revision it was based on, and placing an ID is one change
applied to the current map (a spot someone else took meanwhile gets 409 and the current map back). The health
feed is light enough to ask every two seconds: the roster from the settings and one small database, no log,
index or file system scan.
"""
from datetime import datetime
import time

from flask import g, jsonify, request

from .live import ZURICH
from .monitor import BEAT_SECONDS, LATE_AFTER, LOST_AFTER
from .preparation_views import preparation_session
from .rooms import Conflict
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
        source = rooms.room(session_map["room_id"]) if session_map["room_id"] else None
        return jsonify(map=session_map, rooms=rooms.rooms(), csrf=g.research_auth["csrf"],
                       room_changed=bool(source and source["revision"] != session_map["room_revision"]))

    @bp.get("/sessions/<session_id>/classroom.json")
    def session_classroom_data(session_id):
        study_session(session_id)
        return map_reply(rooms.session_map(session_id))

    @bp.post("/sessions/<session_id>/classroom/room")
    def session_classroom_room(session_id):
        """Copy a room into this session, or bring its newer version in; IDs keep the spots that still exist."""
        study_session(session_id)
        revision = _revision()
        if revision is None:
            return problem("invalid_room")
        try:
            return map_reply(rooms.use_room(session_id, request.form.get("room_id", ""), revision))
        except Conflict as conflict:
            return problem("map_changed", 409, map=conflict.current)
        except ValueError as error:
            return problem(str(error))

    @bp.post("/sessions/<session_id>/classroom/place")
    def session_classroom_place(session_id):
        """One ID onto a spot, or off the map with an empty spot."""
        study_session(session_id)
        try:
            return map_reply(rooms.place(session_id, request.form.get("participant"), request.form.get("spot", "")))
        except Conflict as conflict:
            return problem("spot_taken", 409, map=conflict.current)
        except ValueError as error:
            return problem(str(error))

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
