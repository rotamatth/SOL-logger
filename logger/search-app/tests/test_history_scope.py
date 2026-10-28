"""History controls and exports retain the explicitly selected study context."""
from html import unescape
import json
import re
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from .test_dashboard_filters import rendered_context, selection_form, write_year_run
from .test_enrollment_controls import Controls
from .test_research_dashboard import add_history_rule, app, archive, configure, identity, login, write_run


YEAR = "2026/2027"
SESSION = "grade-4-session-1"
VIEW = f"/dashboard?collection=study&grade=4&school_year={YEAR}&session={SESSION}"


def named_link(response, label):
    matches = [link["href"] for link in Controls(response).links if link["text"] == label]
    assert len(matches) == 1, matches
    return matches[0]


def choose_year(client, response, year):
    form = next(form for form in Controls(response).forms
                if any(control.get("name") == "school_year" and control["tag"] == "button"
                       for control in form["controls"]))
    assert any(control.get("value") == year and control.get("name") == "school_year"
               for control in form["controls"])
    values = {control["name"]: control.get("value", "") for control in form["controls"]
              if control["tag"] == "input" and control.get("name")}
    values["school_year"] = year
    return client.get(urlsplit(form["attrs"]["action"]).path, query_string=values)


def test_preparation_history_and_settings_links_retain_the_selected_session(app):
    configure(app)
    state = app.extensions["research"]["state"]
    before = state.settings()
    client = app.test_client()
    login(client)
    prep = client.get(f"/dashboard/prepare?grade=4&year={YEAR}&session={SESSION}")
    destination = named_link(prep, "Data and history")
    assert parse_qs(urlsplit(destination).query) == {
        "collection": ["study"], "grade": ["4"], "school_year": [YEAR],
        "session": [SESSION], "lang": ["en"],
    }
    history = client.get(destination)
    assert history.status_code == 200
    for response in (prep, history):
        returning = parse_qs(urlsplit(named_link(response, "Prepare a session")).query)
        assert returning["grade"] == ["4"] and returning["year"] == [YEAR]
        assert returning["session"] == [SESSION]
    settings_url = named_link(history, "Study settings")
    settings = client.get(settings_url)
    assert settings.status_code == 200
    back = next(link["href"] for link in Controls(settings).links
                if link["text"] == "← Prepare a session")
    assert parse_qs(urlsplit(back).query)["session"] == [SESSION]
    assert state.settings() == before


def test_known_future_year_can_be_opened_without_collected_records(app):
    configure(app)
    state = app.extensions["research"]["state"]
    new_session = state.add_study_session("4", "2027-10-20", state.settings()["revision"],
                                          school_year="2027/2028")
    before = state.settings()
    client = app.test_client()
    login(client)
    with rendered_context(app) as contexts:
        future = client.get("/dashboard?" + urlencode({
            "collection": "study", "grade": "4", "school_year": "2027/2028", "session": new_session["id"],
        }))
    assert future.status_code == 200
    assert "2027/2028" in future.text
    assert contexts[-1]["people"] == [] and contexts[-1]["downloadable_count"] == 0
    assert state.settings() == before


def test_all_years_history_returns_to_the_sessions_own_preparation_year(app):
    configure(app)
    state = app.extensions["research"]["state"]
    settings = state.settings()
    settings["current_school_year"] = "2027/2028"
    state.save_settings(settings, settings["revision"])
    client = app.test_client()
    login(client)
    response = client.get(f"/dashboard?collection=study&grade=4&session={SESSION}")
    assert response.status_code == 200
    back = named_link(response, "Prepare a session")
    query = parse_qs(urlsplit(back).query)
    assert query["year"] == [YEAR] and query["session"] == [SESSION]
    assert client.get(back).status_code == 200
    history = parse_qs(urlsplit(named_link(response, "Data and history")).query)
    assert "school_year" not in history  # All-years history remains an explicit scope.


def test_year_menu_clears_a_session_from_another_year_and_all_years_is_explicit(app):
    configure(app)
    state = app.extensions["research"]["state"]
    new_session = state.add_study_session("4", "2027-10-20", state.settings()["revision"],
                                          school_year="2027/2028")
    client = app.test_client()
    login(client)
    response = client.get(VIEW)
    assert response.status_code == 200
    changed = choose_year(client, response, "2027/2028")
    assert changed.status_code == 200
    session_buttons = [control["value"] for form in Controls(changed).forms for control in form["controls"]
                       if control["tag"] == "button" and control.get("name") == "session"]
    assert new_session["id"] in session_buttons and SESSION not in session_buttons
    restored = choose_year(client, changed, "")
    assert restored.status_code == 200
    assert "All years" in restored.text and "All sessions" in restored.text
    assert any(control.get("value") == SESSION for form in Controls(restored).forms
               for control in form["controls"] if control.get("name") == "session")


def test_primary_download_is_scoped_while_complete_grade_history_is_explicit(app):
    configure(app)
    current = write_year_run(app)
    second_session = write_year_run(app, date="2026-10-02", suffix="second")
    previous_year = write_year_run(app, school_year="2025/2026", suffix="previous")
    write_year_run(app, uid="21")
    client = app.test_client()
    login(client)
    response = client.get(VIEW)
    assert response.status_code == 200
    primary = named_link(response, "Download this view")
    query = parse_qs(urlsplit(primary).query)
    assert query["school_year"] == [YEAR] and query["session"] == [SESSION]
    downloaded = client.get(primary)
    _, manifest = archive(downloaded)
    assert {run["run_id"] for run in manifest["runs"]} == {current}
    assert manifest["selection"]["school_year"] == YEAR
    assert "2026-2027" in downloaded.headers["Content-Disposition"]
    full = next(link["href"] for link in Controls(response).links
                if "All years" in link["text"] and "/exports/grade?" in link["href"])
    assert not {"school_year", "session"}.intersection(parse_qs(urlsplit(full).query))
    _, all_history = archive(client.get(full))
    assert {run["run_id"] for run in all_history["runs"]} == {current, second_session, previous_year}


