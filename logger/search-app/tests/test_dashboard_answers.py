"""Diletta's dashboard points of November 2026: named questions, the answers with them, and the recap PDF."""
from .test_research_dashboard import app, identity, write_run  # noqa: F401
from .test_task_stats_pages import signed_in


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
