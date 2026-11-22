"""The topics of 2 December 2026: constellations for class 4 and muscles for class 5, each on its own engine."""
import importlib.util
import sys
from pathlib import Path

import pytest

from .test_backend_privacy import backend  # noqa: F401
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


@pytest.mark.parametrize("label", ["costellazioni", "muscoli"])
def test_a_new_topic_shows_its_answers_alone_and_the_plain_recap(student_modules, label):
    module = student_modules()
    schedule(module, {**question_set(), "theme": label})
    client, page = recap_page(module)
    assert "recap-stage--plain" in page and 'class="recap-arrow"' not in page and "-recap.webp" not in page
    for number in (1, 2, 3):
        review = client.get(f"/task-review/{number}").text
        assert "unlock--none" in review and "<video" not in review


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
