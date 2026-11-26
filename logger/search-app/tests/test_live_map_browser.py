"""In a real browser: the live view's classroom map, its colours and reasons, editing, and honest staleness."""
import time

import pytest

from research_dashboard.room_maps import RoomMaps
from .test_editor_browser import app, live, until  # noqa: F401
from .test_live_view import LIVE
from .test_live_view_browser import running  # noqa: F401

SESSION = "grade-4-session-1"
TABLES = [{"id": f"t{n}", "x": 60 + (n % 5) * 180, "y": 80 + (n // 5) * 220, "w": 130, "h": 80, "rotation": 0} for n in range(10)]


def layout(live, placed=8):
    rooms = RoomMaps(live.app.config["RESEARCH_STATE_DIR"])
    return rooms.save_session_map(SESSION, 0, {"tables": TABLES, "placements": {str(n + 1): {"table": f"t{n}"} for n in range(placed)}})


def tablets(live, states):
    """Register tablets and give each its latest report, by the server's clock."""
    monitor = live.app.extensions["research"]["monitor"]
    now = time.time()
    tokens = {}
    for uid, value in states.items():
        tokens[uid] = monitor.register(SESSION, uid, now=now - 30)
        if value is None:
            continue
        at = now - value.get("ago", 0)
        incidents = [{"code": "save_unconfirmed", "reason": "network", "for": 12}] if value.get("save") else []
        monitor.beat(tokens[uid], {"order": at, "page": value.get("page", "/task"), "visible": value.get("visible", True),
                                   "fullscreen": {"capable": True, "active": value.get("fullscreen", True)},
                                   "incidents": incidents}, now=at)
        if value.get("search"):
            monitor.server_incident(tokens[uid], "search_failed", True, now=now - 20)
    return tokens


def circle(page, uid):
    return page.locator(f"#live-map .map-tablet[data-id='{uid}']")


def opened(live, lang="en", width=1366):
    page = live.login()
    page.set_viewport_size({"width": width, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(live.base + LIVE + f"?lang={lang}")
    page.wait_for_selector("#live-map:not([hidden]) .map-tablet")
    return page, errors


def test_without_a_layout_the_list_stays_the_first_view(running):
    page = running.login()
    page.goto(running.base + LIVE + "?lang=en")
    page.wait_for_timeout(800)
    assert page.locator("#live-list-view").is_visible() and page.locator("#live-map").is_hidden()
    page.click("[data-live-view=map]")
    assert page.locator("#live-map").is_visible() and page.locator("#live-map .map-tablet").count() == 20, "every ID waits in the tray"


def test_every_state_has_a_ring_an_icon_and_a_reason_not_just_a_colour(running):
    live = running
    layout(live)
    tablets(live, {"1": {}, "2": {"ago": 9}, "3": {"fullscreen": False, "page": "/search"}, "4": None,
                   "5": {"search": True, "page": "/result"}, "7": {"visible": False}, "8": {"save": True, "page": "/thank_you"}})
    page, errors = opened(live)
    page.wait_for_selector("#live-map .map-tablet.map-red")
    expected = {"1": ("map-green", "✓", ""), "2": ("map-red", "!", "No contact"), "3": ("map-amber", "!", "Out of full screen"),
                "4": ("map-grey", "?", "Not connected yet"), "5": ("map-red", "!", "Search unavailable"),
                "7": ("map-amber", "!", "SOL page not visible"), "8": ("map-red", "!", "Save not confirmed")}
    for uid, (status, icon, reason) in expected.items():
        button = circle(page, uid)
        assert status in button.get_attribute("class"), uid
        assert button.locator(".map-tablet-icon").inner_text() == icon
        assert button.locator(".map-tablet-circle").inner_text().startswith(uid), "the ID stays readable"
        if reason:
            assert button.locator(".map-tablet-reason").inner_text() == reason
    summary = page.inner_text("#live-map-problems")
    assert summary.startswith("5 tablets need attention") and summary.index("2 · No contact") < summary.index("3 · Out of full screen")
    assert errors == []


def test_a_problem_in_the_summary_opens_its_details_and_history(running):
    live = running
    layout(live)
    tokens = tablets(live, {"2": {}})
    monitor = live.app.extensions["research"]["monitor"]
    monitor.server_incident(tokens["2"], "search_failed", True)
    page, _ = opened(live)
    page.locator("#live-map-problems button", has_text="2 · Search unavailable").click()
    details = page.locator("#live-map-details")
    assert details.is_visible() and page.inner_text("#live-map-details-id") == "ID 2"
    text = details.inner_text()
    assert "The search engine refused a search" in text and "Last contact" in text and "Experiment" in text
    assert "No run yet" in text, "no invented progress before a run exists"
    assert page.evaluate("document.activeElement.dataset.id") == "2"
    monitor.server_incident(tokens["2"], "search_failed", False)
    monitor.beat(tokens["2"], {"order": time.time(), "page": "/search", "visible": True, "fullscreen": {"capable": True, "active": True}})
    assert until(page, lambda: "map-green" in circle(page, "2").get_attribute("class"), seconds=6)
    assert until(page, lambda: "solved after" in details.inner_text(), seconds=4), "the recovery stays in the history"
    assert details.is_visible(), "polling keeps the panel open"


def test_the_list_shows_the_same_state_next_to_each_id(running):
    live = running
    layout(live)
    tablets(live, {"1": {}, "2": {"ago": 9}})
    page, _ = opened(live)
    page.click("[data-live-view=list]")
    chip = page.locator("details[data-child='2'] .live-monitor")
    assert until(page, lambda: chip.is_visible() and chip.inner_text() == "No contact", seconds=6)
    assert "map-red" in chip.get_attribute("class")


def test_tables_and_tablets_are_arranged_by_hand_and_saved_for_the_session(running):
    live = running
    layout(live, placed=0)
    page, errors = opened(live)
    page.click("#live-map-edit")
    target = page.locator("#live-map [data-table='t0']")
    tablet = circle(page, "1")
    box, goal = tablet.bounding_box(), target.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 20)
    page.mouse.down()
    page.mouse.move(goal["x"] + goal["width"] / 2, goal["y"] + goal["height"] / 2, steps=8)
    page.mouse.up()
    assert page.locator("#live-map-canvas .map-tablet[data-id='1']").count() == 1, "dropped on its table"
    assert "not saved" in page.inner_text("#live-map-message")
    page.click("#live-map-add-table")
    page.click("#live-map-save")
    assert until(page, lambda: page.inner_text("#live-map-message") == "Map saved.", seconds=4)
    saved = RoomMaps(live.app.config["RESEARCH_STATE_DIR"]).session_map(SESSION)
    assert saved["placements"]["1"] == {"table": "t0"} and len(saved["tables"]) == 11
    page.reload()
    page.wait_for_selector("#live-map-canvas .map-tablet[data-id='1']")
    assert errors == []


def test_a_change_saved_meanwhile_by_another_researcher_is_not_overwritten(running):
    live = running
    layout(live)
    page, _ = opened(live)
    page.click("#live-map-edit")
    page.click("#live-map-add-table")
    rooms = RoomMaps(live.app.config["RESEARCH_STATE_DIR"])
    rooms.save_session_map(SESSION, 1, {"tables": TABLES[:2], "placements": {}})  # Another dashboard saved first.
    page.click("#live-map-save")
    assert until(page, lambda: "Someone else saved this map" in page.inner_text("#live-map-message"), seconds=4)
    assert page.locator("#live-map [data-table]").count() == 2, "their version is shown"
    assert rooms.session_map(SESSION)["revision"] == 2


def test_when_the_health_feed_fails_the_map_says_it_is_not_current(running):
    live = running
    layout(live)
    tablets(live, {"1": {}})
    page, _ = opened(live)
    assert until(page, lambda: page.inner_text("#live-map-monitor").startswith("Monitoring live"), seconds=4)
    page.route("**/health.json**", lambda route: route.abort())
    assert until(page, lambda: "Monitoring unavailable" in page.inner_text("#live-map-monitor"), seconds=8)
    assert "monitor-stale" in page.get_attribute("#live-map", "class")
    assert page.inner_text("#live-map-problems").startswith("No tablet needs attention"), "no invented incidents"
    page.unroute("**/health.json**")
    assert until(page, lambda: "monitor-stale" not in page.get_attribute("#live-map", "class"), seconds=8)


def test_a_signed_out_researcher_sees_that_nothing_is_current(running):
    live = running
    layout(live)
    page, _ = opened(live)
    page.route("**/health.json**", lambda route: route.fulfill(status=401, content_type="application/json", body='{"error": "login"}'))
    assert until(page, lambda: "signed out" in page.inner_text("#live-map-monitor"), seconds=6)


def test_sound_is_off_until_asked_and_beeps_once_per_new_problem(running):
    live = running
    layout(live)
    tokens = tablets(live, {"1": {}, "2": {}})
    page = live.login()
    page.add_init_script("""window.__beeps = 0;
        window.AudioContext = function () { return { state: 'running', currentTime: 0, destination: {}, resume: function () {},
          createGain: function () { return { gain: { setValueAtTime: function () {}, exponentialRampToValueAtTime: function () {} },
                                             connect: function (next) { return next; } }; },
          createOscillator: function () { window.__beeps += 1; return { frequency: {}, connect: function (next) { return next; },
                                                                         start: function () {}, stop: function () {} }; } }; };""")
    page.goto(live.base + LIVE + "?lang=en")
    page.wait_for_selector("#live-map .map-tablet.map-green")
    monitor = live.app.extensions["research"]["monitor"]
    monitor.server_incident(tokens["1"], "search_failed", True)
    page.wait_for_timeout(3000)
    assert page.evaluate("window.__beeps") == 0, "off by default"
    page.click("#live-map-sound")
    monitor.server_incident(tokens["2"], "search_failed", True)
    assert until(page, lambda: page.evaluate("window.__beeps") == 1, seconds=6)
    page.wait_for_timeout(4500)
    assert page.evaluate("window.__beeps") == 1, "never once per poll"


def test_the_map_fits_a_phone_without_sideways_scrolling(running):
    live = running
    layout(live)
    page, _ = opened(live, lang="it", width=390)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    assert circle(page, "1").is_visible()
