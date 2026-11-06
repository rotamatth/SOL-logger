"""Shared context for the researcher dashboard routes.

Every route module receives one :class:`Dashboard`. It owns the blueprint, the
authoritative study state, the reporting index and the small helpers that all
pages share (URL building, rendering and error responses).
"""
from urllib.parse import unquote, urlsplit

from flask import g, jsonify, render_template, request, url_for

from .collection import publish_pending_runs

PREFIX = "/dashboard"
COOKIE = "sol_research"
EDITOR_COOKIE = "sol_research_editor"

# Endpoints whose failures are answered as JSON for the browser scripts.
JSON_ENDPOINTS = ("research.editor_recovery", "research.session_check", "research.editor_logout_check",
                  "research.session_live_data")


def is_dashboard_path(path):
    return path == PREFIX or path.startswith(PREFIX + "/")


def wants_json():
    return (request.path.endswith("/events.json") or request.endpoint in JSON_ENDPOINTS
            or request.endpoint == "research.logout" and request.accept_mimetypes.best == "application/json")


def safe_research_next(value):
    """Accept only a local dashboard path as a post-login destination."""
    if not isinstance(value, str) or len(value) > 8192 or any(ord(c) < 32 for c in value):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if (parsed.scheme or parsed.netloc or not parsed.path.startswith(PREFIX + "/")
            or parsed.path in (PREFIX + "/login", PREFIX + "/logout") or "\\" in value):
        return None
    # A browser resolves dot segments, encoded ones too, so these would leave the dashboard.
    path = unquote(parsed.path)
    if "\\" in path or "//" in path or {".", ".."} & set(path.split("/")):
        return None
    # Rebuilt from our own prefix rather than returned as received, so it can only be a dashboard path.
    return PREFIX + parsed.path[len(PREFIX):] + (f"?{parsed.query}" if parsed.query else "")


class Dashboard:
    """Dependencies and helpers shared by the dashboard route modules."""

    def __init__(self, app, blueprint, state, index):
        self.app = app
        self.bp = blueprint
        self.state = state
        self.index = index
        # Set while registering the route modules.
        self.clear_editor_saved = None
        self.clear_editor_owner = None

    def password_hash(self):
        """The configured hash, or "" so that a missing or plaintext value fails closed."""
        filename = self.app.config["RESEARCH_PASSWORD_HASH_FILE"]
        try:
            if filename:
                with open(filename, encoding="utf-8") as source:
                    value = source.read(4096).strip()
            else:
                value = self.app.config["RESEARCH_PASSWORD_HASH"]
        except (OSError, UnicodeError):
            return ""
        if not isinstance(value, str) or value.count("$") != 2 or not value.startswith(("scrypt:", "pbkdf2:")):
            return ""
        return value

    def u(self, endpoint, **values):
        """URL for a dashboard endpoint that keeps the language and workflow context."""
        values.setdefault("lang", g.get("research_lang", "en"))
        if endpoint in ("session_questions", "enrollment_page") and request.args.get("prepare_session"):
            values.setdefault("prepare_session", request.args["prepare_session"])
        if endpoint == "settings_page":
            source_grade = request.args.get("grade")
            if source_grade and values.get("grade", source_grade) == source_grade:
                values.setdefault("grade", source_grade)
                values.setdefault("year", request.args.get("year") or request.args.get("school_year"))
                values.setdefault("session", request.args.get("session"))
        return url_for("research." + endpoint, **values)

    @staticmethod
    def page(name, **values):
        # Student pages have their own value under this name, empty outside a run: never let it reach these templates.
        values.setdefault("study_context", {})
        return render_template("research/" + name + ".html", **values)

    def problem(self, key, code):
        if wants_json():
            return jsonify(error=key), code
        return self.page("error", message=key), code

    def data(self):
        """Publish pending run snapshots, refresh the index and return (settings, run summaries)."""
        publish_pending_runs(self.app.config["RESEARCH_LOG_DIR"], self.state)
        self.index.refresh()
        settings = self.state.settings()
        return settings, self.index.summaries(settings)
