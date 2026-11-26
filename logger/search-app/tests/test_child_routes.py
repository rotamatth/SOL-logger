"""The search pages of a run keep their own addresses after the practice question started sharing them."""
import pytest

from .test_connected_first_answer import begin, first
from .test_study_enrollment import question_set, schedule, student_modules  # noqa: F401

RESULT = {"title": "Synthetic result", "snippet": "Synthetic snippet", "link": "https://synthetic.invalid/page",
          "docid": "synthetic-document"}


@pytest.fixture
def searching(student_modules):
    module = student_modules()
    schedule(module, question_set())
    module.search_backend.search = lambda query, page, rpp, theme=None: (query, [dict(RESULT)], 1, "none")
    client = begin(module)
    assert first(client).status_code == 303
    return client


def test_the_search_page_of_a_run_sends_its_searches_and_suggestions_to_the_runs_routes(searching):
    page = searching.get("/search").text
    assert 'action="/result"' in page
    assert "`/autocomplete?query=${encodeURIComponent(query)}`" in page
    assert "fetch('/end'" in page
    assert "/static/logger.js" in page and "practice-page.js" not in page


def test_the_results_and_the_viewer_of_a_run_link_to_the_runs_routes(searching):
    results = searching.post("/result", data={"query": "synthetic"}).text
    assert ('href="/webpage?url=https://synthetic.invalid/page&amp;query=synthetic&amp;page=1" '
            'id="abstract-link-1"') in results
    assert 'href="/search" id="serp-logo-link"' in results
    viewer = searching.get("/webpage", query_string={"url": RESULT["link"], "query": "synthetic", "page": 1}).text
    assert 'href="/result?query=synthetic&amp;page=1" id="viewer-back-btn"' in viewer
    assert 'fetch("/iframe_check" + "?url="' in viewer
