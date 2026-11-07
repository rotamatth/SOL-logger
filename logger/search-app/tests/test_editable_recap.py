"""Participant recap preserves originals and saves a durable, retryable PDF."""
import sqlite3
import re
from datetime import datetime, timedelta

import pytest

from study_progress import AttemptKey, ProgressStore
from student_progress import ZONE
from .progress_helpers import confirm_first, final_event
from .test_connected_first_answer import begin, context, events
from .test_study_enrollment import schedule, student_modules  # noqa: F401


@pytest.fixture
def recap(student_modules):
    module = student_modules()
    settings = schedule(module)
    client = begin(module)
    editor = module.PROGRESS.store
    auth = complete_today(client)
    with client.session_transaction() as state:
        current = AttemptKey(state["progress_study_id"], "1", state["progress_session_id"])
    attempt_id = auth["attempt_id"]
    today = editor.get_attempt(current, attempt_id)

    def seed(number, name, complete):
        row = next(s for s in settings["sessions"] if s["grade"] == "4" and s["number"] == number)
        key = AttemptKey(current.study_id, current.participant_id, row["id"])
        tasks = [{"topic_id": str(topic), "question": f"{name} question {topic}"} for topic in (3, 1, 2)]
        snapshot = {**today["metadata"]["study_session_snapshot"], "id": row["id"],
                    "date": row["date"], "number": number}
        saved = editor.start_or_resume(key, tasks, {"study_session_snapshot": snapshot,
                                                     "technical_session_id": name})
        if complete:
            for question in (1, 2, 3):
                editor.submit_first_answer(key, saved["attempt_id"], question, "Prima", confidence=2)
                editor.submit_final_answer(key, saved["attempt_id"], question, f"{name} original {question}")
        return key, saved["attempt_id"]

    past, past_id = seed(1, "Past", True)
    _, future_id = seed(3, "Future", True)
    return module, client, current, past, past_id, future_id, auth


def complete_today(client):
    for number in (1, 2, 3):
        confirm_first(client)
        event = final_event(client, f"Today original {number}")
        assert client.post("/log_session", json={"session_id": event["sessionID"], "logs": [event]}).status_code == 200
        client.get("/next_task")
    with client.session_transaction() as state:
        return {"csrf_token": state["progress_csrf"], "attempt_id": state["progress_id"]}


def draft(client, auth, target, number, text, revision=0):
    return client.post("/recap/draft", json={**auth, "target_attempt_id": target, "number": number,
                                             "text": text, "revision": revision, "answer_revision": 0})


def draft_revisions(client):
    fields = re.findall(r'data-target="([^"]+)" data-number="(\d+)"\s+data-revision="(\d+)"',
                        client.get("/thank_you").text)
    return {f"{target}:{number}": int(revision) for target, number, revision in fields}


def commit(client, auth, action, revisions=None):
    return client.post(f"/recap/{action}", json={
        **auth, "draft_revisions": draft_revisions(client) if revisions is None else revisions,
    })


def test_recap_scope_hidden_drafts_revisions_and_originals(recap):
    module, client, current, past, past_id, future_id, auth = recap
    page = client.get("/thank_you")
    assert page.status_code == 200
    assert page.text.index("Past question 3") < page.text.index("Past question 1")
    assert "Future question" not in page.text and "Sessione 3" in page.text
    assert draft(client, auth, future_id, 1, "Illicit edit").status_code == 409
    assert draft(client, {**auth, "csrf_token": "bad"}, past_id, 1, "Illicit edit").status_code == 403
    assert draft(client, auth, past_id, 1, "Un'idea rivista").status_code == 200
    assert draft(client, auth, auth["attempt_id"], 3, "Hidden card").status_code == 200
    assert "Hidden card" in client.get("/thank_you").text
    assert commit(client, auth, "save-changes").status_code == 200
    assert commit(client, auth, "save-changes").status_code == 200
    store = ProgressStore(module.PROGRESS.store.path)
    assert store.get_attempt(past, past_id)["tasks"][0]["final_answer"]["text"] == "Past original 1"
    assert store.get_attempt(current, auth["attempt_id"])["tasks"][2]["final_answer"]["text"] == "Today original 3"
    revised = [event for event in events(module) if event["type"] == "RecapAnswerEdited"]
    assert len(revised) == 2
    assert {event["after_text"] for event in revised} == {"Un'idea rivista", "Hidden card"}
    assert all(event["attempt_id"] == auth["attempt_id"] for event in revised)
    assert sum(event["type"] == "TaskEnded" for event in events(module)) == 3


