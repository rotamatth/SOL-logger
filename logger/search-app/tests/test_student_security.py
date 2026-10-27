"""Student app hardening: escaping, embedded pages, server-side probes and logging privacy."""
import logging

import pytest

from .test_study_enrollment import schedule, student_modules  # noqa: F401 - pytest fixture
from .progress_helpers import confirm_first

HOSTILE_QUERY = '"><script>alert(1)</script> "luna"'


def searching_client(module, results=()):
    """A participant who started today's session and opened the search page."""
    schedule(module)
    module.search_backend.search = lambda query, page, rpp: (query, [dict(r) for r in results], len(results), "none")
    module.search_backend.autocomplete = lambda query: (["should not be called"], "test")
    module.search_backend.autocomplete_query_model = lambda: None
    client = module.app.test_client()
    assert client.post("/start", data={"user_id": "1"}).status_code == 302
    assert client.get("/task").status_code == 200
    confirm_first(client)
    assert client.get("/search").status_code == 200
    return client


def test_search_page_escapes_queries_and_keeps_only_emphasis_from_the_engine(student_modules):
    module = student_modules()
    client = searching_client(module, results=[{
        "docid": 'doc"1', "title": "La <b>Luna</b> &amp; il Sole<img src=x onerror=alert(2)>",
        "snippet": "Le <b>fasi</b> della luna<script>alert(3)</script> &lt;tag&gt;",
        "link": 'https://example.org/a?x="1"', "displayed_link": "example.org<i>"}])
    page = client.post("/result", data={"query": HOSTILE_QUERY}).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;alert(1)" in page
    assert 'data-sanitized-query="&#34;&gt;&lt;script&gt;' in page
    assert "<b>Luna</b> &amp; il Sole&lt;img src=x onerror=alert(2)&gt;" in page
    assert "<b>fasi</b> della luna&lt;script&gt;alert(3)&lt;/script&gt; &lt;tag&gt;" in page
    assert "<img src=x" not in page and "<script>alert(3)" not in page
    assert 'base_ir="doc&#34;1"' in page and 'data-original-url="https://example.org/a?x=&#34;1&#34;"' in page


def test_viewer_opens_only_web_addresses(student_modules):
    module = student_modules()
    client = searching_client(module)
    for url in ("javascript:alert(document.domain)", "data:text/html,<script>1</script>", "JAVASCRIPT:x", ""):
        response = client.get("/webpage", query_string={"url": url})
        assert response.status_code == 302 and response.location.endswith("/search")
    response = client.get("/webpage", query_string={"url": "https://example.org/page"})
    assert response.status_code == 200 and 'src="https://example.org/page"' in response.get_data(as_text=True)


class FakeResponse:
    def __init__(self, status, headers):
        self.status_code, self.headers = status, headers
        self.is_redirect = status in (301, 302, 303, 307, 308)

    def close(self):
        pass


def test_iframe_probe_needs_an_active_search_and_rechecks_every_redirect(student_modules, monkeypatch):
    module = student_modules()
    anonymous = module.app.test_client()
    probed = []
    monkeypatch.setattr(module.requests, "head", lambda url, **kw: probed.append(url) or FakeResponse(200, {}))
    assert anonymous.get("/iframe_check?url=https://example.org/").get_json()["reason"] == "no-active-search"
    assert probed == []

    client = searching_client(module)
    public = [(2, 1, 6, "", ("93.184.216.34", 0))]
    private = [(2, 1, 6, "", ("127.0.0.1", 0))]
    monkeypatch.setattr(module.socket, "getaddrinfo",
                        lambda host, port: private if host == "internal.example" else public)
    monkeypatch.setattr(module.requests, "head", lambda url, **kw: (
        probed.append(url) or FakeResponse(302, {"location": "http://internal.example/admin"})))
    result = client.get("/iframe_check?url=https://example.org/").get_json()
    assert result == {"blocked": None, "reason": "ssrf-rejected:private-ip:127.0.0.1"}
    assert probed == ["https://example.org/"]

    probed.clear()
    monkeypatch.setattr(module.requests, "head", lambda url, **kw: (
        probed.append(url) or FakeResponse(302, {"location": url + "x"})))
    assert client.get("/iframe_check?url=https://example.org/").get_json()["reason"] == "too-many-redirects"
    assert len(probed) == module.IFRAME_PROBE_MAX_REDIRECTS + 1

    monkeypatch.setattr(module.requests, "head", lambda url, **kw: FakeResponse(200, {"X-Frame-Options": "DENY"}))
    assert client.get("/iframe_check?url=https://example.org/").get_json()["blocked"] is True