def test_all_grades_download_uses_only_the_visible_year(app):
    configure(app)
    current = write_year_run(app)
    fifth_grade = write_year_run(app, uid="21")
    write_year_run(app, school_year="2025/2026", suffix="previous")
    client = app.test_client()
    login(client)
    page = client.get(f"/dashboard?collection=study&grade=all&school_year={YEAR}")
    assert page.status_code == 200
    _, fields = selection_form(page)
    fields["mode"] = "visible"
    _, manifest = archive(client.post("/dashboard/exports/selection", data=fields))
    assert {run["run_id"] for run in manifest["runs"]} == {current, fifth_grade}
    assert manifest["selection"]["school_year"] == YEAR


@pytest.mark.parametrize("path", ["/dashboard?collection=study&grade=4&school_year=bad",
                                   "/dashboard/exports/grade?collection=study&grade=4&school_year=bad"])
def test_invalid_year_scopes_are_rejected(app, path):
    configure(app)
    write_year_run(app)
    client = app.test_client()
    login(client)
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("collection", ["study", "v2", "legacy"])
def test_participant_breadcrumb_preserves_the_collection_year_and_session(app, collection):
    configure(app)
    if collection == "legacy":
        add_history_rule(app.extensions["research"]["state"], grade="4", school_year=YEAR,
                         date_from="2026-09-01", date_to="2027-08-31")
        write_run(app, collection="legacy", metadata=False)
    else:
        write_year_run(app)
    client = app.test_client()
    login(client)
    response = client.get(f"/dashboard/participants/{collection}/{identity('1')}"
                          f"?grade=4&school_year={YEAR}&session={SESSION}&view=logs&lang=it")
    assert response.status_code == 200
    breadcrumb = re.search(r'<p class="breadcrumbs"><a href="([^"]+)"', response.text).group(1)
    assert parse_qs(urlsplit(unescape(breadcrumb)).query) == {
        "collection": [collection], "grade": ["4"], "school_year": [YEAR],
        "session": [SESSION], "lang": ["it"],
    }
    returning = client.get(unescape(breadcrumb))
    assert returning.status_code == 200


def test_participant_year_scope_excludes_sessions_from_other_years(app):
    configure(app)
    write_year_run(app)
    state = app.extensions["research"]["state"]
    future = state.add_study_session("4", "2027-10-20", state.settings()["revision"],
                                     school_year="2027/2028")
    client = app.test_client()
    login(client)
    path = f"/dashboard/participants/study/{identity('1')}?grade=4&school_year={YEAR}&view=logs"
    response = client.get(path)
    assert response.status_code == 200
    assert f'value="{SESSION}"' in response.text
    assert f'value="{future["id"]}"' not in response.text
    assert "2027-10-20" not in response.text
    assert client.get(path + "&session=" + future["id"]).status_code == 404
    all_years = client.get(f"/dashboard/participants/study/{identity('1')}?grade=4&view=logs")
    assert all_years.status_code == 200 and f'value="{future["id"]}"' in all_years.text


def test_participant_year_scope_keeps_recorded_sessions_after_configuration_moves_year(app):
    settings = configure(app)
    key, root, stem = write_run(app)
    sidecar = root / f"{stem}.run.json"
    metadata = json.loads(sidecar.read_text())
    snapshot = settings["sessions"][0]
    metadata.update(school_year_at_collection=YEAR, study_session_at_collection=SESSION,
                    study_session_snapshot=snapshot)
    sidecar.write_text(json.dumps(metadata))
    settings["sessions"][0].update(school_year="2027/2028", date="2027-10-01")
    state = app.extensions["research"]["state"]
    state.save_settings(settings, settings["revision"])
    client = app.test_client()
    login(client)
    response = client.get(f"/dashboard/participants/study/{identity('1')}"
                          f"?grade=4&school_year={YEAR}&session={SESSION}&view=logs")
    assert response.status_code == 200
    assert key in response.text and "2026-10-01" in response.text
    assert "2027-10-01" not in response.text


def test_selected_session_breadcrumb_uses_its_grade_for_a_promoted_participant(app):
    configure(app)
    write_year_run(app)
    _, root, stem = write_run(app, date="2025-10-01", suffix="prior-year")
    sidecar = root / f"{stem}.run.json"
    metadata = json.loads(sidecar.read_text())
    metadata.update(grade_at_collection="3", school_year_at_collection="2025/2026")
    sidecar.write_text(json.dumps(metadata))
    state = app.extensions["research"]["state"]
    state.add_study_session("3", "2025-10-01", state.settings()["revision"], school_year="2025/2026")
    client = app.test_client()
    login(client)
    response = client.get(f"/dashboard/participants/study/{identity('1')}?session={SESSION}&view=logs")
    assert response.status_code == 200
    breadcrumb = unescape(re.search(r'<p class="breadcrumbs"><a href="([^"]+)"', response.text).group(1))
    query = parse_qs(urlsplit(breadcrumb).query)
    assert query["grade"] == ["4"] and query["session"] == [SESSION]
    assert client.get(breadcrumb).status_code == 200
