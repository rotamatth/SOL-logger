"""Preparation selectors and question actions work as ordinary submitted links/forms."""
from urllib.parse import parse_qs, urlsplit
import re

import pytest

from .test_enrollment_controls import Controls, SESSION, YEAR
from .test_research_dashboard import app, configure, login
from .test_study_enrollment import question_set


PREP = f"/dashboard/prepare?grade=4&year={YEAR}&session={SESSION}"


def picker(response):
    return next(form for form in Controls(response).forms
                if "preparation-picker" in form["attrs"].get("class", "").split())


def submit_choice(client, response, name, value, **changes):
    form = picker(response)
    choice = next(control for control in form["controls"]
                  if control["tag"] == "button" and control.get("name") == name
                  and control.get("value") == value)
    fields = {control["name"]: control.get("value", "") for control in form["controls"]
              if control["tag"] == "input" and control.get("name")}
    fields.update(changes)
    fields[choice["name"]] = choice["value"]
    return client.get(urlsplit(form["attrs"]["action"]).path, query_string=fields)


def test_class_choice_submits_and_opens_the_new_class_without_a_second_action(app):
    configure(app)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    before = state.settings()
    page = client.get(PREP)
    form = picker(page)
    assert {control.get("value") for control in form["controls"]
            if control["tag"] == "button" and control.get("name") == "select_grade"} == {"3", "4", "5"}
    assert not any(control["tag"] == "select" and control.get("name") == "grade"
                   for control in form["controls"])
    changed = submit_choice(client, page, "select_grade", "3", session=SESSION)
    assert changed.status_code == 200
    assert any(control.get("name") == "grade" and control.get("value") == "3"
               for control in picker(changed)["controls"])
    assert f"prepare_session={SESSION}" not in changed.text
    assert state.settings() == before


def test_every_session_choice_opens_its_own_date_and_details(app):
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
    page = client.get(PREP)
    offered = {control.get("value") for control in picker(page)["controls"]
               if control["tag"] == "button" and control.get("name") == "session"}
    assert {item["id"] for item in sessions} <= offered
    assert not any(control["tag"] == "select" and control.get("name") == "session"
                   for control in picker(page)["controls"])
    for item in sessions:
        opened = submit_choice(client, page, "session", item["id"])
        assert opened.status_code == 200
        controls = [control for form in Controls(opened).forms for control in form["controls"]]
        assert any(control.get("name") == "name" and control.get("value") == item["name"]
                   for control in controls)
        assert any(control.get("name") == "date" and control.get("value") == item["date"]
                   for control in controls)
        assert f"prepare_session={item['id']}" in opened.text
    assert state.settings() == before


def test_current_class_is_marked_without_offering_a_jump_to_another_session(app):
    configure(app)
    client = app.test_client()
    login(client)
    choices = [control for control in picker(client.get(PREP))["controls"]
               if control["tag"] == "button" and control.get("name") == "select_grade"]
    current = next(control for control in choices if control.get("value") == "4")
    assert "disabled" in current and current.get("aria-current") == "true"
    assert all("disabled" not in control for control in choices if control is not current)


def test_opening_another_year_discards_a_session_from_the_previous_year(app):
    configure(app)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    before = state.settings()
    result = submit_choice(client, client.get(PREP), "session", SESSION, year="2027/2028")
    assert result.status_code == 200
    assert any(control.get("name") == "year" and control.get("value") == "2027/2028"
               for control in picker(result)["controls"])
    assert f"prepare_session={SESSION}" not in result.text
    assert state.settings() == before


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
