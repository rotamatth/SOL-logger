"""A past experiment known only from its logs is listed in Sessions, without a session number."""
import pytest

from .test_research_dashboard import app, configure, login  # noqa: F401

MAY = [{"id": f"{n:024x}", "grade": grade, "collection": "legacy", "school_year": "2025/2026", "date_from": "2026-05-19",
        "date_to": "2026-05-19", "start": start, "end": end, "prefix": "", "width": 0}
       for n, (grade, start, end) in enumerate((("3", 1, 8), ("3", 17, 18), ("4", 9, 16)))]


@pytest.fixture
def client(app):  # noqa: F811
    settings = configure(app)
    state = app.extensions["research"]["state"]
    settings = state.settings()
    settings["historical_grades"] = MAY
    state.save_settings(settings, settings["revision"])
    client = app.test_client()
    login(client)
    return client


def test_the_year_of_the_experiment_lists_it_per_class_and_links_to_its_data(client):
    page = client.get("/dashboard/sessions?year=2025/2026&lang=it").text
    assert page.count("Esperimento 19 maggio") >= 2
    assert "grade=3" in page and "school_year=2025/2026" in page
    assert "10 ID" in page and "8 ID" in page
    assert "Nessuna sessione ancora" not in page
    assert 'id="past-sessions" open' in page


def test_the_class_filter_and_other_years_leave_it_out(client):
    one_class = client.get("/dashboard/sessions?year=2025/2026&grade=4&lang=en").text
    assert one_class.count("19 May experiment") >= 1 and "grade=3&amp;school_year=2025/2026" not in one_class
    assert "19 May experiment" not in client.get("/dashboard/sessions?year=2026/2027&lang=en").text


def test_listing_it_takes_no_session_number(client, app):  # noqa: F811
    client.get("/dashboard/sessions?year=2025/2026")
    assert not any(item["school_year"] == "2025/2026" for item in app.extensions["research"]["state"].settings()["sessions"]
                   if item.get("school_year"))
