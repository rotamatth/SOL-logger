"""Settings › Practice question: researchers set the practice's topic, question and switch, and try its engine."""
from html import unescape
import re

import pytest

from .test_research_dashboard import app, csrf, login  # noqa: F401

PAGE = "/dashboard/settings/practice"
RESULTS = [{"title": f"Vulcano {number}", "link": f"https://volcano{number}.invalid/pagina"} for number in range(1, 8)]


@pytest.fixture
def researcher(app):  # noqa: F811
    client = app.test_client()
    login(client)
    return client


def engine(app, configured=True, shared=False, search=None):  # noqa: F811
    app.config["PRACTICE_ENGINE_STATUS"] = lambda: {"configured": configured, "shared_with_theme": shared}
    app.config["PRACTICE_SEARCH"] = search or (lambda query: (query, [dict(result) for result in RESULTS], 7, "none"))


def save(client, revision=0, **values):
    data = {"csrf": csrf(client.get(PAGE)), "action": "save", "revision": str(revision),
            "topic": "Terremoti", "question": "Come si misura un terremoto?", "enabled": "1"}
    data.update(values)
    return client.post(PAGE, data={key: value for key, value in data.items() if value is not None})


def text(response):
    return unescape(response.get_data(as_text=True))


def test_the_settings_have_a_practice_tab(app, researcher):  # noqa: F811
    settings = text(researcher.get("/dashboard/settings"))
    assert re.search(r'href="/dashboard/settings/practice[^"]*"[^>]*>Practice question<', settings)
    page = text(researcher.get(PAGE))
    assert re.search(r'href="/dashboard/settings/practice[^"]*" aria-current="page">Practice question<', page)


def test_the_page_shows_the_default_volcano_question_and_says_nothing_is_saved(app, researcher):  # noqa: F811
    engine(app)
    page = text(researcher.get(PAGE))
    assert 'value="Vulcani"' in page and "Sapete elencarne 3?" in page
    assert re.search(r'name="enabled" value="1" id="practice-enabled" checked', page)
    assert "Nothing children do in the practice is saved." in page
    assert "a volcano, fixed in the app" in page
    assert "Connected. Children see the practice after Inizia." in page


@pytest.mark.parametrize(("configured", "shared", "enabled", "message"), [
    (False, False, True, "No search engine is set for the practice"),
    (True, True, True, "also an engine a class searches"),
    (True, False, False, "The practice is off: children go straight to the ID page."),
])
def test_the_engine_status_says_what_children_will_see(app, researcher, configured, shared, enabled, message):  # noqa: F811
    engine(app, configured, shared)
    if not enabled:
        assert save(researcher, enabled=None).status_code == 302
    assert message in text(researcher.get(PAGE))


def test_a_saved_practice_is_what_the_next_group_gets(app, researcher):  # noqa: F811
    response = save(researcher, enabled=None)
    assert response.status_code == 302 and "saved=1" in response.location
    stored = app.extensions["research"]["state"].practice()
    assert (stored["enabled"], stored["topic"], stored["question"]) == (False, "Terremoti", "Come si misura un terremoto?")
    page = text(researcher.get(response.location))
    assert "A practice already under way keeps the question it began with." in page
    assert 'value="Terremoti"' in page and "checked" not in re.search(r'<input type="checkbox"[^>]*>', page)[0]


def test_saving_from_an_old_page_is_refused(app, researcher):  # noqa: F811
    assert save(researcher, revision=0).status_code == 302
    refused = save(researcher, revision=0, topic="Vecchia")
    assert refused.status_code == 400 and "changed in another tab or by another researcher" in text(refused)
    assert app.extensions["research"]["state"].practice()["topic"] == "Terremoti"


@pytest.mark.parametrize(("field", "value", "message"), [
    ("question", "   ", "Enter a question of at most 300 characters."),
    ("topic", "t" * 81, "Enter a topic of at most 80 characters."),
])
def test_an_unusable_practice_is_shown_back_unsaved(app, researcher, field, value, message):  # noqa: F811
    refused = save(researcher, **{field: value})
    assert refused.status_code == 400 and message in text(refused)
    assert app.extensions["research"]["state"].practice()["revision"] == 0


def test_saving_needs_the_researchers_token(app, researcher):  # noqa: F811
    refused = researcher.post(PAGE, data={"csrf": "wrong", "action": "save", "revision": "0", "topic": "X",
                                          "question": "Y", "enabled": "1"})
    assert refused.status_code == 400
    assert app.extensions["research"]["state"].practice()["revision"] == 0


def test_the_page_needs_a_signed_in_researcher(app):  # noqa: F811
    assert app.test_client().get(PAGE).status_code in (302, 401, 403)


def test_trying_a_search_shows_the_first_five_titles_and_sites(app, researcher):  # noqa: F811
    asked = []
    engine(app, search=lambda query: asked.append(query) or (query, [dict(result) for result in RESULTS], 7, "none"))
    page = text(researcher.post(PAGE, data={"csrf": csrf(researcher.get(PAGE)), "action": "test",
                                            "test_query": "  tipi di  eruzioni "}))
    assert asked == ["tipi di eruzioni"]
    assert all(f"Vulcano {number}" in page for number in range(1, 6)) and "Vulcano 6" not in page
    assert "(volcano1.invalid)" in page
    assert app.extensions["research"]["state"].practice()["revision"] == 0


@pytest.mark.parametrize(("configured", "search", "query", "message"), [
    (False, None, "vulcano", "No search engine is set for the practice"),
    (True, lambda query: (query, [], 0, "none"), "vulcano", "The engine answered with no results."),
    (True, lambda query: (_ for _ in ()).throw(RuntimeError("secret-engine-id")), "vulcano", "The search engine did not answer."),
    (True, None, "   ", "Enter some words to search"),
])
def test_a_search_that_cannot_answer_says_why_without_details(app, researcher, configured, search, query, message):  # noqa: F811
    engine(app, configured, search=search)
    page = text(researcher.post(PAGE, data={"csrf": csrf(researcher.get(PAGE)), "action": "test", "test_query": query}))
    assert message in page and "secret-engine-id" not in page


def test_every_practice_text_exists_in_both_languages():
    from research_dashboard.i18n import TEXT
    keys = [key for key in TEXT if key.startswith("practice_") or key in ("save_practice", "invalid_practice")]
    assert len(keys) >= 20
    assert all(len(TEXT[key]) == 2 and all(TEXT[key]) for key in keys)


def test_the_italian_page_reads_in_italian(app):  # noqa: F811
    client = app.test_client()
    login(client, lang="it")
    page = text(client.get(PAGE + "?lang=it"))
    assert "Domanda di prova" in page and "Salva domanda di prova" in page and "Prova una ricerca" in page
