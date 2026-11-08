"""Provider failures must not leak participant text or credentials into process logs."""
import builtins
import importlib.util
import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests


APP_ROOT = Path(__file__).resolve().parents[1]
CONFIG = ("synthetic-project", "global", "synthetic-engine", "synthetic-store", "it")
QUERY = "synthetic private participant query"
API_KEY = "synthetic-api-key-for-privacy-test"


@pytest.fixture
def backend(tmp_path, monkeypatch):
    """Load the real backend without opening the project's credentials file."""
    monkeypatch.chdir(tmp_path)
    original_open = builtins.open

    def synthetic_credentials(filename, *args, **kwargs):
        if isinstance(filename, (str, Path)) and Path(filename).name == "API_keys.json":
            return io.StringIO("{}")
        return original_open(filename, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", synthetic_credentials)
    spec = importlib.util.spec_from_file_location("privacy_test_search_backend", APP_ROOT / "search_backend.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SERP_API_KEY = API_KEY
    module.SERP_AUTOCOMPLETE_HL = "it"
    module.SERP_AUTOCOMPLETE_GL = "it"
    module.SEARCH_BACKEND = "vertex"
    module._vertex_config = CONFIG
    return module


@pytest.mark.parametrize("status", [401, 429])
def test_autocomplete_http_failure_does_not_log_query_or_api_key(backend, monkeypatch, caplog, status):
    monkeypatch.setattr(backend, "get_completion_client", lambda location: SimpleNamespace(
        complete_query=lambda request, **options: SimpleNamespace(query_suggestions=[])))

    def provider_failure(url, params, timeout):
        response = requests.Response()
        response.status_code = status
        response.reason = "Synthetic provider failure"
        response.url = requests.Request("GET", url, params=params).prepare().url
        return response

    monkeypatch.setattr(backend.requests, "get", provider_failure)
    with caplog.at_level(logging.DEBUG, logger=backend.__name__):
        assert backend.autocomplete(QUERY) == ([], "none")

    assert "HTTPError" in caplog.text
    assert QUERY not in caplog.text and "synthetic+private+participant+query" not in caplog.text
    assert API_KEY not in caplog.text and "https://serpapi.com" not in caplog.text
    assert "api_key=" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("operation", ["search", "autocomplete"])
def test_provider_error_messages_are_not_logged(backend, monkeypatch, caplog, operation):
    error = RuntimeError(f"Provider rejected {QUERY}; https://provider.invalid/?api_key={API_KEY}")

    def fail(request, **options):
        raise error

    client = SimpleNamespace(search=fail, complete_query=fail)
    monkeypatch.setattr(backend, "get_search_client", lambda location: client)
    monkeypatch.setattr(backend, "get_completion_client", lambda location: client)
    with caplog.at_level(logging.ERROR, logger=backend.__name__):
        if operation == "search":
            with pytest.raises(RuntimeError) as raised:
                backend.vertex_search(QUERY, 1, 10, CONFIG)
            assert raised.value is error
        else:
            assert backend.vertex_autocomplete(QUERY, CONFIG) == []

    assert "RuntimeError" in caplog.text
    assert QUERY not in caplog.text and API_KEY not in caplog.text
    assert "https://provider.invalid" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("vertex_outcome", ["empty", "rpc-error", "client-error", "unconfigured"])
def test_vertex_without_suggestions_uses_serpapi(backend, monkeypatch, vertex_outcome):
    def complete_query(request, **options):
        if vertex_outcome == "rpc-error":
            raise TimeoutError("synthetic Vertex deadline exceeded")
        return SimpleNamespace(query_suggestions=[])

    def completion_client(location):
        if vertex_outcome == "client-error":
            raise RuntimeError("synthetic credentials unavailable")
        return SimpleNamespace(complete_query=complete_query)

    monkeypatch.setattr(backend, "get_completion_client", completion_client)
    if vertex_outcome == "unconfigured":
        monkeypatch.setattr(backend, "_vertex_config", ("", "global", "", "", "it"))
    mock_serpapi(backend, monkeypatch, {"suggestions": [{"value": "fasi della luna"}]})

    assert backend.autocomplete("fasi della lu") == (["fasi della luna"], "SERP_API")


def test_vertex_success_reuses_completion_client_and_skips_serpapi(backend, monkeypatch):
    clients = []

    def complete_query(request, *, retry=None, timeout=None):
        assert request.query_model == "search-history"
        assert timeout is not None and timeout <= 1 and retry is None
        return SimpleNamespace(query_suggestions=[SimpleNamespace(suggestion=f"{request.query} piena")])

    def make_completion_client(**options):
        client = SimpleNamespace(complete_query=complete_query)
        clients.append(client)
        return client

    monkeypatch.setattr(backend.discoveryengine, "CompletionServiceClient", make_completion_client)
    monkeypatch.setattr(backend.requests, "get", unexpected_provider_call)

    assert backend.autocomplete("luna") == (["luna piena"], "vertex")
    assert backend.autocomplete("lune") == (["lune piena"], "vertex")
    assert len(clients) == 1


def test_autocomplete_does_not_call_serpapi_without_a_key(backend, monkeypatch):
    monkeypatch.setattr(backend, "SEARCH_BACKEND", "pyterrier")
    monkeypatch.setattr(backend, "SERP_API_KEY", None)
    monkeypatch.setattr(backend.requests, "get", unexpected_provider_call)
    assert backend.autocomplete("luna") == ([], "none")


def test_pyterrier_uses_serpapi_with_the_legacy_source_label(backend, monkeypatch):
    monkeypatch.setattr(backend, "SEARCH_BACKEND", "pyterrier")
    monkeypatch.setattr(backend, "SERP_AUTOCOMPLETE_CLIENT", "")
    calls = mock_serpapi(backend, monkeypatch, {"suggestions": [
        {"value": "luna piena"}, {}, {"value": 12}, None, {"value": ""},
        {"value": "luna nuova"}, {"value": "luna blu"}, {"value": "luna rossa"},
        {"value": "luna oggi"}, {"value": "luna domani"},
    ]})

    assert backend.autocomplete("luna") == (
        ["luna piena", "luna nuova", "luna blu", "luna rossa", "luna oggi"], "pyterrier"
    )
    assert calls == [{"q": "luna", "engine": "google_autocomplete", "api_key": API_KEY, "hl": "it", "gl": "it"}]


@pytest.mark.parametrize("body", [None, {"suggestions": None}, {"suggestions": []}])
def test_empty_or_malformed_serpapi_response_has_no_source(backend, monkeypatch, body):
    monkeypatch.setattr(backend, "SEARCH_BACKEND", "pyterrier")
    mock_serpapi(backend, monkeypatch, body)
    assert backend.autocomplete("luna") == ([], "none")


@pytest.mark.parametrize(("query", "suggestion", "expected_source"), [
    ("fasi della lna", "fasi della luna", "vertex"),
    ("rocce vulcaniche", "", "none"),
])
def test_vertex_search_uses_the_original_query_with_suggestion_only_correction(
    backend, monkeypatch, query, suggestion, expected_source
):
    def search(request):
        assert request.query == query
        assert request.spell_correction_spec.mode == (
            backend.discoveryengine.SearchRequest.SpellCorrectionSpec.Mode.SUGGESTION_ONLY
        )
        return SimpleNamespace(corrected_query=suggestion, results=[], total_size=0)

    monkeypatch.setattr(backend, "get_search_client", lambda location: SimpleNamespace(search=search))
    assert backend.vertex_search(query, 1, 10, CONFIG) == (suggestion or query, [], 0, expected_source)


def unexpected_provider_call(*args, **kwargs):
    pytest.fail("Unexpected SerpAPI call")


def mock_serpapi(backend, monkeypatch, body):
    calls = []

    def respond(url, params, timeout):
        assert url == "https://serpapi.com/search.json"
        calls.append(params)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(body).encode("utf-8")
        return response

    monkeypatch.setattr(backend.requests, "get", respond)
    return calls
