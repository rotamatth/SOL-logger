"""Provider failures must not leak participant text or credentials into process logs."""
import builtins
import importlib.util
import io
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
    return module


@pytest.mark.parametrize("status", [401, 429])
def test_autocomplete_http_failure_does_not_log_query_or_api_key(backend, monkeypatch, caplog, status):
    monkeypatch.setattr(backend, "get_completion_client", lambda location: SimpleNamespace(
        complete_query=lambda request: SimpleNamespace(query_suggestions=[])))

    def provider_failure(url, params, timeout):
        response = requests.Response()
        response.status_code = status
        response.reason = "Synthetic provider failure"
        response.url = requests.Request("GET", url, params=params).prepare().url
        return response

    monkeypatch.setattr(backend.requests, "get", provider_failure)
    with caplog.at_level(logging.DEBUG, logger=backend.__name__):
        assert backend.vertex_autocomplete(QUERY, CONFIG) == ([], 0)

    assert "HTTPError" in caplog.text
    assert QUERY not in caplog.text and "synthetic+private+participant+query" not in caplog.text
    assert API_KEY not in caplog.text and "https://serpapi.com" not in caplog.text
    assert "api_key=" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("operation", ["search", "autocomplete"])
def test_provider_error_messages_are_not_logged(backend, monkeypatch, caplog, operation):
    error = RuntimeError(f"Provider rejected {QUERY}; https://provider.invalid/?api_key={API_KEY}")

    def fail(request):
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
            assert backend.vertex_autocomplete(QUERY, CONFIG) == ([], 0)

    assert "RuntimeError" in caplog.text
    assert QUERY not in caplog.text and API_KEY not in caplog.text
    assert "https://provider.invalid" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
