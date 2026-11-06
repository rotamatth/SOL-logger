"""The live view of a session: the page and the data it refreshes itself with."""
from datetime import datetime
import json

from flask import jsonify, render_template

from .live import ZURICH, session_progress
from .preparation_views import preparation_session, zurich_today
from .state import identity


def _digest(value):
    return identity(json.dumps(value, sort_keys=True, ensure_ascii=False))[:16]


def register_live_routes(dash):
    bp, state, page = dash.bp, dash.state, dash.page
    # Per worker. Files are read again when their size or modification time changes.
    cache = {}

    def snapshot(session_id):
        settings = state.settings()
        study_session = preparation_session(settings, session_id)
        progress = session_progress(state, settings, dash.index.roots["v2"], study_session, cache)
        for child in progress["children"]:
            child["digest"] = _digest(child)
        return {"settings": settings, "study_session": study_session, **progress,
                "updated": datetime.now(ZURICH).strftime("%H:%M:%S"), "running": study_session.get("date") == zurich_today()}

    @bp.get("/sessions/<session_id>/live")
    def session_live(session_id):
        data = snapshot(session_id)
        study_session = data["study_session"]
        return page("session_live", research_area="sessions", **data,
                    study_context={"grade": study_session["grade"], "school_year": study_session.get("school_year") or None,
                                   "id": study_session["id"]})

    @bp.get("/sessions/<session_id>/live.json")
    def session_live_data(session_id):
        data = snapshot(session_id)
        return jsonify(
            updated=data["updated"],
            totals=render_template("research/session_live_totals.html", totals=data["totals"]),
            questions=render_template("research/session_live_questions.html", questions=data["questions"]),
            rows=[{"id": child["id"], "digest": child["digest"],
                   "html": render_template("research/session_live_row.html", child=child, study_session=data["study_session"])}
                  for child in data["children"]])
