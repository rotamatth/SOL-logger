"""Several children can be deactivated in one reviewed step, without losing anything."""
import re

import pytest

from .test_enrollment_controls import Controls
from .test_permanent_participants import change
from .test_research_dashboard import app, configure, csrf, identity, login, write_run  # noqa: F401
from research_dashboard.state import roster

YEAR = "2026/2027"
SESSION = "grade-4-session-1"
REGISTER = f"/dashboard/settings/enrollment?year={YEAR}&grade=4&lang=en"
WORKFLOW = f"/dashboard/settings/enrollment?year={YEAR}&grade=4&prepare_session={SESSION}&lang=en"


def signed_in(app):
    configure(app)
    client = app.test_client()
    login(client)
    return client, app.extensions["research"]["state"]


def review(client, state, ids, url=REGISTER, **extra):
    page = client.get(url)
    return client.post(url, data={"csrf": csrf(page), "revision": state.settings()["revision"],
                                  "operation": "deactivate", "year": YEAR, "ids": ids, **extra})


def confirm(client, url, response):
    token = next(item["value"] for form in Controls(response).forms for item in form["controls"]
                 if item.get("name") == "review_token")
    return client.post(url, data={"csrf": csrf(response), "action": "confirm", "review_token": token})


def test_review_lists_the_ids_and_changes_nothing_until_confirmed(app):
    client, state = signed_in(app)
    before = state.settings()
    response = review(client, state, ["1", "2", "3"])
    assert response.status_code == 200
    assert "Deactivate participants" in response.text and "1, 2, 3" in response.text
    assert state.settings() == before
    saved = confirm(client, REGISTER, response)
    assert saved.status_code == 302
    after = state.settings()
    assert all(not after["participant_registry"][uid]["active"] for uid in ("1", "2", "3"))
    assert after["participant_registry"]["4"]["active"]
    assert not {"1", "2", "3"} & set(roster(after))


def test_one_selected_id_works_like_several(app):
    client, state = signed_in(app)
    assert confirm(client, REGISTER, review(client, state, "1")).status_code == 302
    assert not state.settings()["participant_registry"]["1"]["active"]


def test_enrollments_keys_and_records_stay(app):
    client, state = signed_in(app)
    key, _, _ = write_run(app)
    before = state.settings()
    assert confirm(client, REGISTER, review(client, state, ["1", "2"])).status_code == 302
    after = state.settings()
    assert after["enrollments"] == before["enrollments"]
    assert {uid: person["key"] for uid, person in after["participant_registry"].items()} == {
        uid: person["key"] for uid, person in before["participant_registry"].items()}
    assert key in client.get(f"/dashboard/participants/study/{identity('1')}?view=logs").text


def test_each_id_gets_its_own_line_in_the_change_history(app):
    client, state = signed_in(app)
    assert confirm(client, REGISTER, review(client, state, ["1", "2"])).status_code == 302
    entry = state.participant_changes()[0]
    assert entry["operation"] == "deactivate" and entry["school_year"] == YEAR
    assert [row["id"] for row in entry["changes"]] == ["1", "2"]
    assert entry["changes"][0]["before"] == [("grade", "4"), ("status", True)]
    assert entry["changes"][0]["after"] == [("grade", "4"), ("status", False)]
    assert "Deactivate participants" in client.get(REGISTER).text


def test_a_stale_review_cannot_be_confirmed(app):
    client, state = signed_in(app)
    response = review(client, state, ["1", "2"])
    change(state, "update", uid="5", year=YEAR, grade="4", active=False)
    latest = state.settings()
    rejected = confirm(client, REGISTER, response)
    assert rejected.status_code == 400 and "another tab or by another researcher" in rejected.text
    assert state.settings() == latest


def test_an_unknown_id_rolls_back_the_whole_selection(app):
    client, state = signed_in(app)
    before = state.settings()
    rejected = review(client, state, ["1", "not-in-the-study"])
    assert rejected.status_code == 400 and "not-in-the-study" in rejected.text
    with pytest.raises(ValueError, match="participant_not_registered"):
        change(state, "deactivate", ids=["1", "not-in-the-study"], year=YEAR)
    assert state.settings() == before


def test_an_already_inactive_id_is_refused(app):
    client, state = signed_in(app)
    change(state, "update", uid="1", year=YEAR, grade="4", active=False)
    before = state.settings()
    assert review(client, state, ["1", "2"]).status_code == 400
    assert state.settings() == before


@pytest.mark.parametrize("fields", [{"ids": []}, {"ids": ["bad id!"]}, {"year": "2026/2028"}])
def test_invalid_selections_are_rejected(app, fields):
    client, state = signed_in(app)
    before = state.settings()
    assert review(client, state, **{"ids": ["1"], **fields}).status_code == 400
    assert state.settings() == before


def test_sign_in_and_csrf_are_required(app):
    client, state = signed_in(app)
    form = {"revision": state.settings()["revision"], "operation": "deactivate", "year": YEAR, "ids": ["1"]}
    assert app.test_client().post(REGISTER, data=form).status_code == 302
    assert client.post(REGISTER, data=form).status_code == 400
    assert state.settings()["participant_registry"]["1"]["active"]


def test_only_active_children_get_a_checkbox(app):
    client, state = signed_in(app)
    change(state, "update", uid="1", year=YEAR, grade="4", active=False)
    page = client.get(REGISTER)
    offered = re.findall(r'name="ids" value="([^"]+)"', page.text)
    assert "1" not in offered and "2" in offered
    assert "Deactivate selected" in page.text
    nothing = client.get(REGISTER + "&status=inactive")
    assert 'type="checkbox" name="ids"' not in nothing.text and "Deactivate selected" not in nothing.text


def test_from_a_session_it_returns_to_that_session(app):
    client, state = signed_in(app)
    response = review(client, state, ["1", "2"], url=WORKFLOW)
    assert response.status_code == 200
    saved = confirm(client, WORKFLOW, response)
    assert saved.status_code == 302 and f"session={SESSION}" in saved.location and "participants_saved=1" in saved.location
    shown = client.get(saved.location)
    assert "18" in shown.text
    assert not re.search(r'<span class="preparation-id">1</span>', shown.text)


def test_a_session_page_refuses_a_year_other_than_its_own(app):
    client, state = signed_in(app)
    before = state.settings()
    assert review(client, state, ["1"], url=WORKFLOW, year="2027/2028").status_code == 400
    assert state.settings() == before


def test_italian_wording(app):
    client, state = signed_in(app)
    assert "Disattiva i selezionati" in client.get(REGISTER.replace("lang=en", "lang=it")).text
    url = REGISTER.replace("lang=en", "lang=it")
    assert "Disattivazione di partecipanti" in review(client, state, ["1"], url=url).text
