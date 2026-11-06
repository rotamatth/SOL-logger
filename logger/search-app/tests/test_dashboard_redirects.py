"""Login redirect validation uses synthetic dashboard state only."""
import pytest

from .test_research_dashboard import PASSWORD, app, csrf
from research_dashboard.dashboard import safe_research_next


@pytest.mark.parametrize("destination", ["//[", "https://[invalid", "//example.com\uff0foutside"])
def test_malformed_next_keeps_login_available_and_uses_default_destination(app, destination):
    client = app.test_client()
    response = client.get("/dashboard/login", query_string={"next": destination, "lang": "it"})
    assert response.status_code == 200

    response = client.post("/dashboard/login?lang=it", data={
        "password": PASSWORD, "csrf": csrf(response), "next": destination,
    })
    assert response.status_code == 302
    assert response.location == "/dashboard/guide?lang=it"  # The first sign-in in this browser.

    response = client.get("/dashboard/login", query_string={"next": destination, "lang": "it"})
    assert response.status_code == 302
    assert response.location == "/dashboard/sessions?lang=it"


@pytest.mark.parametrize("destination", [
    "https://example.com/dashboard/prepare", "//example.com/dashboard/prepare",
    "/dashboard-other/prepare", "/dashboard/login", "/dashboard/logout",
    "/dashboard/\\example.com", "/dashboard/prepare\r\nLocation: https://example.com",
    "/dashboard/../welcome", "/dashboard/./prepare", "/dashboard/%2e%2e/welcome", "/dashboard/%2E%2E/%2E%2E/welcome",
    "/dashboard//example.com", "/dashboard/..//example.com", "/dashboard/%2f%2fexample.com", "/dashboard/%5cexample.com",
])
def test_next_refuses_unsafe_or_looping_destinations(destination):
    assert safe_research_next(destination) is None


def test_next_only_inspects_the_path_for_slashes_and_dots():
    destination = "/dashboard/settings?year=2026/2027&note=a//b&up=../c"
    assert safe_research_next(destination) == destination


def test_next_is_rebuilt_from_the_dashboard_prefix():
    assert safe_research_next(" /dashboard/settings?grade=4#top") == "/dashboard/settings?grade=4"


def test_login_preserves_safe_dashboard_path_and_query(app):
    destination = "/dashboard/settings?grade=4&year=2026%2F2027&lang=it"
    client = app.test_client()
    response = client.get("/dashboard/login", query_string={"next": destination})
    response = client.post("/dashboard/login", data={
        "password": PASSWORD, "csrf": csrf(response), "next": destination,
    })
    assert response.status_code == 302
    assert response.location == destination
