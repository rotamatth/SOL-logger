"""A search backend for tests that load the whole app: it never reaches a search engine."""
import types


def search_backend_stub():
    """Tests replace search and autocomplete as they need. The dashboard's topic line hears that every topic searches."""
    stub = types.ModuleType("search_backend")
    stub.VERTEX_THEME_SETTINGS = {}
    stub.theme_engine_ready = lambda theme: True
    return stub
