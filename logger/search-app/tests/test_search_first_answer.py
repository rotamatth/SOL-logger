"""Search reads the original submitted answer within the current attempt/question."""
from markupsafe import escape

import pytest

from .test_connected_first_answer import module, begin, first, context, Fields  # noqa: F401
from .test_study_enrollment import student_modules  # noqa: F401


@pytest.mark.parametrize("path", ["/search", "/result?query=probe", "/webpage?url=https://example.org/page"])
def test_original_first_answer_is_read_only_on_each_search_surface(module, path):
    client = begin(module)
    text = '  Laika\n</textarea><script>alert("original")</script>'
    assert first(client, text).status_code == 303
    module.search_backend.search = lambda query, page, rpp: (query, [], 0, "none")
    html = client.get(path).text
    fields = Fields(html)
    assert 'id="search-first-answer-btn"' in html
    assert 'id="search-first-answer-dialog"' in html
    assert 'id="search-first-answer-text"' in html and "readonly" in html
    assert escape(text) in html and '<script>alert("original")</script>' not in html
    # The answer must not be included in the common event context/global object.
    event_context = html.split("window.STUDY_PROGRESS_CONTEXT =", 1)[1].split(";", 1)[0]
    assert "Laika" not in event_context
    assert not fields.values.get("text")


def test_confirmed_unknown_is_displayed_without_turning_it_into_an_answer_text(module):
    client = begin(module)
    assert first(client, outcome="unknown").status_code == 303
    page = client.get("/search")
    assert 'id="search-first-answer-btn"' in page.text
    assert 'data-outcome="unknown"' in page.text and "Non lo so" in page.text
    assert 'id="search-first-answer-text"' not in page.text


def test_drafts_and_other_participants_do_not_supply_the_search_original(module):
    client = begin(module)
    fields = Fields(client.get("/task").text).values
    assert client.post("/first-answer/draft", json={**fields, "text": "Draft only", "revision": 0}).status_code == 200
    assert 'id="search-first-answer-btn"' not in client.get("/task").text
    assert client.get("/search").status_code == 302
    assert first(client, "Original one").status_code == 303
    other = begin(module, "2")
    assert first(other, "Original two").status_code == 303
    own_page, other_page = client.get("/search").text, other.get("/search").text
    assert "Original one" in own_page and "Original two" not in own_page and "Draft only" not in own_page
    assert "Original two" in other_page and "Original one" not in other_page


def test_next_question_shows_its_own_original_and_resume_keeps_it(module):
    client = begin(module)
    first(client, "Before question one")
    ctx = context(client)
    upload = {"session_id": ctx["sessionID"], "logs": [{**ctx, "type": "TaskEnded", "answer": "After one"}]}
    assert client.post("/log_session", json=upload).status_code == 200
    assert client.post("/end").status_code == 302
    assert client.get("/search").status_code == 302
    assert first(client, "Before question two").status_code == 303
    resumed = begin(module)
    html = resumed.get("/search").text
    assert "Before question two" in html and "Before question one" not in html and "After one" not in html
    assert context(resumed)["task_number"] == 2
