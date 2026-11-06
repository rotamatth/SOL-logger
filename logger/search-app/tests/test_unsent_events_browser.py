"""Events a browser could not send are not wiped when an ID is entered on that browser again.

Real browser, real student app, synthetic search; storage in a temporary directory.
"""
import json

from .test_background_upload_browser import RESULTS, search, start, student_site  # noqa: F401


def everything_saved(root, uid):
    """Every event of a child, in its full log or in its recovery file."""
    events = []
    for path in root.glob(f"{uid}_*.log"):
        if "_task" not in path.name:
            events.extend(json.loads(line) for line in path.read_text().splitlines())
    return events


def results_saved(events, query):
    """Results-page events are logged after the page has loaded, so only uploads can save them."""
    return [event for event in events if event["type"] == "searchResultGenerated"
            and query in (event.get("rawQuery"), event.get("sanitizedQuery"), event.get("query"))]


def leave_with_unsent_events(page, base, query):
    page.route("**/log_session", lambda route: route.abort())
    search(page, query)
    # The upload sent as a page closes outlives the page: make sure the network really is down for it.
    page.evaluate("() => { window.fetch = () => Promise.reject(new Error('offline')); }")
    page.goto(base + "/welcome?reset=1")
    page.unroute("**/log_session")


def enter_id(page, base, uid):
    page.goto(base + "/start")
    page.select_option("#id-box", uid)
    page.click("#continue-btn")
    page.wait_for_load_state("load")


def test_a_child_entering_their_id_again_keeps_the_events_that_were_not_sent(student_site):
    page, base, root = student_site
    start(page, base, "1")
    leave_with_unsent_events(page, base, "mai inviato")
    assert not results_saved(everything_saved(root, "1"), "mai inviato")
    enter_id(page, base, "1")
    page.wait_for_function("!localStorage.getItem('solUnsentRuns')")
    assert len(results_saved(everything_saved(root, "1"), "mai inviato")) == len(RESULTS)


def test_the_next_child_on_a_tablet_keeps_the_previous_childs_unsent_events_apart(student_site):
    page, base, root = student_site
    start(page, base, "1")
    leave_with_unsent_events(page, base, "del primo")
    start(page, base, "2")
    page.wait_for_function("!localStorage.getItem('solUnsentRuns')")
    assert len(results_saved(everything_saved(root, "1"), "del primo")) == len(RESULTS)
    assert not results_saved(everything_saved(root, "2"), "del primo")
    assert {event["uid"] for event in everything_saved(root, "2")} == {"2"}


def test_a_refused_old_batch_never_holds_up_the_current_run(student_site):
    page, base, root = student_site
    start(page, base, "1")
    leave_with_unsent_events(page, base, "rifiutato")
    page.route("**/log_session", lambda route: route.fulfill(status=400, json={"error": "refused"})
               if "rifiutato" in (route.request.post_data or "") else route.continue_())
    start(page, base, "2")
    search(page, "attuale")
    page.evaluate("() => window.studyLogger.sendLogs()")
    assert len(results_saved(everything_saved(root, "2"), "attuale")) == len(RESULTS)
    assert page.evaluate("JSON.parse(localStorage.getItem('solUnsentRuns')).length") >= 1
