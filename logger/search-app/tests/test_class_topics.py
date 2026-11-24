"""The topics of 2 December 2026: constellations for class 4 and muscles for class 5, each on its own engine."""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

from .test_backend_privacy import backend  # noqa: F401
from .test_research_dashboard import app, login  # noqa: F401
from .test_session_question_editor import URL, configured, editor_form
from .test_child_pages import recap_page
from .test_connected_first_answer import begin
from .test_search_by_theme import engines
from .test_study_enrollment import question_set, schedule, student_modules  # noqa: F401

APP_ROOT = Path(__file__).resolve().parents[1]
OLD = {"VERTEX_SPAZIO_ENGINE_ID": "space-engine", "VERTEX_SPAZIO_DATA_STORE_ID": "space-store",
       "VERTEX_ORECCHIO_ENGINE_ID": "ear-engine", "VERTEX_ORECCHIO_DATA_STORE_ID": "ear-store"}
ALL = {**OLD, "VERTEX_COSTELLAZIONI_ENGINE_ID": "constellations-engine",
       "VERTEX_COSTELLAZIONI_DATA_STORE_ID": "constellations-store",
       "VERTEX_MUSCOLI_ENGINE_ID": "muscles-engine", "VERTEX_MUSCOLI_DATA_STORE_ID": "muscles-store"}


@pytest.mark.parametrize("theme", ["constellations", "muscles"])
def test_each_new_topic_searches_and_completes_on_its_own_engine(backend, monkeypatch, theme):
    calls = engines(backend, monkeypatch, ALL)
    backend.search("query", 1, 10, theme=theme)
    backend.autocomplete("query", theme=theme)
    assert f"/engines/{theme}-engine/" in calls[0] and calls[1].endswith(f"/dataStores/{theme}-store")


@pytest.mark.parametrize("theme", ["constellations", "muscles"])
def test_a_new_topic_without_its_engine_never_searches_an_old_one(backend, monkeypatch, theme):
    calls = engines(backend, monkeypatch, OLD)
    with pytest.raises(RuntimeError):
        backend.search("query", 1, 10, theme=theme)
    assert calls == []


@pytest.mark.parametrize(("label", "theme"), [("costellazioni", "constellations"), (" Costellazioni ", "constellations"),
                                              ("muscoli", "muscles"), ("Corpo umano (muscoli)", "muscles"),
                                              ("corpo umano", "ear"), ("spazio", "space")])
def test_the_words_typed_in_the_dashboard_pick_the_topic(student_modules, label, theme):
    assert student_modules().known_theme(label) == theme


@pytest.mark.parametrize(("label", "theme"), [("costellazioni", "constellations"), ("muscoli", "muscles")])
def test_a_new_topic_shows_its_pictures_after_each_question_and_on_the_recap(student_modules, label, theme):
    module = student_modules()
    schedule(module, {**question_set(), "theme": label})
    client, page = recap_page(module)
    assert f"recap-stage--{theme}" in page and page.count('class="recap-arrow"') == 3
    assert f"/static/images/review/{theme}-recap.webp" in page
    pieces = dict(re.findall(rf'recap-piece--{theme}-(\d)" aria-labelledby="recap-question-(\d)"', page))
    assert sorted(pieces) == ["1", "2", "3"]
    for slot, number in pieces.items():
        # A question's place in the session picks its picture, the same part on its review page and on the recap.
        review = client.get(f"/task-review/{number}").text
        assert f"unlock--{theme}-{slot}" in review and f"/static/images/review/{theme}-{slot}.webp" in review
        assert 'class="unlock-arrow"' in review and "<video" not in review and "/static/videos/review/" not in review


@pytest.mark.parametrize("theme", ["constellations", "muscles"])
def test_every_picture_of_a_new_topic_is_there_and_has_its_place(theme):
    static = APP_ROOT / "static"
    for name in ("1", "2", "3", "recap"):
        assert (static / "images" / "review" / f"{theme}-{name}.webp").stat().st_size > 5_000
    for slot in ("1", "2", "3"):
        assert f".unlock--{theme}-{slot} .review-animation" in (static / "study-review.css").read_text()


