"""In a real browser: the live view's classroom map, its colours and reasons, placing IDs, and honest staleness."""
import time

from .test_editor_browser import app, live, until  # noqa: F401
from .test_live_view import LIVE
from .test_live_view_browser import running  # noqa: F401

SESSION = "grade-4-session-1"
# Ten double desks in two rows, one tablet each, plus an island of two.
ROOM = {"width": 1000, "depth": 700, "pieces": [
    *({"id": f"d{n}", "kind": "desk", "x": 120 + (n % 5) * 180, "y": 160 + (n // 5) * 220} for n in range(10)),
    {"id": "isl", "kind": "island", "x": 500, "y": 600, "desks": 2},
    {"id": "board", "kind": "board", "x": 500, "y": 12},
]}


def rooms(live):
    return live.app.extensions["research"]["rooms"]


def layout(live, placed=8):
    room = rooms(live).create_room("Aula 4a", ROOM)
    rooms(live).use_room(SESSION, room["id"], 0)
    for n in range(placed):
        rooms(live).place(SESSION, str(n + 1), f"d{n}.0.0")
    return room


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


def node(page, uid):
    return page.locator(f"#live-map .map-node[data-id='{uid}']")


def opened(live, lang="en", width=1366):
    page = live.login()
    page.set_viewport_size({"width": width, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(live.base + LIVE + f"?lang={lang}")
    page.wait_for_selector("#live-map:not([hidden]) .map-node")
    return page, errors


def test_without_a_room_the_list_comes_first_and_the_map_says_how_to_get_one(running):
    live = running
    room = rooms(live).create_room("Aula 4a", ROOM)
    page = live.login()
    page.goto(live.base + LIVE + "?lang=en")
    page.wait_for_timeout(800)
    assert page.locator("#live-list-view").is_visible() and page.locator("#live-map").is_hidden()
    assert page.locator("#live-map-rooms").is_hidden(), "the map's controls stay out of the list"
    page.click("[data-live-view=map]")
    assert "no room yet" in page.inner_text("#live-map-empty")
    page.select_option("#live-map-rooms", room["id"])
    page.wait_for_selector("#live-map .map-spot")
    assert page.locator("#live-map .map-spot").count() == 12, "every desk's tablet spot, empty"
    assert rooms(live).session_map(SESSION)["room_id"] == room["id"]
    assert page.locator("#live-map-tray .map-chip").count() == 20, "every ID waits under the map"


def test_every_state_has_a_ring_an_icon_and_words_not_just_a_colour(running):
    live = running
    layout(live)
    tablets(live, {"1": {}, "2": {"ago": 9}, "3": {"fullscreen": False, "page": "/search"}, "4": None,
                   "5": {"search": True, "page": "/result"}, "7": {"visible": False}, "8": {"save": True, "page": "/thank_you"}})
    page, errors = opened(live)
    page.wait_for_selector("#live-map .map-node.map-red")
    expected = {"1": ("map-green", "✓", "OK"), "2": ("map-red", "✕", "No contact"), "3": ("map-amber", "!", "Out of full screen"),
                "4": ("map-grey", "?", "Not connected yet"), "5": ("map-red", "✕", "Search unavailable"),
                "7": ("map-amber", "!", "SOL page not visible"), "8": ("map-red", "✕", "Save not confirmed")}
    for uid, (status, icon, words) in expected.items():
        circle = node(page, uid)
        assert status in circle.get_attribute("class"), uid
        assert circle.locator(".map-badge-icon").text_content() == icon
        assert circle.locator(".map-id").text_content() == uid, "the ID stays readable"
        assert circle.get_attribute("aria-label") == f"ID {uid}: {words}"
    assert "room-desk-red" in page.locator("[data-piece=d1] .room-desk").get_attribute("class"), "the desk shows it too"
    summary = page.inner_text("#live-map-problems")
    assert summary.startswith("5 tablets need attention") and summary.index("2 · No contact") < summary.index("3 · Out of full screen")
    assert errors == []


def test_a_problem_in_the_banner_opens_its_details_and_history(running):
    live = running
    layout(live)
    tokens = tablets(live, {"2": {}})
    monitor = live.app.extensions["research"]["monitor"]
    monitor.server_incident(tokens["2"], "search_failed", True)
    page, _ = opened(live)
    page.locator("#live-map-problems button", has_text="2 · Search unavailable").click()
    details = page.locator("#live-map-details")
    assert details.is_visible() and page.inner_text("#live-map-details-id") == "ID 2"
    assert page.inner_text("#live-map-details-place") == "Desk 2", "where to find it in the room"
    text = details.inner_text()
    assert "The search engine refused a search" in text and "Last contact" in text and "Experiment" in text
    assert "No run yet" in text, "no invented progress before a run exists"
    monitor.server_incident(tokens["2"], "search_failed", False)
    monitor.beat(tokens["2"], {"order": time.time(), "page": "/search", "visible": True, "fullscreen": {"capable": True, "active": True}})
    assert until(page, lambda: "map-green" in node(page, "2").get_attribute("class"), seconds=6)
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


def test_an_id_is_put_on_a_desk_by_tapping_its_empty_spot_then_moved_and_taken_off(running):
    live = running
    layout(live, placed=1)
    page, errors = opened(live)
    page.locator("#live-map [data-spot='d4.0.0']").click()
    picker = page.locator("#live-map-picker")
    assert picker.is_visible() and "Empty spot · Desk 5" in picker.inner_text()
    picker.locator("[data-pick='12']").click()
    assert until(page, lambda: node(page, "12").count() == 1, seconds=4)
    assert rooms(live).session_map(SESSION)["placements"]["12"] == "d4.0.0"
    node(page, "12").click()
    page.locator("#live-map-details-actions button", has_text="Move").click()
    assert "Tap the empty spot where ID 12 goes" in page.inner_text("#live-map-message")
    page.locator("#live-map [data-spot='isl.1.0']").click()
    assert until(page, lambda: rooms(live).session_map(SESSION)["placements"].get("12") == "isl.1.0", seconds=4)
    assert until(page, lambda: page.inner_text("#live-map-details-place") == "Island 1 · desk 2", seconds=4)
    page.locator("#live-map-details-actions button", has_text="Take off the desk").click()
    assert until(page, lambda: "12" not in rooms(live).session_map(SESSION)["placements"], seconds=4)
    assert page.locator("#live-map-tray [data-id='12']").count() == 1
    assert errors == []


def test_an_id_dragged_from_the_strip_lands_on_the_spot_it_is_dropped_on(running):
    live = running
    layout(live, placed=0)
    page = live.login()
    page.set_viewport_size({"width": 1366, "height": 1200})
    page.goto(live.base + LIVE + "?lang=en")
    page.wait_for_selector("#live-map:not([hidden]) .map-spot")
    page.locator("#live-map-tray").scroll_into_view_if_needed()
    chip = page.locator("#live-map-tray [data-id='3']").bounding_box()
    spot = page.locator("#live-map [data-spot='d7.0.0']").bounding_box()
    page.mouse.move(chip["x"] + chip["width"] / 2, chip["y"] + chip["height"] / 2)
    page.mouse.down()
    page.mouse.move(spot["x"] + spot["width"] / 2, spot["y"] + spot["height"] / 2, steps=10)
    page.mouse.up()
    assert until(page, lambda: rooms(live).session_map(SESSION)["placements"].get("3") == "d7.0.0", seconds=4)
    assert until(page, lambda: node(page, "3").count() == 1, seconds=4)
    assert page.locator("#live-map-details").is_hidden(), "a drag is not a tap"


def test_a_spot_taken_meanwhile_by_another_researcher_is_not_overwritten(running):
    live = running
    layout(live, placed=1)
    page, _ = opened(live)
    page.locator("#live-map [data-spot='d4.0.0']").click()
    rooms(live).place(SESSION, "9", "d4.0.0")  # Another dashboard placed an ID there first.
    page.locator("#live-map-picker [data-pick='12']").click()
    assert until(page, lambda: "Someone else put an ID on that spot" in page.inner_text("#live-map-message"), seconds=4)
    assert node(page, "9").count() == 1 and node(page, "12").count() == 0
    assert rooms(live).session_map(SESSION)["placements"]["9"] == "d4.0.0"


def test_a_room_changed_on_the_rooms_page_is_brought_in_only_on_request(running):
    live = running
    room = layout(live, placed=2)
    rooms(live).update_room(room["id"], 1, {**ROOM, "pieces": [p for p in ROOM["pieces"] if p["id"] != "d0"]})
    page, _ = opened(live)
    notice = page.locator("#live-map-room-changed")
    assert notice.is_visible() and "Aula 4a" in notice.inner_text()
    assert node(page, "1").count() == 1, "still the session's own copy"
    page.click("#live-map-room-update")
    assert until(page, lambda: notice.is_hidden(), seconds=4)
    assert node(page, "1").count() == 0 and node(page, "2").count() == 1, "ID 1's desk went, ID 2 stays on its desk"
    assert page.locator("#live-map-tray [data-id='1']").count() == 1


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
    page.wait_for_selector("#live-map .map-node.map-green")
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
    assert node(page, "1").is_visible()
