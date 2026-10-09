"""The research overview keeps participant selection and grade downloads explicit."""
from contextlib import contextmanager
from html import unescape
import json
import re
from urllib.parse import parse_qs, urlsplit

from flask import template_rendered
import pytest

from .test_research_dashboard import app, archive, configure, csrf, identity, login, write_run


@contextmanager
def rendered_context(app):
    contexts = []

    def record(sender, template, context, **extra):
        contexts.append(context)

    template_rendered.connect(record, app)
    try:
        yield contexts
    finally:
        template_rendered.disconnect(record, app)


def overview_context(app, client, query):
    with rendered_context(app) as contexts:
        response = client.get("/dashboard?" + query)
    assert response.status_code == 200
    return contexts[-1]


def write_year_run(app, school_year="2026/2027", **values):
    key, root, stem = write_run(app, **values)
    path = root / f"{stem}.run.json"
    metadata = json.loads(path.read_text())
    metadata["school_year_at_collection"] = school_year
    path.write_text(json.dumps(metadata))
    return key


def selection_form(response):
    form = next(form for form in re.findall(r'<form\b.*?</form>', response.text, re.S)
                if '/exports/selection' in form)
    fields = {name: unescape(value) for name, value in re.findall(
        r'<input type="hidden" name="([^"]+)" value="([^"]*)">', form)}
    return form, fields


@pytest.mark.parametrize("obsolete_status", ["completed", "no_data", "unknown", "", "complete"])
def test_obsolete_search_and_status_urls_never_hide_participants(app, obsolete_status):
    configure(app)
    write_run(app)
    write_run(app, suffix="repeat", answers=1)
    write_run(app, uid="2")
    client = app.test_client()
    login(client)
    context = overview_context(app, client, "grade=4&q=2026&status=" + obsolete_status)
    assert [person["id"] for person in context["people"]] == [str(n) for n in range(1, 21)]
    assert context["downloadable_count"] == 2
    assert {person["id"]: person["dashboard_status"] for person in context["people"][:3]} == {
        "1": "incomplete", "2": "completed", "3": "no_data"}
    assert not {"q", "status_filter", "status_counts"}.intersection(context)


def test_row_status_still_uses_the_selected_session_and_school_year(app):
    configure(app)
    write_year_run(app)
    write_year_run(app, suffix="later", date="2026-10-02", answers=1)
    client = app.test_client()
    login(client)
    all_sessions = overview_context(app, client, "grade=4")
    assert all_sessions["people"][0]["dashboard_status"] == "incomplete"
    first_session = overview_context(app, client, "grade=4&session=grade-4-session-1")
    assert first_session["people"][0]["dashboard_status"] == "completed"
    assert len(first_session["people"]) == 20
    year_only = overview_context(app, client, "grade=4&school_year=2026/2027")
    assert len(year_only["people"]) == 1
    assert year_only["people"][0]["dashboard_status"] == "incomplete"


def test_overview_keeps_visualization_selection_and_grade_downloads_without_filter_panels(app):
    configure(app)
    write_year_run(app)
    write_year_run(app, uid="2")
    client = app.test_client()
    login(client)
    response = client.get("/dashboard?grade=4&q=2026&status=completed")
    assert response.status_code == 200
    for obsolete in ('id="participant-search"', 'class="dashboard-filters', 'class="dashboard-stats',
                     'id="session-filter"', 'id="school-year-filter"', 'name="q"', 'name="status"',
                     'Download filtered results', 'Download visible', 'Other downloads'):
        assert obsolete not in response.text
    form, fields = selection_form(response)
    assert fields["grade"] == "4" and fields["collection"] == "study"
    form_id = re.search(r'\bid="([^"]+)"', form).group(1)
    selected = re.search(r'<button\b[^>]*value="selected"[^>]*>.*?</button>', response.text, re.S)
    assert selected and "Download selected" in selected.group()
    assert f'form="{form_id}"' in selected.group()
    assert 'value="visible"' not in response.text
    assert '/exports/grade?' in response.text
    checkboxes = re.findall(r'<input type="checkbox"[^>]*>', response.text)
    assert len(checkboxes) == 2
    assert all(f'form="{form_id}"' in checkbox and 'name="participant"' in checkbox
               and "disabled" not in checkbox for checkbox in checkboxes)
    assert {re.search(r'value="([^"]+)"', checkbox).group(1) for checkbox in checkboxes} == {
        "v2:" + identity("1"), "v2:" + identity("2")}
    for row in re.findall(r"<tr>(.*?)</tr>", response.text, re.S):
        if 'type="checkbox"' not in row:
            continue
        direct_actions = re.sub(r"<details\b.*?</details>", "", row, flags=re.S)
        assert "Visualize logs" in direct_actions
        assert "/exports/" not in row
    assert 'Logs available' in response.text and 'No saved data' in response.text
    italian = client.get("/dashboard?grade=4&lang=it")
    assert "Scarica i selezionati" in italian.text


