"""Classroom layouts for the live view's map: reusable rooms, each session's own copy, and the tablets' health feed."""
from io import BytesIO
import json
import sqlite3

from PIL import Image
import pytest

from research_dashboard import room_maps
from research_dashboard.room_maps import Conflict, RoomMaps
from .test_live_view import signed_in
from .test_research_dashboard import app, configure, csrf, identity, login  # noqa: F401

SESSION = "grade-4-session-1"
BASE = f"/dashboard/sessions/{SESSION}"
TABLES = [{"id": "t1", "x": 100, "y": 100, "w": 120, "h": 80, "rotation": 0},
          {"id": "t2", "x": 400, "y": 100, "w": 120, "h": 80, "rotation": 90}]


def picture(kind="PNG", size=(40, 30)):
    data = BytesIO()
    Image.new("RGB", size, "white").save(data, kind)
    return data.getvalue()


@pytest.fixture
def maps(tmp_path):
    return RoomMaps(tmp_path)


# -- The store ----------------------------------------------------------------------------------------------------

def test_a_session_map_starts_empty_and_keeps_ids_as_exact_strings(maps):
    assert maps.session_map(SESSION) == {"revision": 0, "updated": None, "tables": [], "image": None, "placements": {},
                                         "room_id": None}
    saved = maps.save_session_map(SESSION, 0, {"tables": TABLES, "placements": {"1": {"table": "t1"}, "001": {"x": 5, "y": 6},
                                                                               "C-001": {"table": "t2"}}})
    assert saved["revision"] == 1 and set(saved["placements"]) == {"1", "001", "C-001"}
    assert saved["placements"]["001"] == {"x": 5.0, "y": 6.0}


@pytest.mark.parametrize("body", [
    {"tables": [{**TABLES[0], "x": 1001}]},
    {"tables": [{**TABLES[0], "w": 5}]},
    {"tables": [TABLES[0], TABLES[0]]},
    {"tables": [{**TABLES[0], "id": "bad id"}]},
    {"tables": TABLES, "placements": {"1": {"table": "missing"}}},
    {"tables": TABLES, "placements": {"1\n": {"table": "t1"}}},
    {"tables": TABLES, "image": "../../etc/passwd"},
    {"tables": "nope"},
])
def test_a_bad_map_is_refused_whole(maps, body):
    with pytest.raises(ValueError, match="invalid_map"):
        maps.save_session_map(SESSION, 0, body)
    assert maps.session_map(SESSION)["revision"] == 0


def test_two_open_dashboards_cannot_silently_overwrite_each_other(maps):
    maps.save_session_map(SESSION, 0, {"tables": TABLES})
    with pytest.raises(Conflict) as stale:
        maps.save_session_map(SESSION, 0, {"tables": []})
    assert stale.value.current["tables"] == maps.session_map(SESSION)["tables"] and len(stale.value.current["tables"]) == 2


def test_a_session_starts_from_a_copy_of_a_room_and_never_changes_it_by_itself(maps):
    room = maps.create_room("Aula 4a", {"tables": TABLES})
    copy = maps.start_from_room(SESSION, room["id"], 0)
    assert copy["tables"] == room["tables"] and copy["placements"] == {} and copy["room_id"] == room["id"]
    moved = [{**TABLES[0], "x": 600}, TABLES[1]]
    maps.save_session_map(SESSION, copy["revision"], {"tables": moved, "placements": {"7": {"table": "t1"}}, "room_id": room["id"]})
    assert maps.room(room["id"])["tables"] == room["tables"], "rearranging a session leaves the room alone"
    assert "placements" not in maps.room(room["id"]), "a room never carries a class's IDs"
    updated = maps.update_room(room["id"], room["revision"], maps.session_map(SESSION))
    assert updated["revision"] == 2 and updated["tables"][0]["x"] == 600 and "placements" not in updated
    with pytest.raises(Conflict):
        maps.update_room(room["id"], room["revision"], maps.session_map(SESSION))


def test_two_named_rooms_are_kept_and_listed(maps):
    maps.create_room("Aula del mattino", {"tables": TABLES})
    maps.create_room("aula del pomeriggio", {"tables": TABLES[:1]})
    assert [room["name"] for room in maps.rooms()] == ["Aula del mattino", "aula del pomeriggio"]
    with pytest.raises(ValueError, match="invalid_room_name"):
        maps.create_room("   ", {"tables": []})


