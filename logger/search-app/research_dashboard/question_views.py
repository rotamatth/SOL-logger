"""Question editor for one study session (shared class questions or one participant).

The editor always works on a separate working copy. Only "Approve questions"
publishes it; children keep receiving the approved version until then. See
``question_versions`` for the stored fields.
"""
from copy import deepcopy
import json
import secrets

from flask import abort, g, redirect, request
from itsdangerous import BadSignature, URLSafeSerializer

from .editor_views import recovery_key
from .question_versions import (discard_question_draft, publish_questions, published_questions, question_draft,
                                remove_individual_questions, save_question_draft, working_questions)
from .settings_views import session_review_url
from .state import SETTING_FIELDS, roster
from .study_config import question_choices, question_library, session_readiness

SAVE_ACTIONS = ("save_questions", "save_draft", "save_draft_return", "approve_questions")
VISIBLE_ERRORS = {"settings_changed", "questions_incomplete", "questions_unapproved",
                  "question_session_removed", "question_participant_moved", "duplicate_question_id"}


class LibraryChoices:
    """Previous questions offered for reuse, by full set and by unique wording."""

    def __init__(self, library):
        self.library = library
        self.unique = question_choices(library)
        self._unique_by_id = {item["id"]: item for item in self.unique}
        self._questions = {f"{item['id']}:{slot}": question
                           for item in library for slot, question in enumerate(item["question_set"]["questions"])}
        self._questions.update({item["id"]: item["question_data"] for item in self.unique})

    def question(self, selected_id, draft_metadata):
        selected = self._questions.get(selected_id)
        if selected is None:
            raise ValueError("invalid_question_set")
        if selected_id in self._unique_by_id:
            # A chosen full set supplies an explicit experiment condition.
            # Reuse that source when it is unambiguous.
            wanted = json.dumps(draft_metadata, sort_keys=True)
            matching = [source["question_data"] for source in self._unique_by_id[selected_id]["sources"]
                        if json.dumps(source["set_metadata"], sort_keys=True) == wanted]
            if matching and len({json.dumps(item, sort_keys=True) for item in matching}) == 1:
                selected = matching[0]
        return deepcopy(selected)

    def question_set(self, set_id):
        selected = next((item for item in self.library if item["id"] == set_id), None)
        if selected is None:
            raise ValueError("invalid_question_set")
        draft = deepcopy(selected["question_set"])
        draft["approved"] = False
        return draft


def edited_questions(draft, form, action, choices):
    """Merge the three submitted rows into the draft's questions, keeping IDs and metadata."""
    old_questions = draft.get("questions", [])
    questions = []
    for slot in range(3):
        old = old_questions[slot] if slot < len(old_questions) else {}
        question = deepcopy(old)
        question.update(id=old.get("id") or secrets.token_hex(12),
                        topic=form.get(f"topic_{slot}", "").strip(),
                        question=form.get(f"question_{slot}", "").replace("\r\n", "\n").replace("\r", "\n").strip())
        if action == "load_questions" and form.get(f"library_question_{slot}"):
            question = choices.question(form[f"library_question_{slot}"], draft.get("metadata", {}))
        questions.append(question)
    return questions


