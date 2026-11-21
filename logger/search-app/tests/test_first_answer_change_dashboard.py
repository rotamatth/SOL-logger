"""The dashboard shows a "Non lo so" replaced before the first search as the written answer, marked as a change."""
import json
from pathlib import Path

from .test_dashboard_answers import DATE, write_answered_run
from .test_research_dashboard import app, identity  # noqa: F401
from .test_task_stats_pages import at, signed_in


def test_the_dashboard_shows_the_written_answer_and_that_it_replaced_non_lo_so(app):  # noqa: F811
    client = signed_in(app)
    write_answered_run(app)
    root = Path(app.config["RESEARCH_LOG_DIR"])
    stem = f"1_{DATE}_09-00-00_a"
    base = {"uid": "1", "sessionID": "technical-1-a", "task_number": 2, "actual_topic_number": "1",
            "task_order": ["3", "1", "2"], "task_question": "Synthetic question 1?"}
    event = {**base, "type": "OwnKnowledgeAnswerChanged", "timestamp": at(2), "attempt_id": "attempt-1",
             "answer": "Io e Europa", "outcome": "answered", "confidence": 1, "previousOutcome": "unknown",
             "answerPhase": "pre-search"}
    for name in (f"{stem}_FULL.log", f"{stem}_task2_topic1.log"):
        with (root / name).open("a") as log:
            log.write(json.dumps(event) + "\n")
    page = client.get(f"/dashboard/participants/study/{identity('1')}").text
    assert "Io e Europa" in page and "★☆☆" in page
    assert "first “Non lo so”, changed before searching" in page
    italian = client.get(f"/dashboard/participants/study/{identity('1')}?lang=it").text
    assert "prima “Non lo so”, cambiata prima della ricerca" in italian
