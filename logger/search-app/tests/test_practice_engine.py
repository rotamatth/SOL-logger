"""The practice question searches its own engine, and setting it never changes the engine a run searches."""
from pathlib import Path
import importlib.util

import pytest

from .test_backend_privacy import CONFIG, backend  # noqa: F401
from .test_search_by_theme import BOTH, engines

APP_ROOT = Path(__file__).resolve().parents[1]
PRACTICE = {"VERTEX_PROVA_ENGINE_ID": "volcano-engine", "VERTEX_PROVA_DATA_STORE_ID": "volcano-store"}


def with_practice(backend, monkeypatch, settings):
    calls = engines(backend, monkeypatch, settings)
    monkeypatch.setattr(backend, "_practice_config", backend.load_practice_config(CONFIG))
    return calls


def test_the_practice_question_searches_and_completes_on_its_own_engine(backend, monkeypatch):
    calls = with_practice(backend, monkeypatch, {**BOTH, **PRACTICE})
    backend.search("vulcano", 1, 10, theme=backend.PRACTICE_THEME)
    backend.autocomplete("vulca", theme=backend.PRACTICE_THEME)
    assert "/engines/volcano-engine/" in calls[0] and calls[0].startswith("projects/synthetic-project/")
    assert calls[1].endswith("/dataStores/volcano-store")
    assert backend.practice_engine_status() == {"configured": True, "shared_with_theme": False}


@pytest.mark.parametrize("settings", [{}, BOTH, {"VERTEX_PROVA_ENGINE_ID": "volcano-engine"}])
def test_without_both_ids_the_practice_question_never_searches_another_engine(backend, monkeypatch, settings):
    calls = with_practice(backend, monkeypatch, settings)
    with pytest.raises(RuntimeError):
        backend.search("vulcano", 1, 10, theme=backend.PRACTICE_THEME)
    with pytest.raises(RuntimeError):
        backend.autocomplete("vulca", theme=backend.PRACTICE_THEME)
    assert calls == []
    assert backend.practice_engine_configured() is False


@pytest.mark.parametrize(("theme", "engine"), [(None, "synthetic-engine"), ("space", "synthetic-engine")])
def test_a_practice_engine_alone_leaves_the_single_engine_of_runs_as_it_was(backend, monkeypatch, theme, engine):
    calls = with_practice(backend, monkeypatch, PRACTICE)
    backend.search("query", 1, 10, theme=theme)
    assert f"/engines/{engine}/" in calls[0]


@pytest.mark.parametrize(("theme", "engine"), [("space", "space-engine"), ("ear", "ear-engine")])
def test_with_a_practice_engine_each_theme_still_searches_its_own(backend, monkeypatch, theme, engine):
    calls = with_practice(backend, monkeypatch, {**BOTH, **PRACTICE})
    backend.search("query", 1, 10, theme=theme)
    assert f"/engines/{engine}/" in calls[0]


def test_the_dashboard_hears_when_the_practice_engine_is_one_a_class_searches(backend, monkeypatch):
    with_practice(backend, monkeypatch, {**BOTH, "VERTEX_PROVA_ENGINE_ID": "space-engine",
                                         "VERTEX_PROVA_DATA_STORE_ID": "volcano-store"})
    assert backend.practice_engine_status() == {"configured": True, "shared_with_theme": True}


def load_check_tool(backend, monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "search_backend", backend)
    spec = importlib.util.spec_from_file_location("check_search_engines_tool", APP_ROOT / "tools" / "check_search_engines.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return tool


def test_the_engine_check_asks_the_practice_engine_on_the_topic_given(backend, monkeypatch, capsys):
    with_practice(backend, monkeypatch, {**BOTH, **PRACTICE})
    asked = []
    monkeypatch.setattr(backend, "vertex_search", lambda query, page, rpp, config: asked.append((query, config[2])) or (
        query, [{"link": "https://example.org/page"}], 1, "none"))
    monkeypatch.setattr(backend, "vertex_autocomplete", lambda query, config: [])
    tool = load_check_tool(backend, monkeypatch)
    assert tool.main(["--prova-query", "terremoti"]) == 0
    assert ("terremoti", "volcano-engine") in asked
    assert "prova: 1 results for 'terremoti'" in capsys.readouterr().out


def test_the_engine_check_says_when_the_practice_question_is_skipped(backend, monkeypatch, capsys):
    with_practice(backend, monkeypatch, BOTH)
    monkeypatch.setattr(backend, "vertex_search", lambda query, page, rpp, config: (
        query, [{"link": "https://example.org/page"}], 1, "none"))
    monkeypatch.setattr(backend, "vertex_autocomplete", lambda query, config: [])
    tool = load_check_tool(backend, monkeypatch)
    assert tool.main([]) == 0
    assert "the practice question is skipped" in capsys.readouterr().out


def test_the_server_passes_the_practice_engine_to_the_app():
    """docker-compose.yml names each variable it hands to the app: without these the IDs in .env never arrive."""
    compose = (APP_ROOT.parent / "docker-compose.yml").read_text()
    for name in ("VERTEX_PROVA_ENGINE_ID", "VERTEX_PROVA_DATA_STORE_ID"):
        assert f'{name}: "${{{name}:-}}"' in compose