def test_pdf_failure_rolls_back_edits_and_finished_events(recap, monkeypatch, student_modules):
    module, client, _, _, past_id, _, auth = recap
    assert client.get("/recap/pdf").status_code == 404
    assert draft(client, auth, past_id, 1, "Keep this draft").status_code == 200
    revisions = draft_revisions(client)

    def fail(*_):
        raise sqlite3.OperationalError("synthetic PDF failure")

    with monkeypatch.context() as patch:
        patch.setattr(module.RECAP, "render_pdf", fail)
        assert commit(client, auth, "finish", revisions).status_code == 503
    assert "Keep this draft" in client.get("/thank_you").text
    assert not [event for event in events(module) if event["type"] in ("RecapAnswerEdited", "studySessionFinished")]
    assert commit(client, auth, "finish", revisions).status_code == 200
    pdf = client.get("/recap/pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF-")
    assert "attachment" in pdf.headers["Content-Disposition"]
    assert commit(client, auth, "finish", revisions).status_code == 200
    assert client.get("/recap/pdf").data == pdf.data
    worker = student_modules()
    same_browser = worker.app.test_client()
    cookie_name = module.app.config["SESSION_COOKIE_NAME"]
    same_browser.set_cookie(cookie_name, client.get_cookie(cookie_name).value)
    assert same_browser.get("/recap/pdf").data == pdf.data
    assert draft(client, auth, past_id, 1, "Late draft", 2).status_code == 409
    assert client.post("/recap/restart", json=auth).status_code == 200
    assert client.get("/recap/pdf").status_code == 404
    types = [event["type"] for event in events(module)]
    assert types.count("studySessionFinished") == 1 and "experimentFinished" not in types
    resumed = begin(worker)
    assert context(resumed)["attempt_id"] == auth["attempt_id"]
    assert "Keep this draft" not in resumed.get("/thank_you").text
    assert resumed.get("/recap/pdf").status_code == 404
    with resumed.session_transaction() as state:
        fresh_auth = {**auth, "csrf_token": state["progress_csrf"]}
    assert resumed.post("/recap/finish", json=fresh_auth).status_code == 404


def test_session_three_finishes_the_study_exactly_once(student_modules):
    module = student_modules()
    settings = schedule(module)
    today = datetime.now(ZONE).date()
    for row in settings["sessions"]:
        row["date"] = (today + timedelta(days=row["number"] - 3)).isoformat()
    module.RESEARCH_STATE.save_settings(settings, settings["revision"])
    client = begin(module)
    auth = complete_today(client)
    assert "Salva l’attività" in client.get("/thank_you").text
    for _ in range(2):
        assert commit(client, auth, "finish").status_code == 200
    for kind in ("sessionCompleted", "studySessionFinished", "experimentFinished"):
        matches = [event for event in events(module) if event["type"] == kind]
        assert len(matches) == 1 and matches[0]["study_session_id"] == "grade-4-session-3"


def test_an_empty_hidden_draft_prevents_a_partial_commit(recap):
    module, client, _, _, past_id, _, auth = recap
    assert draft(client, auth, past_id, 1, "Good edit").status_code == 200
    assert draft(client, auth, past_id, 3, "").status_code == 200
    assert commit(client, auth, "save-changes").status_code == 400
    assert not [event for event in events(module) if event["type"] == "RecapAnswerEdited"]
    assert draft(client, auth, past_id, 3, "Recovered edit", 1).status_code == 200
    assert commit(client, auth, "save-changes").status_code == 200
    assert len([event for event in events(module) if event["type"] == "RecapAnswerEdited"]) == 2


def test_an_old_tab_cannot_commit_an_unseen_draft_or_overwrite_a_revision(recap):
    _, client, _, _, past_id, _, auth = recap
    revisions = draft_revisions(client)
    assert draft(client, auth, past_id, 1, "Edit in the other tab").status_code == 200
    assert commit(client, auth, "finish", revisions).status_code == 409
    assert client.get("/recap/pdf").status_code == 404
    assert commit(client, auth, "save-changes").status_code == 200
    assert draft(client, auth, past_id, 1, "Edit based on original", 2).status_code == 409


def test_finish_compares_snapshot_again_after_pdf_layout(recap, monkeypatch):
    module, client, _, _, past_id, _, auth = recap
    revisions = draft_revisions(client)
    render = module.RECAP.render_pdf

    def render_during_edit(columns):
        # The renderer holds no writer. Another request can save while it runs.
        assert draft(client, auth, past_id, 3, "Changed while rendering").status_code == 200
        return render(columns)

    with monkeypatch.context() as patch:
        patch.setattr(module.RECAP, "render_pdf", render_during_edit)
        assert commit(client, auth, "finish", revisions).status_code == 409
    assert client.get("/recap/pdf").status_code == 404
    assert "Changed while rendering" in client.get("/thank_you").text
    assert commit(client, auth, "finish").status_code == 200


def test_past_the_idle_limit_the_recap_gives_way_to_the_start_page_and_a_closing_page(recap):
    module, client, current, past, past_id, future_id, auth = recap
    assert draft(client, auth, past_id, 1, "Scritto prima della pausa").status_code == 200
    with client.session_transaction() as state:
        state["last_active"] = (datetime.now() - timedelta(minutes=61)).isoformat()
    assert draft(client, auth, past_id, 1, "Scritto dopo la pausa", 1).status_code == 404
    assert client.get("/thank_you", follow_redirects=True).request.path == "/welcome"
    # Whoever picks the number next must not see these answers: the run closes without the recap.
    page = client.post("/start", data={"user_id": "1"}, follow_redirects=True)
    assert page.request.path == "/thank_you" and "Hai risposto alle tre domande" in page.text
    assert "Chiudi l’attività" in page.text and "Scritto prima della pausa" not in page.text
    with client.session_transaction() as state:
        assert state["progress_id"] == auth["attempt_id"]


def test_the_recap_buttons_arrive_disabled_until_the_script_enables_them(recap):
    module, client, current, past, past_id, future_id, auth = recap
    page = client.get("/thank_you").text
    for action in ("save", "finish"):
        assert re.search(rf'<button[^>]*data-action="{action}"[^>]*\bdisabled\b', page)
