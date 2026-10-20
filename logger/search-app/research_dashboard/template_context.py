"""Values available in every dashboard template."""
from datetime import datetime
import json
from zoneinfo import ZoneInfo

from flask import g, request, url_for

from .dashboard import is_dashboard_path
from .editor_i18n import EDITOR_MESSAGE_KEYS
from .i18n import translate
from .participants import GRADES
from .question_versions import published_questions, question_draft, working_questions
from .study_config import question_set_problem

ZURICH = ZoneInfo("Europe/Zurich")


def question_status(assignment):
    if assignment is None:
        return "question_set_missing"
    return "questions_approved" if question_set_problem(assignment) is None else "questions_draft"


def question_view(study_session, uid=""):
    """Approved version, editor working copy and whether a separate draft exists."""
    return {"published": published_questions(study_session, uid),
            "working": working_questions(study_session, uid),
            "has_draft": question_draft(study_session, uid) is not None}


def navigation_context(state):
    """Grade/year/session carried by the global navigation; unknown sessions are dropped."""
    grade = request.args.get("grade", "4")
    year = request.args.get("year") or request.args.get("school_year") or None
    session_id = request.args.get("session")
    if session_id and g.get("research_auth") and g.research_auth["authenticated"]:
        selected = next((item for item in state.settings()["sessions"]
                         if item["id"] == session_id and not item.get("removed")), None)
        if not selected or selected["grade"] != grade or year and selected.get("school_year") != year:
            session_id = None
    else:
        session_id = None
    return {"grade": grade, "school_year": year, "id": session_id}


def language_url(lang):
    """The current page in another UI language."""
    endpoint = request.endpoint if request.endpoint and request.endpoint.startswith("research.") else "research.overview"
    values = {**request.args.to_dict(), **(request.view_args or {}), "lang": lang}
    if endpoint == "research.overview":
        values.pop("q", None)
        values.pop("status", None)
    return url_for(endpoint, **values)


def register_template_context(dash):
    @dash.app.context_processor
    def context():
        if not is_dashboard_path(request.path):
            return {}
        language = g.get("research_lang", "en")

        def when(timestamp):
            if not timestamp:
                return translate("unknown", language)
            return datetime.fromtimestamp(timestamp, ZURICH).strftime("%Y-%m-%d %H:%M:%S %Z")

        return {"t": lambda key: translate(key, language), "u": dash.u, "language": language,
                "question_status": question_status, "question_view": question_view,
                "language_url": language_url, "auth": g.get("research_auth"), "when": when,
                "grades": GRADES,
                "editor_messages": {key: translate(key, language) for key in EDITOR_MESSAGE_KEYS},
                "study_context": navigation_context(dash.state),
                "pretty": lambda value: json.dumps(value, ensure_ascii=False, indent=2)}
