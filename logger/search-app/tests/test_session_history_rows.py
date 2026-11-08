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


def test_the_experiment_shows_each_class_theme_and_questions(client):
    sessions = client.get("/dashboard/sessions?year=2025/2026&lang=it").text
    assert "Tema: India" in sessions and "Tema: Spazio" in sessions
    third = client.get("/dashboard?collection=study&grade=3&school_year=2025/2026&lang=it").text
    assert "Tema: <strong>India</strong>" in third and "Bandiera India simbolo" in third
    assert "Come si chiama il fiume sacro agli indiani?" in third and "Altre galassie" not in third
    fourth = client.get("/dashboard?collection=study&grade=4&school_year=2025/2026&lang=it").text
    # May's 4th class had space, with the questions this year's 4th class has again.
    assert "Tema: <strong>Spazio</strong>" in fourth and "Sistema solare Giove" in fourth
    assert "Quali sono i nomi di altre 3 galassie oltre la nostra?" in fourth and "India" not in fourth
    assert "Esperimento 19 maggio" not in client.get("/dashboard?collection=study&grade=4&school_year=2026/2027&lang=it").text


def test_ids_with_different_questions_get_no_theme(client, app):  # noqa: F811
    state = app.extensions["research"]["state"]
    settings = state.settings()
    settings["historical_grades"] = [{**MAY[0], "start": 1, "end": 12}]  # India for 1-8, space for 9-12.
    state.save_settings(settings, settings["revision"])
    page = client.get("/dashboard?collection=study&grade=3&school_year=2025/2026&lang=it").text
    assert "Tema:" not in page and "Bandiera India simbolo" not in page