def register_question_routes(dash):
    bp, state = dash.bp, dash.state

    def save(settings, revision, session_id, change):
        """Apply ``change`` to a copy of the session and persist it at ``revision``."""
        updated = deepcopy({key: settings[key] for key in SETTING_FIELDS})
        change(next(s for s in updated["sessions"] if s["id"] == session_id))
        state.save_settings(updated, revision)

    @bp.route("/settings/questions/<session_id>", methods=["GET", "POST"])
    def session_questions(session_id):
        settings = state.settings()
        study_session = next((s for s in settings["sessions"] if s["id"] == session_id), None)
        if study_session is None:
            abort(404)
        from_preparation = bool(request.args.get("prepare_session"))
        if from_preparation and request.args["prepare_session"] != session_id:
            abort(404)
        uid = request.args.get("participant", "")
        if uid and uid not in settings["participant_registry"]:
            abort(404)
        # Removed elsewhere while the editor was open: a POST keeps the typed text
        # on screen with an explanation; it never saves. A new GET is still 404.
        unavailable = None
        if study_session.get("removed"):
            unavailable = "question_session_removed"
        elif uid and roster(settings, study_session.get("school_year")).get(uid) != study_session["grade"]:
            unavailable = "question_participant_moved"
        if unavailable and request.method != "POST":
            abort(404)
        exceptions = study_session.get("participant_questions", {})
        published = published_questions(study_session, uid)
        has_draft = question_draft(study_session, uid) is not None
        draft = working_questions(study_session, uid)
        choices = LibraryChoices(question_library(dash.app, settings))
        error = None
        revision = settings["revision"]
        signer = URLSafeSerializer(g.research_hash, salt="sol-question-draft")
        key = recovery_key(session_id, uid)

        def back_to_session(**values):
            year = study_session.get("school_year") or None
            if from_preparation:
                return redirect(dash.u("prepare_page", grade=study_session["grade"], year=year,
                                       session=session_id, _anchor="prepare-questions", **values))
            return redirect(dash.u("overview", grade=study_session["grade"], session=session_id, **values))

        if request.method == "POST":
            action = request.form.get("action", "save_questions")
            try:
                revision = int(request.form["revision"])
                if request.form.get("draft_token"):
                    payload = signer.loads(request.form["draft_token"])
                    if (payload.get("session_id") != session_id or payload.get("participant") != uid
                            or payload.get("revision") != revision):
                        raise ValueError("invalid_question_set")
                    # The signed draft may contain an earlier validation error.
                    # Apply corrections before validating the final assignment.
                    draft = deepcopy(payload["question_set"])
                questions = edited_questions(draft, request.form, action, choices)
                # Only an explicit approval publishes. The legacy save_questions
                # action publishes only when it explicitly posts approved=1.
                publish = action == "approve_questions" or (
                    action == "save_questions" and request.form.get("approved") == "1")
                draft.update(questions=questions, theme=request.form.get("theme", "").strip(), approved=False)
                if unavailable:
                    raise ValueError(unavailable)
                if revision != settings["revision"]:
                    raise ValueError("settings_changed")
                if action == "load_set":
                    draft = choices.question_set(request.form.get("library_set"))
                elif action == "load_questions":
                    pass  # Preview only: the page shows the merged, unsaved draft.
                elif action == "remove_exception" and uid:
                    save(settings, revision, session_id, lambda target: remove_individual_questions(target, uid))
                    dash.clear_editor_saved(key)
                    return redirect(dash.u("session_questions", session_id=session_id, saved="1"))
                elif action == "discard_draft":
                    save(settings, revision, session_id, lambda target: discard_question_draft(target, uid))
                    dash.clear_editor_saved(key)
                    return redirect(dash.u("session_questions", session_id=session_id, participant=uid or None,
                                           discarded="1"))
                elif action in SAVE_ACTIONS:
                    store = publish_questions if publish else save_question_draft
                    save(settings, revision, session_id, lambda target: store(target, draft, uid))
                    dash.clear_editor_saved(key)
                    if action == "save_draft_return":
                        return back_to_session(draft_saved="1")
                    if action == "approve_questions" and from_preparation:
                        return back_to_session(approved="1")
                    return redirect(dash.u("session_questions", session_id=session_id, participant=uid or None,
                                           saved="1"))
                else:
                    raise ValueError("invalid_question_set")
            except (ValueError, KeyError, BadSignature) as exc:
                error = str(exc) if str(exc) in VISIBLE_ERRORS else "invalid_question_set"
        review_url = None
        if error == "question_session_removed":
            review_url = session_review_url(dash, settings, study_session)
        elif error == "question_participant_moved":
            review_url = dash.u("enrollment_page", year=study_session.get("school_year") or None, q=uid)
        return dash.page("session_questions", settings=settings, study_session=study_session,
                         from_preparation=from_preparation, review_url=review_url,
                         research_area="prepare" if from_preparation else "settings",
                         study_context=study_session,
                         participant=uid, draft=draft, has_exception=uid in exceptions,
                         published=published, has_draft=has_draft, recovery_key=key,
                         readiness=session_readiness(settings, study_session), library=choices.library,
                         unique_questions=choices.unique,
                         unsaved_preview=request.method == "POST" and not error,
                         draft_token=signer.dumps({"session_id": session_id, "participant": uid,
                                                  "revision": revision, "question_set": draft}),
                         form_revision=revision, error=error), 400 if error else 200
