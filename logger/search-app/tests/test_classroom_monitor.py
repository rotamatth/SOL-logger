"""The classroom map's view of each tablet: registered at the ID, heard until the reset, honest about what it knows."""
import sqlite3

import pytest

from research_dashboard import monitor as monitor_module
from research_dashboard.monitor import Monitor, stage_for
from .progress_helpers import HiddenFields
from .test_editable_recap import commit, complete_today
from .test_practice_question import answer_first, recorded, set_number, site, through_practice  # noqa: F401
from .test_study_enrollment import question_set, schedule, student_modules  # noqa: F401

SESSION = "grade-4-session-2"
T0 = 1_800_000_000.0


@pytest.fixture
def store(tmp_path):
    return Monitor(tmp_path)


def report(order, page="/task", visible=True, capable=True, active=True, **extra):
    return {"order": order, "page": page, "visible": visible, "fullscreen": {"capable": capable, "active": active}, **extra}


def heard(store, token, at, **values):
    assert store.beat(token, report(at, **values), now=at)


def tablet(store, participant="1", now=None):
    return store.health(SESSION, now=now)[participant]


def codes(item):
    return [reason["code"] for reason in item["reasons"]]


# -- The store ----------------------------------------------------------------------------------------------------

def test_one_registration_per_tablet_and_id_kept_across_reloads(store):
    token = store.register(SESSION, "1", now=T0)
    assert store.register(SESSION, "1", current_token=token, now=T0 + 5) == token
    other = store.register(SESSION, "2", current_token=token, now=T0 + 10)
    assert other != token and store.active(token, now=T0 + 10) is None, "the tablet's earlier ID is retired"
    assert set(store.health(SESSION, now=T0 + 10)) == {"2"}


def test_ids_are_exact_strings(store):
    for participant in ("1", "001", "C-001"):
        heard(store, store.register(SESSION, participant, now=T0), T0, page="/task")
    assert set(store.health(SESSION, now=T0)) == {"1", "001", "C-001"}


def test_a_registered_tablet_not_heard_yet_is_grey_not_lost(store):
    store.register(SESSION, "1", now=T0)
    item = tablet(store, now=T0 + 600)
    assert item["status"] == "grey" and not item["connected"] and item["reasons"] == []


@pytest.mark.parametrize(("seconds", "status", "reason"), [(0, "green", None), (3.9, "green", None),
                                                          (4, "amber", "contact_late"), (5.9, "amber", "contact_late"),
                                                          (6, "red", "no_contact"), (300, "red", "no_contact")])
def test_freshness_from_the_server_clock(store, seconds, status, reason):
    token = store.register(SESSION, "1", now=T0)
    heard(store, token, T0)
    item = tablet(store, now=T0 + seconds)
    assert item["status"] == status and codes(item) == ([reason] if reason else [])


def test_a_hidden_page_that_goes_silent_is_not_blamed_on_the_network(store):
    token = store.register(SESSION, "1", now=T0)
    heard(store, token, T0, visible=False)
    item = tablet(store, now=T0 + 60)
    assert item["status"] == "amber" and codes(item) == ["page_hidden", "no_signal_hidden"]


def test_reports_out_of_order_or_from_an_unknown_tablet_change_nothing(store):
    token = store.register(SESSION, "1", now=T0)
    heard(store, token, T0 + 10, page="/search")
    assert not store.beat(token, report(T0 + 5, page="/fine"), now=T0 + 11), "an older report arrived late"
    assert tablet(store, now=T0 + 11)["stage"] == "experiment"
    assert not store.beat("x" * 32, report(T0 + 20), now=T0 + 20)
    assert not store.beat(token, {"page": "/task"}, now=T0 + 20), "no order, no report"


def test_full_screen_is_expected_in_the_practice_and_the_experiment_only_where_the_browser_has_it(store):
    token = store.register(SESSION, "1", now=T0)
    heard(store, token, T0, page="/search", active=False)
    assert codes(tablet(store, now=T0)) == ["fullscreen_off"]
    heard(store, token, T0 + 1, page="/search", capable=False, active=False)
    assert tablet(store, now=T0 + 1)["status"] == "green", "a browser without full screen is not a problem"
    heard(store, token, T0 + 2, page="/start", active=False)
    assert tablet(store, now=T0 + 2)["status"] == "green", "the adult still holds a tablet on the ID page"


