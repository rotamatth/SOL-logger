"""Diletta's dashboard points of November 2026: named questions, the answers with them, and the recap PDF."""
import html
import json
import sqlite3
from pathlib import Path

from study_progress import ProgressStore
from .test_research_dashboard import app, identity, write_run  # noqa: F401
from .test_task_stats_pages import SESSION, at, signed_in

DATE = "2026-10-01"


def write_answered_run(app, uid="1", attempt="attempt-1", suffix="a", answers=None):
    """A run of the current app whose events carry the first and the final answer of each question."""
    root = Path(app.config["RESEARCH_LOG_DIR"])
    settings = app.extensions["research"]["state"].settings()
    study_session = next(item for item in settings["sessions"] if item["id"] == SESSION)
    stem, technical, order = f"{uid}_{DATE}_09-00-00_{suffix}", f"technical-{uid}-{suffix}", ("3", "1", "2")
    answers = answers or [("Andromeda", "answered", 2, "Andromeda e il Triangolo"),
                          ("", "unknown", None, "Io, Europa, Ganimede e Callisto"),
                          ("Un cane", "answered", 3, "Laika")]
    full = []
    for number, (topic, (first, outcome, confidence, final)) in enumerate(zip(order, answers, strict=True), 1):
        base = {"uid": uid, "sessionID": technical, "task_number": number, "actual_topic_number": topic,
                "task_order": list(order), "task_question": f"Synthetic question {topic}?"}
        events = [{**base, "type": "TaskStarted", "timestamp": at(0)},
                  {**base, "type": "OwnKnowledgeAnswerSubmitted", "timestamp": at(1), "attempt_id": attempt,
                   "answer": first, "outcome": outcome, "confidence": confidence, "answerPhase": "pre-search"},
                  {**base, "type": "TaskEnded", "timestamp": at(3), "attempt_id": attempt, "answer": final,
                   "answerPhase": "post-search"}]
        full.extend(events)
        (root / f"{stem}_task{number}_topic{topic}.log").write_text("".join(json.dumps(e) + "\n" for e in events))
    (root / f"{stem}_FULL.log").write_text("".join(json.dumps(e) + "\n" for e in full))
    (root / f"{stem}.run.json").write_text(json.dumps({
        "schema_version": 1, "collection": "v2", "participant_id": uid, "technical_session_id": technical,
        "log_id": suffix, "started_at": DATE + "T09:00:00+02:00", "grade_at_collection": "4",
        "school_year_at_collection": study_session["school_year"], "study_session_at_collection": SESSION,
        "study_session_snapshot": {key: study_session.get(key, "") for key in ("id", "name", "date", "grade", "number", "theme")},
        "assignment_source": "shared", "task_order": list(order),
        "tasks": [{"presented_number": number, "topic_id": topic, "question": f"Synthetic question {topic}?"}
                  for number, topic in enumerate(order, 1)]}))
    return identity("v2\0" + stem)


def test_mays_runs_name_each_question_by_its_topic(app):
    client = signed_in(app)
    write_run(app, uid="10", collection="legacy", metadata=False, date="2026-05-19")
    page = client.get(f"/dashboard/participants/legacy/{identity('10')}").text
    # ID 10 had the space topics in May; the log names only the topic numbers 3, 1 and 2.
    assert "1. Altre galassie" in page and "2. Sistema solare Giove" in page and "3. Primo animale nello spazio" in page


def test_older_legacy_runs_keep_the_topic_number_because_the_file_may_have_changed(app):
    client = signed_in(app)
    write_run(app, uid="10", collection="legacy", metadata=False, date="2026-05-12")
    page = client.get(f"/dashboard/participants/legacy/{identity('10')}").text
    assert '<span class="stats-question">1. 3</span>' in page and "Altre galassie" not in page


def test_each_question_shows_the_childs_two_answers(app):
    client = signed_in(app)
    write_answered_run(app)
    page = client.get(f"/dashboard/participants/study/{identity('1')}").text
    assert "Before searching" in page and "After searching" in page
    assert "Andromeda</dd>" not in page and "Andromeda <span" in page and "★★☆" in page
    assert "Andromeda e il Triangolo" in page and "Laika" in page and "★★★" in page
    assert "Don&#39;t know" in page and "Io, Europa, Ganimede e Callisto" in page
    italian = client.get(f"/dashboard/participants/study/{identity('1')}?lang=it").text
    assert "Prima della ricerca" in italian and "Dopo la ricerca" in italian and "Non lo so" in italian


def test_answers_are_shown_as_text(app):
    client = signed_in(app)
    write_answered_run(app, answers=[("<b>uno</b>", "answered", 1, "<script>x()</script>")] * 3)
    page = client.get(f"/dashboard/participants/study/{identity('1')}").text
    assert "<script>x()</script>" not in page and "&lt;script&gt;x()&lt;/script&gt;" in page


