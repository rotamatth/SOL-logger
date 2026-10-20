"""Authentication, CSRF, response headers and error pages for the dashboard.

The dashboard uses its own server-side session (SQLite), independent of the
participant Flask session. Every non-GET request needs the session-bound CSRF token.
"""
import secrets
import sqlite3

from flask import g, redirect, request
from werkzeug.security import check_password_hash

from .dashboard import COOKIE, EDITOR_COOKIE, PREFIX, is_dashboard_path, safe_research_next, wants_json
from .state import identity

CONTENT_SECURITY_POLICY = ("default-src 'self'; script-src 'self'; connect-src 'self'; style-src 'self'; "
                           "img-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
SESSION_SECONDS = 28800
# Question forms carry signed copies of bounded metadata objects.
LARGE_FORM_ENDPOINTS = ("research.session_questions", "research.editor_recovery")
LARGE_FORM_BYTES = 4 * 1024 * 1024
FORM_BYTES = 64 * 1024


def _editor_owner_cookie():
    candidate = request.cookies.get(EDITOR_COOKIE, "")
    if len(candidate) == 64 and all(c in "0123456789abcdef" for c in candidate):
        return candidate
    return None


def register_security(dash):
    app, bp, state = dash.app, dash.bp, dash.state

    @bp.errorhandler(OSError)
    def storage_unavailable(error):
        app.logger.error("Research storage unavailable", exc_info=error)
        return dash.problem("storage_unavailable", 503)

    @bp.errorhandler(sqlite3.Error)
    def storage_error(error):
        app.logger.error("Research database unavailable", exc_info=error)
        return dash.problem("storage_error", 503)

    @bp.errorhandler(404)
    def not_found(_):
        return dash.problem("not_found", 404)

    @bp.errorhandler(400)
    def bad_request(_):
        return dash.problem("invalid_settings", 400)

    @app.before_request
    def research_gate():
        if not is_dashboard_path(request.path):
            return None
        g.research_lang = "it" if request.args.get("lang") == "it" else "en"
        g.research_auth = None
        g.research_cookie = request.cookies.get(COOKIE, "")
        g.research_editor_owner = _editor_owner_cookie()
        request.max_content_length = LARGE_FORM_BYTES if request.endpoint in LARGE_FORM_ENDPOINTS else FORM_BYTES
        if request.endpoint == "research.static":
            return None
        g.research_hash = dash.password_hash()
        if not g.research_hash:
            return dash.problem("unconfigured", 503)
        g.research_auth = state.session(g.research_cookie, identity(g.research_hash))
        authenticated = bool(g.research_auth and g.research_auth["authenticated"])
        if request.endpoint != "research.login" and not authenticated:
            if wants_json():
                return dash.problem("login", 401)
            return redirect(dash.u("login", next=safe_research_next(request.full_path.rstrip("?"))))
        if authenticated and not g.research_editor_owner:
            g.research_editor_owner = secrets.token_hex(32)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            supplied = request.form.get("csrf", "")
            if not (g.research_auth and secrets.compare_digest(supplied, g.research_auth["csrf"])):
                return dash.problem("csrf_error", 400)
        return None

    @app.after_request
    def research_headers(response):
        if not is_dashboard_path(request.path):
            return response
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        for header in list(response.headers):
            if header[0].lower().startswith("access-control-"):
                del response.headers[header[0]]
        secure = app.config["RESEARCH_COOKIE_SECURE"]  # Read per request: it can be reconfigured.
        if g.get("research_new_token"):
            response.set_cookie(COOKIE, g.research_new_token, max_age=SESSION_SECONDS, path=PREFIX,
                                httponly=True, samesite="Lax", secure=secure)
        elif g.get("research_clear_cookie"):
            response.delete_cookie(COOKIE, path=PREFIX, httponly=True, samesite="Lax", secure=secure)
        if g.get("research_clear_editor"):
            response.delete_cookie(EDITOR_COOKIE, path=PREFIX, httponly=True, samesite="Strict", secure=secure)
        elif g.get("research_editor_owner") and g.get("research_auth") and g.research_auth["authenticated"]:
            response.set_cookie(EDITOR_COOKIE, g.research_editor_owner, max_age=SESSION_SECONDS, path=PREFIX,
                                httponly=True, samesite="Strict", secure=secure)
        return response

    @bp.route("/login", methods=["GET", "POST"])
    def login():
        destination = (safe_research_next(request.args.get("next") or request.form.get("next"))
                       or dash.u("prepare_page"))
        if g.research_auth and g.research_auth["authenticated"]:
            return redirect(destination)
        if request.method == "GET":
            if not g.research_auth:
                g.research_new_token, g.research_auth = state.new_session(identity(g.research_hash))
            return dash.page("login", error=None)
        attempt = state.reserve_login_attempt(request.remote_addr or "unknown")
        if not attempt:
            return dash.page("login", error="throttled"), 429, {"Retry-After": "900"}
        supplied = request.form.get("password", "")
        try:
            accepted = len(supplied) <= 1024 and check_password_hash(g.research_hash, supplied)
        except (ValueError, TypeError):
            accepted = False
        if not accepted:
            return dash.page("login", error="bad_password"), 401
        state.successful_attempt(attempt)
        state.revoke(g.research_cookie)
        g.research_new_token, g.research_auth = state.new_session(identity(g.research_hash), authenticated=True)
        return redirect(destination)

    @bp.post("/logout")
    def logout():
        dash.clear_editor_owner()
        state.revoke(g.research_cookie)
        g.research_clear_cookie = True
        g.research_clear_editor = True
        return redirect(dash.u("login"))