def load_check_tool(backend, monkeypatch):
    monkeypatch.setitem(sys.modules, "search_backend", backend)
    spec = importlib.util.spec_from_file_location("check_search_engines_tool", APP_ROOT / "tools" / "check_search_engines.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return tool


@pytest.mark.parametrize(("settings", "asked"), [(OLD, ["space-engine", "ear-engine"]),
                                                 (ALL, ["space-engine", "ear-engine", "constellations-engine", "muscles-engine"])])
def test_the_engine_check_asks_every_topic_with_an_engine_and_names_the_others(backend, monkeypatch, capsys, settings, asked):
    engines(backend, monkeypatch, settings)
    seen = []
    monkeypatch.setattr(backend, "vertex_search", lambda query, page, rpp, config: seen.append(config[2]) or (
        query, [{"link": "https://example.org/page"}], 1, "none"))
    monkeypatch.setattr(backend, "vertex_autocomplete", lambda query, config: [])
    assert load_check_tool(backend, monkeypatch).main() == 0
    out = capsys.readouterr().out
    assert seen == asked
    assert ("costellazioni: no engine set (VERTEX_COSTELLAZIONI_ENGINE_ID, VERTEX_COSTELLAZIONI_DATA_STORE_ID)." in out) == (settings is OLD)
    assert ("muscoli: 1 results" in out) == (settings is ALL)


def test_the_server_passes_the_new_topic_engines_to_the_app():
    """docker-compose.yml names each variable it hands to the app: without these the IDs in .env never arrive."""
    compose = (APP_ROOT.parent / "docker-compose.yml").read_text()
    for label in ("COSTELLAZIONI", "MUSCOLI"):
        for name in (f"VERTEX_{label}_ENGINE_ID", f"VERTEX_{label}_DATA_STORE_ID"):
            assert f'{name}: "${{{name}:-}}"' in compose


@pytest.mark.parametrize(("settings", "label", "expected"), [
    (ALL, "Costellazioni", {"topic": "costellazioni", "searches": True, "setting": "COSTELLAZIONI"}),
    (OLD, "muscoli", {"topic": "muscoli", "searches": False, "setting": "MUSCOLI"}),
    (ALL, "costelazioni", {"topic": None, "searches": False, "setting": None}),
    ({}, "costelazioni", {"topic": None, "searches": True, "setting": None})])
def test_the_dashboard_hears_which_topic_a_text_picks_and_whether_it_searches(student_modules, backend, monkeypatch,
                                                                              settings, label, expected):
    monkeypatch.chdir(APP_ROOT)  # The backend fixture left the app's folder, which the children's app reads from.
    module = student_modules()
    engines(backend, monkeypatch, settings)
    monkeypatch.setattr(module, "search_backend", backend)
    assert module.app.config["TOPIC_SEARCH_STATUS"](label) == expected
    assert module.app.config["TOPIC_WORDS"] == ("spazio", "orecchio", "costellazioni", "muscoli")


def topic_line(app, status, theme):  # noqa: F811
    app.config.update(TOPIC_SEARCH_STATUS=lambda text: {**status, "text": text}, TOPIC_WORDS=("spazio", "muscoli"))
    client = app.test_client()
    login(client)
    configured(app)
    client.post(URL, data=editor_form(client, action="save_draft", theme=theme))
    return client.get(URL).text


def test_the_questions_page_names_the_topic_it_recognised(app):  # noqa: F811
    page = topic_line(app, {"topic": "muscoli", "searches": True, "setting": "MUSCOLI"}, "Muscoli")
    assert 'id="question-theme-status">Recognised topic: muscoli.' in page and "notice warning" not in page.split("question-theme")[1]
    assert '<datalist id="question-theme-words"><option value="spazio"><option value="muscoli"></datalist>' in page


def test_the_questions_page_warns_when_the_topic_has_no_engine(app):  # noqa: F811
    page = topic_line(app, {"topic": "muscoli", "searches": False, "setting": "MUSCOLI"}, "muscoli")
    assert '<p class="notice warning" id="question-theme-status">Topic: muscoli.' in page
    assert "VERTEX_MUSCOLI_ENGINE_ID and VERTEX_MUSCOLI_DATA_STORE_ID" in page


def test_the_questions_page_warns_when_the_app_does_not_know_the_topic(app):  # noqa: F811
    page = topic_line(app, {"topic": None, "searches": False, "setting": None}, "muscle")
    assert "children’s search would show an error. Type one of: spazio, muscoli." in page


def test_the_questions_page_asks_for_a_topic_when_there_is_none(app):  # noqa: F811
    page = topic_line(app, {"topic": None, "searches": False, "setting": None}, "")
    assert '<p class="notice warning" id="question-theme-status">No topic yet. Type one of: spazio, muscoli.</p>' in page


def test_a_dashboard_without_the_children_app_shows_no_topic_line(app):  # noqa: F811
    client = app.test_client()
    login(client)
    configured(app)
    page = client.get(URL).text
    assert "question-theme-status" not in page and "question-theme-words" not in page