@pytest.mark.parametrize("kind", ["PNG", "JPEG", "WEBP"])
def test_a_floor_plan_is_kept_when_it_really_is_a_picture(maps, kind):
    name = maps.save_image(picture(kind))
    path, media = maps.image_file(name)
    assert path.read_bytes() == picture(kind) and media.startswith("image/") and oct(path.stat().st_mode & 0o777) == "0o600"
    assert maps.save_session_map(SESSION, 0, {"tables": TABLES, "image": name})["image"] == name


@pytest.mark.parametrize("data", [b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", b"<html></html>", b"", b"GIF89a" + b"0" * 20])
def test_anything_else_is_refused(maps, data):
    with pytest.raises(ValueError, match="invalid_image"):
        maps.save_image(data)


def test_a_huge_picture_is_refused(maps, monkeypatch):
    monkeypatch.setattr(room_maps, "IMAGE_PIXELS", 100)
    with pytest.raises(ValueError, match="invalid_image"):
        maps.save_image(picture(size=(20, 20)))


# -- The dashboard's endpoints ------------------------------------------------------------------------------------

def token(client):
    return client.get(f"{BASE}/map.json").get_json()["csrf"]


def save(client, body, revision, csrf_token=None):
    return client.post(f"{BASE}/map", data={"csrf": csrf_token or token(client), "revision": revision, "map": json.dumps(body)})


def test_the_map_needs_a_researcher(app):
    configure(app)
    response = app.test_client().get(f"{BASE}/map.json")
    assert response.status_code == 401 and response.get_json() == {"error": "login"}
    assert app.test_client().get(f"{BASE}/health.json").status_code == 401


def test_saving_needs_the_csrf_token_and_the_revision(app):
    client, _ = signed_in(app)
    refused = client.post(f"{BASE}/map", data={"revision": 0, "map": json.dumps({"tables": TABLES})})
    assert refused.status_code == 400 and refused.get_json()["error"] == "csrf_error"
    saved = save(client, {"tables": TABLES, "placements": {"1": {"table": "t1"}}}, 0)
    assert saved.status_code == 200 and saved.get_json()["map"]["revision"] == 1
    stale = save(client, {"tables": []}, 0)
    assert stale.status_code == 409 and stale.get_json()["error"] == "map_changed"
    assert len(stale.get_json()["map"]["tables"]) == 2, "the other researcher's version comes back"
    assert client.get(f"{BASE}/map.json").get_json()["map"]["placements"] == {"1": {"table": "t1"}}


def test_a_room_is_made_from_a_session_and_reused_by_another(app):
    client, _ = signed_in(app)
    save(client, {"tables": TABLES, "placements": {"1": {"table": "t1"}}}, 0)
    made = client.post("/dashboard/rooms", data={"csrf": token(client), "name": "Aula 4a", "session_id": SESSION}).get_json()
    assert made["room"]["name"] == "Aula 4a" and "placements" not in made["room"]
    other = "/dashboard/sessions/grade-4-session-2"
    copied = client.post(f"{other}/map/room", data={"csrf": token(client), "revision": 0, "room_id": made["room"]["id"]})
    assert copied.status_code == 200
    copy = copied.get_json()["map"]
    assert copy["tables"] == made["room"]["tables"] and copy["placements"] == {}, "no IDs of the other class"
    stale = client.post(f"/dashboard/rooms/{made['room']['id']}", data={"csrf": token(client), "revision": 7, "session_id": SESSION})
    assert stale.status_code == 409 and stale.get_json()["error"] == "room_changed"


def test_a_floor_plan_is_uploaded_checked_and_served_only_to_researchers(app):
    client, _ = signed_in(app)
    uploaded = client.post(f"{BASE}/map/image", data={"csrf": token(client), "image": (BytesIO(picture()), "plan.png")},
                           content_type="multipart/form-data")
    name = uploaded.get_json()["image"]
    served = client.get(f"/dashboard/room-images/{name}")
    assert served.status_code == 200 and served.mimetype == "image/png" and served.headers["X-Content-Type-Options"] == "nosniff"
    assert app.test_client().get(f"/dashboard/room-images/{name}").status_code == 401
    refused = client.post(f"{BASE}/map/image", data={"csrf": token(client), "image": (BytesIO(b"<svg/>"), "plan.png")},
                          content_type="multipart/form-data")
    assert refused.status_code == 400 and refused.get_json()["error"] == "invalid_image"


def test_the_health_feed_lists_the_class_and_each_registered_tablet(app):
    client, state = signed_in(app)
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
    client, state = signed_in(app)
    rooms_file = app.config["RESEARCH_STATE_DIR"] + "/rooms.sqlite3"
    before = open(rooms_file, "rb").read()
    for _ in range(3):
        client.get(f"{BASE}/map.json")
        client.get(f"{BASE}/health.json")
    assert open(rooms_file, "rb").read() == before
