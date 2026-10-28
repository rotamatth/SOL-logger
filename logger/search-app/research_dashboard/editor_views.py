"""Private, versioned researcher form recovery; never changes study assignments."""
import json
import sqlite3

from flask import g, jsonify, request

from .editor_recovery import EditorRecovery
from .state import identity


def recovery_key(session_id, participant=""):
    return f"questions:{session_id}:{participant}"


def register_editor_routes(dash):
    app, bp = dash.app, dash.bp

    def storage():
        # A failure of this optional editor store must not stop student collection.
        return EditorRecovery(app.config["RESEARCH_STATE_DIR"])

    @bp.get("/editor/logout-check")
    def editor_logout_check():
        """Warn before deleting this browser's copies, including those from closed tabs."""
        try:
            return jsonify(has_recovery=storage().has_copies(g.research_editor_owner, identity(g.research_hash)),
                           csrf=g.research_auth["csrf"])
        except (ValueError, OSError, RuntimeError, sqlite3.Error):
            return jsonify(error="recovery_unavailable", csrf=g.research_auth["csrf"]), 503

    @bp.route("/editor/recovery", methods=["GET", "POST"])
    def editor_recovery():
        key = request.args.get("key", "") if request.method == "GET" else request.form.get("key", "")
        if not key.startswith(("questions:", "details:", "ids:")):
            return jsonify(error="invalid_recovery"), 400
        try:
            store = storage()
            owner, credential = g.research_editor_owner, identity(g.research_hash)
            if request.method == "GET":
                record = store.read(owner, credential, key)
            else:
                sequence = int(request.form["sequence"])
                action = request.form.get("action", "save")
                if action == "save":
                    fields = json.loads(request.form["fields"])
                    record = store.save(owner, credential, key, fields, sequence)
                elif action == "clear":
                    record = store.clear(owner, credential, key, sequence)
                else:
                    raise ValueError("invalid_recovery")
            return jsonify(recovery=record, csrf=g.research_auth["csrf"])
        except (ValueError, KeyError, TypeError) as exc:
            error = str(exc) if str(exc) in ("recovery_changed", "recovery_limit") else "invalid_recovery"
            return jsonify(error=error), 409 if error == "recovery_changed" else 400
        except (OSError, RuntimeError, sqlite3.Error):
            # Optional store: the editor keeps the text on the page and reports the failure.
            app.logger.warning("Private editor recovery is unavailable", exc_info=True)
            return jsonify(error="recovery_unavailable"), 503

    def clear_saved(key):
        # A later edit from another tab must not be deleted by an older save.
        raw = request.form.get("recovery_sequence")
        if not raw:
            return  # The form was submitted without the editor script.
        try:
            storage().clear(g.research_editor_owner, identity(g.research_hash), key, int(raw))
        except (ValueError, OSError, RuntimeError, sqlite3.Error):
            # The explicit save already succeeded; a recovery-store problem must not undo that.
            app.logger.warning("Could not clear private editor recovery after saving")

    def clear_owner():
        if not g.get("research_editor_owner"):
            return
        try:
            storage().clear_owner(g.research_editor_owner)
        except (ValueError, OSError, RuntimeError, sqlite3.Error):
            # Copies still expire after 8 hours and are bound to the deleted edit cookie.
            app.logger.warning("Could not remove private editor recovery copies at logout")

    dash.clear_editor_saved = clear_saved
    dash.clear_editor_owner = clear_owner