def test_multiple_selected_participants_download_only_their_logs_and_keep_original_bytes(app):
    configure(app)
    first = write_year_run(app)
    eleventh = write_year_run(app, uid="11")
    unchecked = write_year_run(app, uid="12")
    incomplete = write_year_run(app, uid="13", answers=1)
    other = write_year_run(app, uid="2")
    later = write_year_run(app, suffix="later", date="2026-10-02")
    previous_year = write_year_run(app, suffix="previous-year", school_year="2025/2026")
    write_year_run(app, uid="21")
    client = app.test_client()
    login(client)
    response = client.get(
        "/dashboard?grade=4&collection=study&school_year=2026/2027"
        "&session=grade-4-session-1&q=1&status=completed")
    assert response.status_code == 200
    _, fields = selection_form(response)
    assert {name: fields[name] for name in ("collection", "grade", "school_year", "session")} == {
        "collection": "study", "grade": "4", "school_year": "2026/2027", "session": "grade-4-session-1"}
    assert not {"q", "status"}.intersection(fields)
    fields.update(mode="selected", participant=["v2:" + identity("1"), "v2:" + identity("11")])
    selected_zip, selected = archive(client.post("/dashboard/exports/selection", data=fields))
    assert {run["run_id"] for run in selected["runs"]} == {first, eleventh}
    assert selected["selection"] == {
        "collection": "study", "grade": "4", "school_year": "2026/2027",
        "study_session_id": "grade-4-session-1", "mode": "selected", "participant_count": 2}
    original_events = [json.loads(line) for name in selected_zip.namelist() if name.endswith(".log")
                       for line in selected_zip.read(name).splitlines()]
    assert {event["uid"] for event in original_events} == {"1", "11"}
    download_links = [urlsplit(unescape(value)) for value in re.findall(r'href="([^"]+)"', response.text)]
    session_link = next(link for link in download_links if link.path.endswith("/exports/grade_session"))
    assert parse_qs(session_link.query)["school_year"] == ["2026/2027"]
    _, whole_session = archive(client.get(session_link.geturl()))
    assert {run["run_id"] for run in whole_session["runs"]} == {first, eleventh, unchecked, incomplete, other}
    grade_link = next(link for link in download_links if link.path.endswith("/exports/grade"))
    assert not {"q", "status", "session", "school_year"}.intersection(parse_qs(grade_link.query))
    _, whole_grade = archive(client.get(grade_link.geturl()))
    assert {run["run_id"] for run in whole_grade["runs"]} == {
        first, eleventh, unchecked, incomplete, other, later, previous_year}


@pytest.mark.parametrize("mode", ["selected", "visible"])
def test_obsolete_filter_fields_do_not_narrow_or_reject_exports(app, mode):
    configure(app)
    first = write_run(app)[0]
    second = write_run(app, uid="2", answers=1)[0]
    write_run(app, uid="21")
    client = app.test_client()
    login(client)
    form = {"csrf": csrf(client.get("/dashboard")), "collection": "study", "grade": "4",
            "mode": mode, "participant": "v2:" + identity("2"), "q": "2026", "status": "obsolete"}
    _, manifest = archive(client.post("/dashboard/exports/selection", data=form))
    assert {run["run_id"] for run in manifest["runs"]} == ({second} if mode == "selected" else {first, second})
    assert not {"q", "status"}.intersection(manifest["selection"])
    form.update(mode="selected", participant="v2:" + identity("21"))
    assert client.post("/dashboard/exports/selection", data=form).status_code == 400


def test_refresh_preserves_collection_scope_and_drops_obsolete_filters(app):
    configure(app)
    write_year_run(app)
    client = app.test_client()
    login(client)
    fields = {"csrf": csrf(client.get("/dashboard")), "collection": "study", "grade": "4",
              "school_year": "2026/2027", "session": "grade-4-session-1",
              "q": "2026", "status": "obsolete"}
    response = client.post("/dashboard/refresh?lang=it", data=fields)
    assert response.status_code == 302
    assert parse_qs(urlsplit(response.location).query) == {
        "collection": ["study"], "grade": ["4"], "school_year": ["2026/2027"],
        "session": ["grade-4-session-1"], "lang": ["it"]}


def test_scoped_links_keep_context_in_exports_and_provide_a_clean_overview_link(app):
    configure(app)
    write_year_run(app)
    client = app.test_client()
    login(client)
    response = client.get(
        "/dashboard?grade=4&collection=study&school_year=2026/2027"
        "&session=grade-4-session-1&q=1&status=completed&lang=it")
    assert response.status_code == 200
    assert '2026/2027' in response.text and 'Sessione 1' in response.text
    assert 'id="session-filter"' not in response.text and 'id="school-year-filter"' not in response.text
    _, fields = selection_form(response)
    assert fields["school_year"] == "2026/2027" and fields["session"] == "grade-4-session-1"
    links = [urlsplit(unescape(value)) for value in re.findall(r'href="([^"]+)"', response.text)]
    overview_links = [link for link in links if link.path.rstrip("/") == "/dashboard"]
    assert any(parse_qs(link.query).get("grade") == ["4"]
               and not {"school_year", "session", "q", "status"}.intersection(parse_qs(link.query))
               for link in overview_links)
    assert all(not {"q", "status"}.intersection(parse_qs(link.query)) for link in links)
