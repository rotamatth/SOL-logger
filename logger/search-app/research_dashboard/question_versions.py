"""Separate researcher working copies from questions used for student admission.

The helpers operate on a caller-owned session dictionary. Persist the result
through State.save_settings so revision checks and the transaction remain the
single write boundary. Legacy unapproved assignments are deliberately retained;
reading them never publishes, moves or repairs their contents implicitly.
"""
from copy import deepcopy
import re

from .study_config import validate_question_set


def _participant(participant):
    if not isinstance(participant, str) or (participant and not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", participant)):
        raise ValueError("invalid_participant_questions")


def validate_question_drafts(study_session):
    """Validate optional working-copy fields without changing published data."""
    drafts = []
    if "question_draft" in study_session:
        drafts.append(study_session["question_draft"])
    if "participant_question_drafts" in study_session:
        individual = study_session["participant_question_drafts"]
        if (not isinstance(individual, dict) or len(individual) > 3000
                or any(not isinstance(uid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", uid)
                       for uid in individual)):
            raise ValueError("invalid_participant_questions")
        drafts.extend(individual.values())
    for draft in drafts:
        validate_question_set(draft)
        if draft.get("approved", False):
            raise ValueError("invalid_question_set")


def published_questions(study_session, participant=""):
    """Copy the exact published field, including legacy unapproved assignments.

    An absent individual assignment returns None rather than the shared set;
    student assignment resolution is owned by study_config.assignment_for.
    """
    _participant(participant)
    value = (study_session.get("participant_questions", {}).get(participant)
             if participant else study_session.get("question_set"))
    return deepcopy(value)


def question_draft(study_session, participant=""):
    """Copy an explicitly saved working draft, or None if none exists."""
    _participant(participant)
    value = (study_session.get("participant_question_drafts", {}).get(participant)
             if participant else study_session.get("question_draft"))
    return deepcopy(value)


def question_fields(study_session, participant=""):
    """Everything an editor save can replace: the approved version and the working copy."""
    _participant(participant)
    if participant:
        return (study_session.get("participant_questions", {}).get(participant),
                study_session.get("participant_question_drafts", {}).get(participant))
    return study_session.get("question_set"), study_session.get("question_draft")


def working_questions(study_session, participant=""):
    """Return the editor's isolated working copy without changing admission.

    A new individual working copy starts from the shared editor content. It is
    unapproved until explicitly published and does not create an assignment.
    """
    _participant(participant)
    draft = question_draft(study_session, participant)
    if draft is not None:
        return draft
    published = published_questions(study_session, participant)
    if published is not None:
        return published
    if participant:
        draft = working_questions(study_session)
        draft["approved"] = False
        return draft
    return {"questions": [], "approved": False, "theme": ""}


def save_question_draft(study_session, question_set, participant=""):
    """Save an incomplete working copy while leaving admission fields intact."""
    _participant(participant)
    draft = deepcopy(question_set)
    if not isinstance(draft, dict):
        raise ValueError("invalid_question_set")
    draft["approved"] = False
    validate_question_set(draft)
    if participant:
        study_session.setdefault("participant_question_drafts", {})[participant] = draft
    else:
        study_session["question_draft"] = draft
    return deepcopy(draft)


def discard_question_draft(study_session, participant=""):
    """Discard only the saved working copy; retain any published assignment."""
    _participant(participant)
    if not participant:
        return study_session.pop("question_draft", None) is not None
    drafts = study_session.get("participant_question_drafts", {})
    removed = drafts.pop(participant, None) is not None
    if not drafts:
        study_session.pop("participant_question_drafts", None)
    return removed


def publish_questions(study_session, question_set, participant=""):
    """Explicitly replace one admission assignment with complete approved text."""
    _participant(participant)
    published = deepcopy(question_set)
    if not isinstance(published, dict):
        raise ValueError("invalid_question_set")
    published["approved"] = True
    validate_question_set(published, require_ready=True)
    if participant:
        study_session.setdefault("participant_questions", {})[participant] = published
    else:
        study_session["question_set"] = published
    discard_question_draft(study_session, participant)
    return deepcopy(published)


def remove_individual_questions(study_session, participant):
    """Return an ID to shared questions, clearing both individual versions."""
    _participant(participant)
    if not participant:
        raise ValueError("invalid_participant_questions")
    published = study_session.get("participant_questions", {})
    removed = published.pop(participant, None) is not None
    if not published:
        study_session.pop("participant_questions", None)
    return discard_question_draft(study_session, participant) or removed