def test_a_failed_search_stays_red_until_a_search_works(store):
    token = store.register(SESSION, "1", now=T0)
    heard(store, token, T0)
    assert store.server_incident(token, "search_failed", True, now=T0 + 1)
    heard(store, token, T0 + 5)
    item = tablet(store, now=T0 + 5)
    assert item["status"] == "red" and codes(item) == ["search_failed"], "a heartbeat does not clear it"
    assert store.server_incident(token, "search_failed", False, now=T0 + 9)
    heard(store, token, T0 + 9)
    item = tablet(store, now=T0 + 9)
    assert item["status"] == "green"
    assert [(entry["code"], entry["event"], entry["seconds"]) for entry in item["history"]] == [
        ("search_failed", "recovered", 8), ("search_failed", "start", None)]


def test_a_save_the_tablet_could_not_confirm_keeps_its_start_and_clears_when_it_says_so(store):
    token = store.register(SESSION, "1", now=T0)
    unconfirmed = [{"code": "save_unconfirmed", "reason": "network", "for": 2}]
    heard(store, token, T0, incidents=unconfirmed)
    heard(store, token, T0 + 4, incidents=unconfirmed)
    item = tablet(store, now=T0 + 4)
    assert item["reasons"][0] == {"code": "save_unconfirmed", "severity": "red", "since": T0 - 2, "reason": "network"}
    heard(store, token, T0 + 6, incidents=[], lastSaveFor=0)
    item = tablet(store, now=T0 + 6)
    assert item["status"] == "green" and item["last_save"] == T0 + 6
    assert item["history"][0]["code"] == "save_unconfirmed" and item["history"][0]["event"] == "recovered"


def test_a_search_that_does_not_come_back_is_shown_as_waiting(store):
    token = store.register(SESSION, "1", now=T0)
    heard(store, token, T0, searchPendingFor=19)
    assert tablet(store, now=T0)["status"] == "green", "a slow search is still a search"
    heard(store, token, T0 + 1, searchPendingFor=20)
    assert codes(tablet(store, now=T0 + 1)) == ["search_waiting"]


def test_a_silence_is_written_in_the_history_once_it_ends(store):
    token = store.register(SESSION, "1", now=T0)
    heard(store, token, T0)
    heard(store, token, T0 + 10)
    assert [(entry["code"], entry["event"]) for entry in tablet(store, now=T0 + 10)["history"]] == [
        ("no_contact", "recovered"), ("no_contact", "start")]
    assert tablet(store, now=T0 + 10)["history"][0]["seconds"] == 10


def test_two_tablets_with_one_id_are_shown_rather_than_overwriting_each_other(store):
    first = store.register(SESSION, "1", now=T0)
    second = store.register(SESSION, "1", now=T0)
    heard(store, first, T0)
    heard(store, second, T0 + 1)
    assert "two_tablets" in codes(tablet(store, now=T0 + 2))


def test_a_registration_ends_after_a_long_day(store):
    token = store.register(SESSION, "1", now=T0)
    later = T0 + monitor_module.REGISTRATION_HOURS * 3600 + 1
    assert store.active(token, now=later) is None and store.health(SESSION, now=later) == {}


def test_the_history_is_bounded_per_session(store, monkeypatch):
    monkeypatch.setattr(monitor_module, "HISTORY_PER_SESSION", 4)
    token = store.register(SESSION, "1", now=T0)
    for step in range(6):
        store.server_incident(token, "search_failed", step % 2 == 0, now=T0 + step)
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM history").fetchone()[0] == 4


def test_an_unreadable_database_says_so_instead_of_blaming_the_tablets(store, monkeypatch):
    def broken():
        raise sqlite3.OperationalError("locked")
    monkeypatch.setattr(store, "_connect", broken)
    assert store.health(SESSION) is None
    assert store.register(SESSION, "1") is None and store.beat("x" * 32, report(1)) is False


@pytest.mark.parametrize(("path", "stage"), [("/start", "prepared"), ("/prova/cerca", "practice"), ("/task/intro", "experiment"),
                                             ("/result", "experiment"), ("/thank_you", "recap"), ("/fine", "finished")])
def test_the_stage_comes_from_the_page(path, stage):
    assert stage_for(path) == stage


# -- Through the children's app -----------------------------------------------------------------------------------

def monitor_of(module):
    return module.app.extensions["research"]["monitor"]


def beat(client, order, page="/start", **values):
    return client.post("/presenza", json=report(order, page=page, **values))


def test_choosing_the_id_makes_the_tablet_monitorable_before_any_run(site):
    client = site.app.test_client()
    assert set_number(client, "1").status_code == 303
    assert client.get_cookie("sol_monitor") is not None
    assert monitor_of(site).health(SESSION)["1"]["status"] == "grey", "registered, not heard yet"
    assert beat(client, 1).status_code == 204
    assert monitor_of(site).health(SESSION)["1"]["status"] == "green"
    through_practice(client)
    beat(client, 2, page="/prova/cerca")
    assert monitor_of(site).health(SESSION)["1"]["stage"] == "practice"
    assert recorded(site) == ([], 0, 0), "monitoring the practice leaves no log, attempt or study record"


