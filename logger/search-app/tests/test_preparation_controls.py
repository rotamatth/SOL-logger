"""Preparation selectors and question actions work as ordinary submitted links/forms."""
from urllib.parse import parse_qs, urlsplit
import re

import pytest

from .test_enrollment_controls import Controls, SESSION, YEAR
from .test_research_dashboard import app, configure, login
from .test_study_enrollment import question_set


PREP = f"/dashboard/prepare?grade=4&year={YEAR}&session={SESSION}"


def test_the_session_page_has_no_menus_and_links_back_to_the_list(app):
    configure(app)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    before = state.settings()
    page = client.get(PREP)
    assert "preparation-picker" not in page.text and "select_grade" not in page.text
    back = next(link for link in Controls(page).links if link["text"] == "← Back to Sessions")
    assert urlsplit(back["href"]).path == "/dashboard/sessions"
    assert parse_qs(urlsplit(back["href"]).query)["year"] == [YEAR] and urlsplit(back["href"]).fragment == SESSION
    assert f'id="{SESSION}"' in client.get(back["href"]).text
    assert state.settings() == before


def test_every_listed_session_opens_its_own_date_and_details(app):
    configure(app)
    state = app.extensions["research"]["state"]
    settings = state.settings()
    sessions = [item for item in settings["sessions"] if item["grade"] == "4"]
    for item in sessions:
        item["name"] = f"Visit {item['number']}"
    state.save_settings(settings, settings["revision"])
    client = app.test_client()
    login(client)
    before = state.settings()
    listed = client.get(f"/dashboard/sessions?grade=4&year={YEAR}")
    for item in sessions:
        link = next(link for link in Controls(listed).links
                    if link["text"] == item["name"])
        opened = client.get(link["href"])
        assert opened.status_code == 200
        controls = [control for form in Controls(opened).forms for control in form["controls"]]
        assert any(control.get("name") == "name" and control.get("value") == item["name"]
                   for control in controls)
        assert any(control.get("name") == "date" and control.get("value") == item["date"]
                   for control in controls)
        assert f"prepare_session={item['id']}" in opened.text
    assert state.settings() == before


def test_a_session_from_another_year_is_not_opened_under_this_year(app):
    configure(app)
    client = app.test_client()
    login(client)
    assert client.get(f"/dashboard/prepare?grade=4&year=2027/2028&session={SESSION}").status_code == 404


@pytest.mark.parametrize("url", [PREP, f"/dashboard/settings/questions/{SESSION}?prepare_session={SESSION}"])
def test_question_tables_label_shared_and_individual_actions_with_the_id(app, url):
    configure(app)
    state = app.extensions["research"]["state"]
    settings = state.settings()
    settings["sessions"][0].update(question_set=question_set(), participant_questions={"2": question_set()})
    state.save_settings(settings, settings["revision"])
    client = app.test_client()
    login(client)
    before = state.settings()
    page = client.get(url)
    assert page.status_code == 200
    headers = re.findall(r"<thead\b[^>]*>(.*?)</thead>", page.text, re.S)
    assert len(headers) == 1
    headings = [re.sub(r"<[^>]+>", "", text).strip()
                for text in re.findall(r"<th\b[^>]*>(.*?)</th>", headers[0], re.S)]
    assert headings == ["ID", "Questions", "Configuration", "Actions"]
    for uid, expected in (("1", "Personalize"), ("2", "Edit")):
        matches = [anchor for anchor in Controls(page).links
                   if parse_qs(urlsplit(anchor["href"]).query).get("participant") == [uid]]
        assert len(matches) == 1
        action = matches[0]
        assert action["text"] == expected
        assert uid in action.get("aria-label", "")
        query = parse_qs(urlsplit(action["href"]).query)
        assert query["prepare_session"] == [SESSION]
        assert urlsplit(action["href"]).path.endswith("/" + SESSION)
        assert client.get(action["href"]).status_code == 200
    assert state.settings() == before
