"""Enrollment controls retain session context and exact permanent identities."""
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from .test_permanent_participants import change
from .test_research_dashboard import app, configure, csrf, login


YEAR = "2026/2027"
SESSION = "grade-4-session-1"
WORKFLOW = f"/dashboard/settings/enrollment?year={YEAR}&grade=4&prepare_session={SESSION}"


class Controls(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.links = []
        self.forms = []
        self.form = None
        self.link = None
        self.select = None
        self.feed(response.text if hasattr(response, "text") else response)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.form = {"attrs": attrs, "controls": [], "text": ""}
        elif tag in ("input", "select", "textarea", "button") and self.form is not None:
            control = {"tag": tag, **attrs}
            self.form["controls"].append(control)
            if tag == "select":
                control["options"] = []
                self.select = control
        elif tag == "option" and self.select is not None:
            self.select["options"].append(attrs)
        if tag == "a":
            self.link = {**attrs, "href": attrs.get("href", ""), "text": ""}

    def handle_endtag(self, tag):
        if tag == "form" and self.form is not None:
            self.forms.append(self.form)
            self.form = None
        if tag == "a" and self.link is not None:
            self.link["text"] = " ".join(self.link["text"].split())
            self.links.append(self.link)
            self.link = None
        if tag == "select":
            self.select = None

    def handle_data(self, data):
        if self.link is not None:
            self.link["text"] += data
        if self.form is not None:
            self.form["text"] += data


def listed_ids(response):
    ids = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", response.text, re.S):
        cell = re.search(r"<td>(.*?)</td>", row, re.S)
        if cell:
            ids.append(unescape(re.sub(r"<[^>]+>", "", cell[1])).strip())
    return ids


def link(response, label):
    matches = [item["href"] for item in Controls(response).links if item["text"] == label]
    assert len(matches) == 1, matches
    return matches[0]


@pytest.mark.parametrize("query, expected", [("1", ["1"]), ("001", ["001"]),
                                            ("Child-A", ["Child-A"]), ("child-a", [])])
def test_id_filter_matches_the_exact_permanent_id(app, query, expected):
    configure(app)
    state = app.extensions["research"]["state"]
    change(state, "add", ids=["001", "Child-A"], year=YEAR, grade="4")
    client = app.test_client()
    login(client)
    before = state.settings()
    response = client.get(WORKFLOW + "&" + urlencode({"q": query}))
    assert response.status_code == 200
    assert listed_ids(response) == expected
    assert state.settings() == before


@pytest.mark.parametrize("filters", ["&q=missing&status=inactive", "&q=1&status=active&edit=1&page=1"])
def test_clear_filters_keeps_the_session_year_and_class(app, filters):
    configure(app)
    client = app.test_client()
    login(client)
    response = client.get(WORKFLOW + filters)
    assert response.status_code == 200
    destination = link(response, "Clear filters")
    query = parse_qs(urlsplit(destination).query)
    assert query["year"] == [YEAR]
    assert query["grade"] == ["4"]
    assert query["prepare_session"] == [SESSION]
    assert not {"q", "status", "page", "edit"}.intersection(query)
    restored = client.get(destination)
    assert restored.status_code == 200
    assert listed_ids(restored) == [str(number) for number in range(1, 21)]


@pytest.mark.parametrize("url", [WORKFLOW,
    f"/dashboard/settings/questions/{SESSION}?prepare_session={SESSION}"])
def test_global_preparation_link_returns_to_the_selected_session(app, url):
    configure(app)
    client = app.test_client()
    login(client)
    response = client.get(url)
    assert response.status_code == 200
    destination = link(response, "Prepare a session")
    query = parse_qs(urlsplit(destination).query)
    assert query["session"] == [SESSION]
    assert query["grade"] == ["4"]
    assert query["year"] == [YEAR]
    assert client.get(destination).status_code == 200


@pytest.mark.parametrize("edit", [False, True])
def test_workflow_enrollment_forms_keep_the_session_year_fixed(app, edit):
    configure(app)
    client = app.test_client()
    login(client)
    response = client.get(WORKFLOW + ("&edit=1" if edit else ""))
    assert response.status_code == 200
    forms = [form for form in Controls(response).forms
             if any(item.get("name") == "operation" for item in form["controls"])]
    assert forms
    for form in forms:
        years = [item for item in form["controls"] if item.get("name") == "year"]
        assert len(years) == 1
        assert years[0].get("type") == "hidden"
        assert years[0].get("value") == YEAR


def test_failed_existing_id_enrollment_keeps_the_operation_and_help(app):
    configure(app)
    state = app.extensions["research"]["state"]
    client = app.test_client()
    login(client)
    before = state.settings()
    response = client.post(WORKFLOW, data={
        "csrf": csrf(client.get(WORKFLOW)), "revision": before["revision"],
        "operation": "enroll", "ids": "unknown-id", "year": YEAR, "grade": "4",
    })
    assert response.status_code == 400
    assert state.settings() == before
    assert "unknown-id" in response.text
    assert "Children already in the study" in response.text
    assert "Existing IDs cannot be reused" not in response.text
    forms = [form for form in Controls(response).forms
             if any(item.get("name") == "ids" for item in form["controls"])]
    assert len(forms) == 1
    operation = [item for item in forms[0]["controls"] if item.get("name") == "operation"]
    assert len(operation) == 1
    if operation[0]["tag"] == "select":
        assert any(option.get("value") == "enroll" and "selected" in option
                   for option in operation[0]["options"])
    else:
        assert operation[0].get("value") == "enroll"
    assert any(item.get("name") == "year" and item.get("type") == "hidden"
               and item.get("value") == YEAR for item in forms[0]["controls"])