def test_monitoring_continues_through_the_run_and_the_last_page_until_the_reset(site):
    client = site.app.test_client()
    set_number(client, "1")
    through_practice(client)
    assert client.post("/start", data={"user_id": "1"}).status_code == 302
    auth = complete_today(client)
    assert commit(client, auth, "finish").status_code == 200
    client.get("/fine?reset=1")
    assert beat(client, 3, page="/fine").status_code == 204
    item = monitor_of(site).health(SESSION)["1"]
    assert item["stage"] == "finished" and item["status"] == "green", "Salva cleared the run's session, not the tablet's"
    client.get("/welcome?reset=1")
    assert client.get_cookie("sol_monitor") is None
    beat(client, 4, page="/welcome")
    assert monitor_of(site).health(SESSION) == {}, "after the reset the tablet belongs to no circle"


def test_a_new_id_on_the_same_tablet_retires_the_previous_one(site):
    client = site.app.test_client()
    set_number(client, "1")
    beat(client, 1)
    client.get("/welcome?reset=1")
    set_number(client, "2")
    beat(client, 2)
    assert set(monitor_of(site).health(SESSION)) == {"2"}


def test_test_ids_are_not_monitored(site):
    client = site.app.test_client()
    set_number(client, "TEST-spazio")
    assert client.get_cookie("sol_monitor") is None


def test_a_refused_search_turns_red_and_the_next_answer_clears_it(site):
    client = site.app.test_client()
    set_number(client, "1")
    beat(client, 1)

    def refuse(*_args, **_kwargs):
        raise RuntimeError("engine down")
    working = site.search_backend.search
    site.search_backend.search = refuse
    client.get("/prova")
    assert answer_first(client).status_code == 303
    assert client.post("/prova/risultati", data={"query": "vulcani"}).status_code == 503
    assert [reason["code"] for reason in monitor_of(site).health(SESSION)["1"]["reasons"]] == ["search_failed"]
    site.search_backend.search = working
    assert client.post("/prova/risultati", data={"query": "vulcani"}).status_code == 200
    assert monitor_of(site).health(SESSION)["1"]["status"] == "green"


def test_a_save_the_server_refuses_shows_until_a_save_goes_through(site, monkeypatch):
    client = site.app.test_client()
    set_number(client, "1")
    through_practice(client)
    client.post("/start", data={"user_id": "1"})
    beat(client, 1, page="/task")
    fields = HiddenFields(client.get("/task").text).values
    draft = {key: fields[key] for key in ("csrf_token", "attempt_id")}
    draft.update(question_number=int(fields["question_number"]), text="Un cane", revision=0)
    store = site.PROGRESS.store
    working = store.save_draft

    def refuse(*_args, **_kwargs):
        raise sqlite3.OperationalError("disk I/O error")
    monkeypatch.setattr(store, "save_draft", refuse)
    assert client.post("/first-answer/draft", json=draft).status_code == 503
    item = monitor_of(site).health(SESSION)["1"]
    assert item["status"] == "red" and item["reasons"][0]["code"] == "save_failed" and item["reasons"][0]["reason"] == "server"
    beat(client, 2, page="/task")
    assert monitor_of(site).health(SESSION)["1"]["status"] == "red", "a heartbeat does not clear an unsaved answer"
    monkeypatch.setattr(store, "save_draft", working)
    assert client.post("/first-answer/draft", json=draft).status_code == 200
    item = monitor_of(site).health(SESSION)["1"]
    assert item["status"] == "green" and item["last_save"] is not None


def test_a_draft_refused_as_stale_after_conferma_is_not_a_failed_save(site):
    """Found in the rehearsal of 26 November: the autosave that lands just after Conferma is refused (409). The
    answer itself is saved, so the map must not turn the class red for it; a refused answer still would."""
    client = site.app.test_client()
    set_number(client, "1")
    through_practice(client)
    client.post("/start", data={"user_id": "1"})
    beat(client, 1, page="/task")
    fields = HiddenFields(client.get("/task").text).values
    draft = {key: fields[key] for key in ("csrf_token", "attempt_id")}
    draft.update(question_number=int(fields["question_number"]), text="Un cane", revision=0)
    assert client.post("/first-answer/draft", json=draft).status_code == 200
    assert client.post("/first-answer", data={**fields, "outcome": "answered", "confidence": "2", "text": "Un cane"}).status_code == 303
    stale = client.post("/first-answer/draft", json={**draft, "text": "Un cane nero", "revision": 1})  # After Conferma.
    assert stale.status_code == 409
    item = monitor_of(site).health(SESSION)["1"]
    assert item["status"] == "green" and "save_failed" not in codes(item)