def test_iframe_probe_refuses_a_malformed_redirect_location(student_modules, monkeypatch):
    module = student_modules()
    client = searching_client(module)
    monkeypatch.setattr(module.socket, "getaddrinfo",
                        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))])
    probed = []
    monkeypatch.setattr(module.requests, "head", lambda url, **kw: (
        probed.append(url) or FakeResponse(302, {"location": "https://[invalid"})))

    response = client.get("/iframe_check", query_string={"url": "https://example.org/"})

    assert response.status_code == 200
    assert response.get_json() == {"blocked": None, "reason": "ssrf-rejected:malformed-url"}
    assert probed == ["https://example.org/"]


def test_iframe_probe_handles_requests_redirect_preparation_errors(student_modules, monkeypatch):
    module = student_modules()
    client = searching_client(module)
    monkeypatch.setattr(module.socket, "getaddrinfo",
                        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))])
    probed = []

    class MalformedRedirectAdapter(module.requests.adapters.BaseAdapter):
        """Exercise real requests redirect preparation without making a network request."""
        def send(self, request, **kwargs):
            probed.append(request.url)
            response = module.requests.Response()
            response.status_code = 302
            response.headers["Location"] = "https://[invalid"
            response.url = request.url
            response.request = request
            response._content = b""
            return response

        def close(self):
            pass

    with module.requests.Session() as request_session:
        request_session.trust_env = False
        request_session.mount("https://", MalformedRedirectAdapter())
        monkeypatch.setattr(module.requests, "head", request_session.head)
        response = client.get("/iframe_check", query_string={"url": "https://example.org/"})

    assert response.status_code == 200
    assert response.get_json() == {"blocked": None, "reason": "request-error:ValueError"}
    assert probed == ["https://example.org/"]


def test_autocomplete_is_only_for_participants_in_a_session(student_modules):
    module = student_modules()
    calls = []
    module.search_backend.autocomplete = lambda query: calls.append(query) or (["luna piena"], "vertex")
    module.search_backend.autocomplete_query_model = lambda: "search-history"
    anonymous = module.app.test_client()
    assert anonymous.get("/autocomplete?query=luna").get_json()["suggestions"] == []
    assert calls == []
    client = searching_client(module)
    module.search_backend.autocomplete = lambda query: calls.append(query) or (["luna piena"], "vertex")
    assert client.get("/autocomplete?query=luna").get_json()["suggestions"] == ["luna piena"]
    assert calls == ["luna"]


def test_autocomplete_failure_keeps_its_fallback_without_logging_private_text(student_modules, caplog):
    module = student_modules()
    client = searching_client(module)
    query = "synthetic private autocomplete query"
    credential = "synthetic-provider-key"

    def broken_autocomplete(value):
        raise RuntimeError(f"Provider failed for {value} with credential {credential}")

    module.search_backend.autocomplete = broken_autocomplete
    with caplog.at_level(logging.WARNING):
        response = client.get("/autocomplete", query_string={"query": query})

    assert response.status_code == 200
    assert response.get_json() == {"suggestions": [], "source": "none", "query_model": None}
    assert "Autocomplete failed" in caplog.text and "RuntimeError" in caplog.text
    assert query not in caplog.text and credential not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_student_responses_have_no_cors_and_safe_headers(student_modules):
    module = student_modules()
    client = module.app.test_client()
    for path in ("/start", "/welcome", "/autocomplete?query=abc"):
        response = client.get(path, headers={"Origin": "https://untrusted.example"})
        assert "Access-Control-Allow-Origin" not in response.headers
        assert "Access-Control-Allow-Credentials" not in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
        assert response.headers["Referrer-Policy"] == "same-origin"
    preflight = client.options("/log_session", headers={"Origin": "https://untrusted.example",
                                                        "Access-Control-Request-Method": "POST"})
    assert "Access-Control-Allow-Origin" not in preflight.headers
    # The dashboard keeps its stricter policy.
    assert module.app.test_client().get("/dashboard/login").headers["X-Frame-Options"] == "DENY"


