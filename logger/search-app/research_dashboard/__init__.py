"""Private researcher dashboard, independent of participant session state.

``init_dashboard(app)`` wires the blueprint at ``/dashboard``. Each area lives in
its own module and registers its routes on a shared :class:`Dashboard` context:

* ``security``          login, CSRF, response headers, error pages
* ``template_context``  values available in every template
* ``preparation_views`` session preparation (the dashboard's start page)
* ``question_views``    question editor (working draft vs approved questions)
* ``editor_views``      private recovery of unsaved editor text
* ``enrollment_views``  permanent participants and yearly enrollment
* ``settings_views``    school year, session administration, ID ranges
* ``history_views``     data and history, runs, logs, trash
* ``export_views``      ZIP downloads
"""
import os

from flask import Blueprint

from .dashboard import COOKIE, EDITOR_COOKIE, PREFIX, Dashboard, safe_research_next
from .editor_views import register_editor_routes
from .enrollment_views import register_enrollment_routes
from .export_views import register_export_routes
from .history_data import display_session
from .history_views import register_history_routes
from .index import Index
from .preparation_views import register_preparation_routes
from .question_views import register_question_routes
from .security import register_security
from .settings_views import register_settings_routes
from .state import State
from .student_config import configure_students
from .template_context import register_template_context

__all__ = ["COOKIE", "EDITOR_COOKIE", "PREFIX", "display_session", "init_dashboard", "safe_research_next"]


def _configure(app):
    app.config.setdefault("RESEARCH_STATE_DIR", os.getenv("RESEARCH_STATE_DIR", "research_state"))
    app.config.setdefault("RESEARCH_LOG_DIR", os.getenv("SOL_LOG_DIR", "logs_v2"))
    app.config.setdefault("RESEARCH_LEGACY_LOG_DIR", os.getenv("RESEARCH_LEGACY_LOG_DIR", "logs"))
    app.config.setdefault("RESEARCH_PASSWORD_HASH_FILE", os.getenv("RESEARCH_PASSWORD_HASH_FILE", ""))
    app.config.setdefault("RESEARCH_PASSWORD_HASH", os.getenv("RESEARCH_PASSWORD_HASH", ""))
    app.config.setdefault("RESEARCH_COOKIE_SECURE", os.getenv("RESEARCH_COOKIE_SECURE", "0") == "1")


def init_dashboard(app):
    """Register the dashboard on ``app`` and return the authoritative study ``State``."""
    configure_students(app)
    _configure(app)
    state = State(app.config["RESEARCH_STATE_DIR"])
    index = Index(app.config["RESEARCH_STATE_DIR"], {
        "v2": app.config["RESEARCH_LOG_DIR"], "legacy": app.config["RESEARCH_LEGACY_LOG_DIR"]}, initialize=False)
    blueprint = Blueprint("research", __name__, template_folder="templates", static_folder="static",
                          url_prefix=PREFIX)
    dash = Dashboard(app, blueprint, state, index)
    app.extensions["research"] = {"state": state, "index": index,
                                  "credential_ready": lambda: bool(dash.password_hash())}
    register_security(dash)
    register_template_context(dash)
    register_editor_routes(dash)
    register_preparation_routes(dash)
    register_question_routes(dash)
    register_enrollment_routes(dash)
    register_settings_routes(dash)
    register_history_routes(dash)
    register_export_routes(dash)
    app.extensions["research"]["clear_editor_saved"] = dash.clear_editor_saved
    app.register_blueprint(blueprint)
    return state
