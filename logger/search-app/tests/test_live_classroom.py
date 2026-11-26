"""The live view's classroom map on the server: the session's copy of a room, placing IDs, and the tablets' health."""
from pathlib import Path
import sqlite3

from .test_live_view import signed_in
from .test_research_dashboard import app, configure  # noqa: F401

SESSION = "grade-4-session-1"
BASE = f"/dashboard/sessions/{SESSION}"
ROOM = {"width": 800, "depth": 600, "pieces": [
    {"id": "a", "kind": "desk", "x": 120, "y": 300},
    {"id": "i", "kind": "island", "x": 400, "y": 300, "desks": 2},
]}


def token(client):
    return client.get(f"{BASE}/classroom.json").get_json()["csrf"]


def with_room(app):
    client, state = signed_in(app)
    room = app.extensions["research"]["rooms"].create_room("Aula 4a", ROOM)
    return client, room


def test_the_map_and_the_health_need_a_researcher(app):
    configure(app)
    client = app.test_client()
    response = client.get(f"{BASE}/classroom.json")
    assert response.status_code == 401 and response.get_json() == {"error": "login"}
    assert client.get(f"{BASE}/health.json").status_code == 401
    assert client.post(f"{BASE}/classroom/place", data={"participant": "1", "spot": "a.0.0"}).status_code in (400, 401)


def test_a_session_chooses_a_room_and_places_ids_one_at_a_time(app):
    client, room = with_room(app)
    empty = client.get(f"{BASE}/classroom.json").get_json()
    assert empty["map"]["revision"] == 0 and empty["rooms"][0]["name"] == "Aula 4a" and empty["room_changed"] is False
    refused = client.post(f"{BASE}/classroom/room", data={"revision": 0, "room_id": room["id"]})
    assert refused.status_code == 400 and refused.get_json()["error"] == "csrf_error"
    chosen = client.post(f"{BASE}/classroom/room", data={"csrf": token(client), "revision": 0, "room_id": room["id"]}).get_json()
    assert chosen["map"]["room_id"] == room["id"] and len(chosen["map"]["pieces"]) == 2
    placed = client.post(f"{BASE}/classroom/place", data={"csrf": token(client), "participant": "1", "spot": "i.1.0"})
    assert placed.status_code == 200 and placed.get_json()["map"]["placements"] == {"1": "i.1.0"}
    taken = client.post(f"{BASE}/classroom/place", data={"csrf": token(client), "participant": "2", "spot": "i.1.0"})
    assert taken.status_code == 409 and taken.get_json()["error"] == "spot_taken" and taken.get_json()["map"]["placements"] == {"1": "i.1.0"}
    missing = client.post(f"{BASE}/classroom/place", data={"csrf": token(client), "participant": "2", "spot": "z.0.0"})
    assert missing.status_code == 400 and missing.get_json()["error"] == "spot_missing"
    off = client.post(f"{BASE}/classroom/place", data={"csrf": token(client), "participant": "1", "spot": ""})
    assert off.get_json()["map"]["placements"] == {}


def test_a_room_edited_later_is_announced_and_brought_in_on_request(app):
    client, room = with_room(app)
    client.post(f"{BASE}/classroom/room", data={"csrf": token(client), "revision": 0, "room_id": room["id"]})
    client.post(f"{BASE}/classroom/place", data={"csrf": token(client), "participant": "1", "spot": "a.0.0"})
    app.extensions["research"]["rooms"].update_room(room["id"], 1, {**ROOM, "width": 900})
    seen = client.get(f"{BASE}/classroom.json").get_json()
    assert seen["room_changed"] is True and seen["map"]["width"] == 800, "the session keeps its copy until asked"
    stale = client.post(f"{BASE}/classroom/room", data={"csrf": token(client), "revision": 1, "room_id": room["id"]})
    assert stale.status_code == 409 and stale.get_json()["error"] == "map_changed"
    fresh = client.post(f"{BASE}/classroom/room", data={"csrf": token(client), "revision": 2, "room_id": room["id"]}).get_json()
    assert fresh["room_changed"] is False and fresh["map"]["width"] == 900 and fresh["map"]["placements"] == {"1": "a.0.0"}


def test_the_health_feed_lists_the_class_and_each_registered_tablet(app):
    client, _ = signed_in(app)
    monitor = app.extensions["research"]["monitor"]
    tablet = monitor.register(SESSION, "1")
    assert monitor.beat(tablet, {"order": 1, "page": "/task", "visible": True, "fullscreen": {"capable": False, "active": None}})
    health = client.get(f"{BASE}/health.json").get_json()
    assert health["available"] is True and "1" in health["roster"] and health["tablets"]["1"]["status"] == "green"
    assert health["timing"] == {"beat": 2, "late": 4, "lost": 6}
    assert "2" not in health["tablets"], "an ID with no registered tablet is simply not connected yet"


def test_an_unreadable_monitor_is_reported_as_unavailable_not_as_ten_lost_tablets(app, monkeypatch):
    client, _ = signed_in(app)
    monitor = app.extensions["research"]["monitor"]

    def broken():
        raise sqlite3.OperationalError("locked")
    monkeypatch.setattr(monitor, "_connect", broken)
    health = client.get(f"{BASE}/health.json").get_json()
    assert health["available"] is False and health["tablets"] == {}


def test_reading_the_map_and_the_health_writes_nothing(app):
    client, room = with_room(app)
    client.post(f"{BASE}/classroom/room", data={"csrf": token(client), "revision": 0, "room_id": room["id"]})
    rooms_file = Path(app.config["RESEARCH_STATE_DIR"]) / "rooms.sqlite3"
    before = rooms_file.read_bytes()
    for _ in range(3):
        client.get(f"{BASE}/classroom.json")
        client.get(f"{BASE}/health.json")
        client.get(f"{BASE}/live")
    assert rooms_file.read_bytes() == before
