"""The children's side of the classroom map: which tablet a request comes from, and what the server saw happen.

The tablet's registration travels in a cookie of its own (`sol_monitor`), apart from the run's browser session:
Salva clears that session, and the last page must still be heard from. Only an explicit reset retires it, or a
new ID chosen on the same tablet. Everything here is best effort: a monitoring failure never changes a page.
"""
from flask import g, request, session

from .monitor import SAVE_REASONS

COOKIE = "sol_monitor"
# The children's requests that save an answer. A refused or failed one leaves "Save not confirmed" on the map until
# the same tablet's next save goes through. The practice saves nothing, so its routes are not here.
SAVE_ENDPOINTS = frozenset(("first_answer", "first_answer_draft", "first_answer_change", "final_answer_draft",
                            "recap_draft", "recap_save", "recap_finish", "end"))


class Monitoring:
    def __init__(self, app, monitor, is_test_participant):
        self.app, self.monitor, self.is_test = app, monitor, is_test_participant
        app.after_request(self._after)

    def token(self):
        if g.get("monitor_clear"):
            return None
        return g.get("monitor_token") or request.cookies.get(COOKIE)

    def attach(self, study_session_id, participant_id):
        """From now on this tablet is `participant_id` in `study_session_id`; a different earlier ID is retired."""
        if self.is_test(participant_id):
            return
        token = self.monitor.register(study_session_id, participant_id, request.cookies.get(COOKIE))
        if token:
            g.monitor_token, g.monitor_clear = token, False

    def detach(self):
        """An adult reset the tablet: its circle stops being updated, and the next ID starts afresh."""
        self.monitor.retire(request.cookies.get(COOKIE))
        g.monitor_clear, g.monitor_token = True, None

    def beat(self, report):
        return self.monitor.beat(self.token(), report)

    def search(self, ok):
        """The engine answered (results or none: both are fine) or refused."""
        self.monitor.server_incident(self.token(), "search_failed", not ok)

    def _run_registration(self):
        """A run under way keeps its tablet registered: after a reload, a resumed run, or a cookie the browser lost."""
        study_session = session.get("study_session") if isinstance(session.get("study_session"), dict) else {}
        participant_id, session_id = session.get("user_id"), study_session.get("id")
        if (not isinstance(participant_id, str) or not isinstance(session_id, str) or session.get("assignment_source") == "test"
                or self.is_test(participant_id)):
            return
        current = self.monitor.active(self.token())
        if not current or current["study_session_id"] != session_id or current["participant_id"] != participant_id:
            self.attach(session_id, participant_id)

    def _after(self, response):
        if request.path.startswith(("/dashboard", "/static")):
            return response
        try:
            if request.method == "POST" and request.endpoint in SAVE_ENDPOINTS:
                if response.status_code >= 500 or response.status_code == 409:
                    reason = "conflict" if response.status_code == 409 else "server"
                    self.monitor.server_incident(self.token(), "save_failed", True, reason if reason in SAVE_REASONS else None)
                elif response.status_code < 400:
                    self.monitor.server_incident(self.token(), "save_failed", False)
            if not g.get("monitor_clear"):
                self._run_registration()
        except Exception:  # noqa: BLE001 - monitoring must never break a child's page.
            self.app.logger.warning("Classroom monitoring skipped a request", exc_info=True)
        secure = self.app.config.get("SESSION_COOKIE_SECURE", False)
        if g.get("monitor_clear"):
            response.delete_cookie(COOKIE, path="/", httponly=True, samesite="Lax", secure=secure)
        elif g.get("monitor_token") and g.monitor_token != request.cookies.get(COOKIE):
            # A browser-session cookie, like the run's own: closing the browser forgets which tablet this is.
            response.set_cookie(COOKIE, g.monitor_token, path="/", httponly=True, samesite="Lax", secure=secure)
        return response
