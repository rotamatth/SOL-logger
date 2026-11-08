"""Each run searches the engine of its own theme and never answers from another dataset."""
from types import SimpleNamespace

import pytest

from .test_backend_privacy import CONFIG, backend  # noqa: F401
from .test_connected_first_answer import begin, first
from .test_study_enrollment import question_set, schedule, student_modules  # noqa: F401

BOTH = {"VERTEX_SPAZIO_ENGINE_ID": "space-engine", "VERTEX_SPAZIO_DATA_STORE_ID": "space-store",
        "VERTEX_ORECCHIO_ENGINE_ID": "ear-engine", "VERTEX_ORECCHIO_DATA_STORE_ID": "ear-store"}


def engines(backend, monkeypatch, settings):
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(backend, "_theme_configs", backend.load_theme_configs(CONFIG))
    monkeypatch.setattr(backend, "SERP_API_KEY", None)
    calls = []
    monkeypatch.setattr(backend, "get_search_client", lambda location: SimpleNamespace(
        search=lambda request: calls.append(request.serving_config) or SimpleNamespace(
            results=[], total_size=0, corrected_query="")))
    monkeypatch.setattr(backend, "get_completion_client", lambda location: SimpleNamespace(
        complete_query=lambda request, **options: calls.append(request.data_store) or SimpleNamespace(
            query_suggestions=[])))
    return calls


@pytest.mark.parametrize("theme", [None, "space", "ear"])
def test_without_theme_engines_every_run_keeps_the_single_engine(backend, monkeypatch, theme):
    calls = engines(backend, monkeypatch, {})
    backend.search("query", 1, 10, theme=theme)
    backend.autocomplete("query", theme=theme)
    assert "/engines/synthetic-engine/" in calls[0] and calls[1].endswith("/dataStores/synthetic-store")


@pytest.mark.parametrize(("theme", "engine", "store"), [("space", "space-engine", "space-store"),
                                                        ("ear", "ear-engine", "ear-store")])
def test_each_theme_searches_and_completes_on_its_own_engine(backend, monkeypatch, theme, engine, store):
    calls = engines(backend, monkeypatch, BOTH)
    backend.search("query", 1, 10, theme=theme)
    backend.autocomplete("query", theme=theme)
    assert f"/engines/{engine}/" in calls[0] and calls[0].startswith("projects/synthetic-project/")
    assert calls[1].endswith(f"/dataStores/{store}")


@pytest.mark.parametrize("theme", ["ear", None])
def test_a_theme_without_its_engine_never_answers_from_another_dataset(backend, monkeypatch, theme):
    calls = engines(backend, monkeypatch, {"VERTEX_SPAZIO_ENGINE_ID": "space-engine",
                                           "VERTEX_SPAZIO_DATA_STORE_ID": "space-store"})
    with pytest.raises(RuntimeError):
        backend.search("query", 1, 10, theme=theme)
    with pytest.raises(RuntimeError):
        backend.autocomplete("query", theme=theme)
    assert calls == []


@pytest.mark.parametrize(("label", "theme"), [("spazio", "space"), (" Spazio ", "space"), ("orecchio", "ear"),
                                              ("Corpo umano (orecchio)", "ear"), ("Another theme", None)])
def test_a_run_asks_for_the_engine_of_its_question_set_also_after_resuming(student_modules, label, theme):
    module = student_modules()
    schedule(module, {**question_set(), "theme": label})
    client = begin(module)
    assert first(client).status_code == 303
    seen = []
    module.search_backend.search = lambda query, page, rpp, theme=None: seen.append(theme) or (query, [], 0, "none")
    module.search_backend.autocomplete = lambda query, theme=None: seen.append(theme) or (["luna"], "vertex")
    module.search_backend.autocomplete_query_model = lambda: "search-history"
    assert client.get("/result?query=probe").status_code == 200
    assert client.get("/autocomplete?query=luna").get_json()["suggestions"] == ["luna"]
    resumed = begin(module)
    assert resumed.get("/autocomplete?query=luna").get_json()["suggestions"] == ["luna"]
    assert seen == [theme, theme, theme]