def test_a_version_3_index_is_read_again_for_the_answers(app):
    signed_in(app)
    key = write_answered_run(app)
    index = app.extensions["research"]["index"]
    index.refresh(force=True)
    with index.connect() as db:
        db.execute("PRAGMA user_version=3")
        db.execute("UPDATE runs SET summary=json_remove(summary,'$.attempt_ids')")
    reopened = type(index)(app.config["RESEARCH_STATE_DIR"], index.roots)
    reopened.refresh(force=True)
    summary = next(run for run in reopened.summaries(app.extensions["research"]["state"].settings()) if run["id"] == key)
    assert summary["attempt_ids"] == ["attempt-1"]
    assert summary["task_stats"]["1"]["first_answer"] == {"text": "Andromeda", "unknown": False, "confidence": 2}
    assert summary["task_stats"]["1"]["final_answer"] == "Andromeda e il Triangolo"


def keep_pdf(app, tmp_path, attempt, pdf):
    path = tmp_path / "progress.sqlite3"
    ProgressStore(path)
    app.config["SOL_PROGRESS_DB_PATH"] = str(path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO progress_recap_exports VALUES (?, ?, ?)", (attempt, "2026-10-01T09:05:00", pdf))


def test_researchers_download_the_recap_pdf_the_server_kept(app, tmp_path):
    client = signed_in(app)
    keep_pdf(app, tmp_path, "attempt-1", b"%PDF-1.4 synthetic recap")
    key = write_answered_run(app)
    other = write_answered_run(app, uid="2", attempt="attempt-2", suffix="b")
    page = client.get(f"/dashboard/runs/{key}").text
    assert f"/dashboard/runs/{key}/recap.pdf" in page and "Download the child&#39;s final recap (PDF)" in page
    assert f"/dashboard/runs/{key}/recap.pdf" in client.get(f"/dashboard/participants/study/{identity('1')}").text
    response = client.get(f"/dashboard/runs/{key}/recap.pdf")
    assert response.status_code == 200 and response.mimetype == "application/pdf"
    assert response.data == b"%PDF-1.4 synthetic recap"
    assert 'attachment; filename=riepilogo-1-2026-10-01.pdf' in response.headers["Content-Disposition"]
    assert "no-store" in response.headers["Cache-Control"]
    # A run whose child did not save the activity has no PDF and no link.
    assert "recap.pdf" not in client.get(f"/dashboard/runs/{other}").text
    assert client.get(f"/dashboard/runs/{other}/recap.pdf").status_code == 404


def test_the_pdf_needs_a_sign_in_and_one_attempt(app, tmp_path):
    client = signed_in(app)
    keep_pdf(app, tmp_path, "attempt-1", b"%PDF-1.4 synthetic recap")
    key = write_answered_run(app)
    assert app.test_client().get(f"/dashboard/runs/{key}/recap.pdf").status_code in (302, 401, 403)
    root = Path(app.config["RESEARCH_LOG_DIR"])
    full = next(root.glob("1_*_FULL.log"))
    full.write_text(full.read_text() + json.dumps({"uid": "1", "sessionID": "technical-1-a", "task_number": 1,
                                                   "type": "OwnKnowledgeAnswerSubmitted", "attempt_id": "attempt-9",
                                                   "timestamp": at(4)}) + "\n")
    app.extensions["research"]["index"].refresh(force=True)
    # Logs naming two attempts cannot say which PDF is theirs.
    assert client.get(f"/dashboard/runs/{key}/recap.pdf").status_code == 404


def test_without_the_childrens_database_there_is_no_link(app):
    client = signed_in(app)
    key = write_answered_run(app)
    assert "recap.pdf" not in client.get(f"/dashboard/runs/{key}").text
    assert client.get(f"/dashboard/runs/{key}/recap.pdf").status_code == 404


def test_mays_run_page_shows_each_question_from_the_first_apps_file(app):
    client = signed_in(app)
    key, _, _ = write_run(app, uid="10", collection="legacy", metadata=False, date="2026-05-19")
    older, _, _ = write_run(app, uid="10", collection="legacy", metadata=False, date="2026-05-12", suffix="b")
    page = html.unescape(client.get(f"/dashboard/runs/{key}?lang=it").text)
    # Presented task 1 was topic 3 for ID 10: the galaxies.
    assert "Altre galassie" in page and "Quali sono i nomi di altre 3 galassie oltre la nostra?" in page
    assert "Non registrata nel log" in page and "Non viene sostituito" not in page
    assert "Non viene sostituito" in html.unescape(client.get(f"/dashboard/runs/{older}?lang=it").text)
