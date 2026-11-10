"""Task statistics reach the researcher pages from real indexed logs, without changing exports."""
import json
from pathlib import Path

from .test_research_dashboard import app, archive, configure, dashboard_links, identity, login  # noqa: F401

SESSION = "grade-4-session-1"
DATE = "2026-10-01"


def at(minute, second=0, date=DATE):
    return f"{date}T09:{minute:02d}:{second:02d}.000"


def write_detailed_run(app, uid, order=("3", "1", "2"), date=DATE, session=SESSION, suffix="a", minutes=2, searches=1, finished=3):
    root = Path(app.config["RESEARCH_LOG_DIR"])
    state = app.extensions["research"]["state"]
    settings = state.settings()
    study_session = next(item for item in settings["sessions"] if item["id"] == session)
    stem = f"{uid}_{date}_09-00-00_{suffix}"
    technical = f"technical-{uid}-{suffix}"
    full = []
    for number, topic in enumerate(order, 1):
        base = {"uid": uid, "sessionID": technical, "task_number": number, "actual_topic_number": topic,
                "task_order": list(order), "task_question": f"Synthetic question {topic}?"}
        events = [{**base, "type": "TaskStarted", "timestamp": at(0, date=date)}]
        events += [{**base, "type": "querySubmitted", "timestamp": at(0, 10, date), "query": "synthetic"}] * searches
        events += [{**base, "type": "clickedResult", "timestamp": at(1, date=date), "rank": "3"},
                   {**base, "type": "webpageClosed", "timestamp": at(1, 30, date), "durationMs": 30000}]
        if number <= finished:
            events.append({**base, "type": "TaskEnded", "timestamp": at(minutes, date=date), "answer": "Synthetic"})
        full.extend(events)
        (root / f"{stem}_task{number}_topic{topic}.log").write_text("".join(json.dumps(e) + "\n" for e in events))
    (root / f"{stem}_FULL.log").write_text("".join(json.dumps(e) + "\n" for e in full))
    (root / f"{stem}.run.json").write_text(json.dumps({
        "schema_version": 1, "collection": "v2", "participant_id": uid, "technical_session_id": technical,
        "log_id": suffix, "started_at": date + "T09:00:00+02:00", "grade_at_collection": "4",
        "school_year_at_collection": study_session["school_year"], "study_session_at_collection": session,
        "study_session_snapshot": {key: study_session.get(key, "") for key in ("id", "name", "date", "grade", "number", "theme")},
        "assignment_source": "shared", "task_order": list(order),
        "tasks": [{"presented_number": number, "topic_id": topic, "question": f"Synthetic question {topic}?"}
                  for number, topic in enumerate(order, 1)]}))
    return identity("v2\0" + stem)


def signed_in(app):
    configure(app)
    client = app.test_client()
    login(client)
    return client


def test_a_child_sees_figures_for_each_question(app):
    client = signed_in(app)
    write_detailed_run(app, "1", searches=2)
    page = client.get(f"/dashboard/participants/study/{identity('1')}")
    assert "Statistics by question" in page.text
    assert "1. Synthetic question 3?" in page.text
    assert "2 min" in page.text and "average position" in page.text and "30 s" in page.text
    assert ">None<" in page.text


def test_an_unfinished_question_is_marked_and_has_no_time(app):
    client = signed_in(app)
    write_detailed_run(app, "1", finished=1)
    page = client.get(f"/dashboard/participants/study/{identity('1')}")
    assert page.text.count('badge incomplete">Incomplete / in progress') >= 2
    assert '<dt>Time</dt><dd>—</dd>' in page.text


def test_the_class_table_groups_shuffled_questions_across_children(app):
    client = signed_in(app)
    write_detailed_run(app, "1", order=("3", "1", "2"), minutes=2)
    write_detailed_run(app, "2", order=("1", "2", "3"), minutes=4)
    write_detailed_run(app, "3", order=("2", "3", "1"), minutes=6, finished=1)
    page = client.get(f"/dashboard?collection=study&grade=4&school_year=2026/2027&session={SESSION}")
    assert "This class, question by question" in page.text
    assert page.text.count('<span class="stats-question">Synthetic question') == 3
    assert '<td data-label="Finished">3 / 20</td>' in page.text  # Children 1, 2 and 3 finished question 2.
    assert '<td data-label="Finished">2 / 20</td>' in page.text
    assert "range 2 min – 6 min" in page.text


def test_the_class_table_says_so_when_nothing_is_finished(app):
    client = signed_in(app)
    page = client.get(f"/dashboard?collection=study&grade=4&school_year=2026/2027&session={SESSION}")
    assert "No question has been finished yet" in page.text
    assert "This class, question by question" not in client.get("/dashboard?collection=study&grade=4").text


def test_a_child_across_sessions_gets_charts_with_a_table(app):
    client = signed_in(app)
    write_detailed_run(app, "1", minutes=2, searches=1)
    single = client.get(f"/dashboard/participants/study/{identity('1')}")
    assert "Across sessions" in single.text and 'class="trend-chart"' not in single.text
    write_detailed_run(app, "1", date="2026-10-02", session="grade-4-session-2", suffix="b", minutes=4, searches=3)
    app.extensions["research"]["index"].refresh(force=True)
    both = client.get(f"/dashboard/participants/study/{identity('1')}")
    assert both.text.count('class="trend-chart"') == 3
    assert 'class="trend-column"' in both.text and "<title>" in both.text
    assert "style=" not in both.text.split('class="trend-charts"')[1].split("</section>")[0]
    assert "6 min" in both.text and "12 min" in both.text  # Totals: 3 × 2 min and 3 × 4 min.


def test_the_run_page_shows_the_figures_and_exports_do_not_change(app):
    client = signed_in(app)
    key = write_detailed_run(app, "1")
    page = client.get(f"/dashboard/runs/{key}")
    assert "Statistics by question" in page.text and "Logged events" in page.text
    overview = client.get("/dashboard?collection=study&grade=4")
    assert overview.status_code == 200
    participant = client.get(f"/dashboard/participants/study/{identity('1')}")
    download = next(link for link in dashboard_links(participant) if link.path.endswith("/exports/participant"))
    z, manifest = archive(client.get(download.geturl()))
    exported = json.loads(z.read(manifest["runs"][0]["metadata_path"]))
    assert "task_stats" not in exported and "stats" not in exported["tasks"]["1"]
    assert "task_stats" not in manifest["runs"][0]


def test_statistics_are_translated(app):
    client = signed_in(app)
    write_detailed_run(app, "1")
    page = client.get(f"/dashboard/participants/study/{identity('1')}?lang=it")
    assert "Statistiche per domanda" in page.text and "Eventi registrati" in page.text
    assert "posizione media" in page.text


def test_the_index_rereads_files_indexed_before_statistics_existed(app):
    client = signed_in(app)
    key = write_detailed_run(app, "1")
    index = app.extensions["research"]["index"]
    index.refresh(force=True)
    with index.connect() as db:
        db.execute("PRAGMA user_version=2")
        db.execute("UPDATE runs SET summary=json_remove(summary,'$.task_stats')")
    reopened = type(index)(app.config["RESEARCH_STATE_DIR"], index.roots)
    reopened.refresh(force=True)
    summary = next(run for run in reopened.summaries(app.extensions["research"]["state"].settings()) if run["id"] == key)
    assert summary["task_stats"]["1"]["searches"] == 1
    assert client.get(f"/dashboard/runs/{key}").status_code == 200