def test_oversized_uploads_are_refused(student_modules):
    module = student_modules()
    client = searching_client(module)
    body = b'{"logs": "' + b"x" * (16 * 1024 * 1024) + b'"}'
    assert client.post("/log_session", data=body, content_type="application/json").status_code == 413


def test_logging_contract_warnings_never_contain_participant_text(student_modules, caplog):
    module = student_modules()
    answer = "my secret answer about the moon"
    with caplog.at_level(logging.WARNING):
        module.warn_logging_contract_issues([
            {"type": "querySubmitted", "query": answer}, {"type": "querySubmitted", "query": answer},
            {"type": "webpageClosed", "answer": answer},
            {"type": "clickedResult", "query": answer}, "not an object"], "1")
    text = caplog.text
    assert "duplicate consecutive querySubmitted" in text and "webpageClosed missing fields" in text
    assert "SERP event missing query fields" in text and "not an object" in text
    assert answer not in text


@pytest.mark.parametrize("value, expected", [
    ("<b>x</b> &amp; <i>y</i><br/>", "<b>x</b> &amp; <i>y</i><br>"),
    ('<b onclick="x">bad</b>', '&lt;b onclick=&#34;x&#34;&gt;bad<b>'.replace("<b>", "</b>")),
    ("&lt;script&gt;", "&lt;script&gt;"),
    (None, ""),
])
def test_rich_text_filter(student_modules, value, expected):
    module = student_modules()
    assert str(module.rich_text(value)) == expected


def test_malformed_addresses_are_refused_without_a_server_error(student_modules):
    module = student_modules()
    client = searching_client(module)
    for url in ("http://[invalid", "https://[::1/x", "http://", "https:///path-only"):
        response = client.get("/webpage", query_string={"url": url})
        assert response.status_code == 302 and response.location.endswith("/search"), url
    result = client.get("/iframe_check", query_string={"url": "http://[invalid"}).get_json()
    assert result["blocked"] is None and result["reason"] == "ssrf-rejected:malformed-url"


class FakeVertex:
    """Stands in for the Google clients; records nothing, returns fixed text."""
    def __init__(self, **response):
        self.response = type("Response", (), response)()

    def search(self, request):
        return self.response

    def complete_query(self, request):
        return self.response


def test_search_backend_logs_never_contain_queries_or_suggestions(monkeypatch, caplog):
    import search_backend
    config = ("project", "global", "engine", "store", "it", "search-history")
    secret = "la mia domanda segreta"
    monkeypatch.setattr(search_backend, "get_search_client", lambda location: FakeVertex(
        corrected_query=secret + " corretta", results=[], total_size=0))
    suggestion = type("Suggestion", (), {"suggestion": secret + " suggerita"})()
    monkeypatch.setattr(search_backend, "get_completion_client", lambda location: FakeVertex(
        query_suggestions=[suggestion]))
    with caplog.at_level(logging.DEBUG, logger="search_backend"):
        corrected, results, total, source = search_backend.vertex_search(secret, 1, 10, config)
        suggestions, fallback = search_backend.vertex_autocomplete(secret, config)
    assert (corrected, results, total, source) == (secret + " corretta", [], 0, "vertex")
    assert (suggestions, fallback) == ([secret + " suggerita"], 0)
    assert caplog.records and secret not in caplog.text


def test_unconfigured_or_failing_vertex_search_raises_for_the_error_page(monkeypatch):
    import search_backend

    class Broken:
        def search(self, request):
            raise RuntimeError("503 unavailable")

    with pytest.raises(RuntimeError):
        search_backend.vertex_search("luna", 1, 10, ("", "global", "", "", "it"))
    monkeypatch.setattr(search_backend, "get_search_client", lambda location: Broken())
    with pytest.raises(RuntimeError):
        search_backend.vertex_search("luna", 1, 10, ("p", "global", "e", "s", "it"))
    assert search_backend.vertex_autocomplete("luna", ("", "global", "", "", "it")) == ([], 0)
