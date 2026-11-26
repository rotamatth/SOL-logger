"""Classrooms drawn to scale: desks, islands and landmarks, tablet spots, and each session's copy with its IDs."""
import json
from pathlib import Path

import pytest

from research_dashboard.rooms import Conflict, Rooms, spot_ids, validate_geometry
from .test_live_view import signed_in
from .test_research_dashboard import app, configure  # noqa: F401

SESSION = "grade-4-session-1"
ROOM = {"width": 800, "depth": 600, "pieces": [
    {"id": "board", "kind": "board", "x": 400, "y": 10},
    {"id": "a", "kind": "desk", "x": 120, "y": 300},
    {"id": "b", "kind": "desk", "x": 330, "y": 480, "rotation": -15, "tablets": 2},
    {"id": "i", "kind": "island", "x": 330, "y": 300, "rotation": 90, "desks": 4},
]}


@pytest.fixture
def rooms(tmp_path):
    return Rooms(tmp_path)


def test_a_room_is_measured_in_centimetres_and_every_desk_has_its_tablet_spots():
    room = validate_geometry(ROOM)
    assert room["width"] == 800 and room["pieces"][2]["rotation"] == 345.0, "turning stays within one circle"
    assert room["pieces"][0] == {"id": "board", "kind": "board", "x": 400.0, "y": 10.0, "rotation": 0.0}, "landmarks hold no tablet"
    assert spot_ids(room) == ["a.0.0", "b.0.0", "b.0.1", "i.0.0", "i.1.0", "i.2.0", "i.3.0"]


@pytest.mark.parametrize("change", [
    {"width": 150}, {"depth": 3500}, {"width": True},
    {"pieces": [{"id": "a", "kind": "desk", "x": 900, "y": 10}]},
    {"pieces": [{"id": "a", "kind": "sofa", "x": 10, "y": 10}]},
    {"pieces": [{"id": "a", "kind": "desk", "x": 10, "y": 10}, {"id": "a", "kind": "desk", "x": 20, "y": 10}]},
    {"pieces": [{"id": "a b", "kind": "desk", "x": 10, "y": 10}]},
    {"pieces": [{"id": "a", "kind": "desk", "x": 10, "y": 10, "tablets": 3}]},
    {"pieces": [{"id": "a", "kind": "island", "x": 10, "y": 10, "desks": 3}]},
    {"pieces": "nope"},
])
def test_a_bad_room_is_refused_whole(rooms, change):
    with pytest.raises(ValueError, match="invalid_room"):
        rooms.create_room("Aula 4a", {**ROOM, **change})
    assert rooms.rooms() == []


def test_two_named_rooms_are_listed_with_their_size_and_desks(rooms):
    rooms.create_room("Aula del mattino", ROOM)
    rooms.create_room("aula del pomeriggio", {"width": 750, "depth": 650, "pieces": []})
    listed = rooms.rooms()
    assert [room["name"] for room in listed] == ["Aula del mattino", "aula del pomeriggio"]
    assert (listed[0]["desks"], listed[0]["spots"], listed[0]["width"]) == (6, 7, 800.0)
    with pytest.raises(ValueError, match="invalid_room_name"):
        rooms.create_room("   ", ROOM)


def test_two_open_dashboards_cannot_silently_overwrite_a_room(rooms):
    room = rooms.create_room("Aula 4a", ROOM)
    rooms.update_room(room["id"], 1, {**ROOM, "width": 900})
    with pytest.raises(Conflict) as stale:
        rooms.update_room(room["id"], 1, {**ROOM, "width": 700})
    assert stale.value.current["width"] == 900 and stale.value.current["revision"] == 2
    with pytest.raises(Conflict):
        rooms.delete_room(room["id"], 1)
    rooms.delete_room(room["id"], 2)
    assert rooms.room(room["id"]) is None


def test_a_session_works_on_its_copy_and_ids_go_on_spots(rooms):
    room = rooms.create_room("Aula 4a", ROOM)
    assert rooms.session_map(SESSION)["revision"] == 0
    copy = rooms.use_room(SESSION, room["id"], 0)
    assert copy["room_id"] == room["id"] and copy["room_revision"] == 1 and copy["placements"] == {}
    placed = rooms.place(SESSION, "001", "b.0.1")
    placed = rooms.place(SESSION, "C-7", "i.2.0")
    assert placed["placements"] == {"001": "b.0.1", "C-7": "i.2.0"}, "IDs stay exact strings"
    assert "placements" not in rooms.room(room["id"]), "a room never carries a class's IDs"
    moved = rooms.place(SESSION, "001", "a.0.0")
    assert moved["placements"]["001"] == "a.0.0" and moved["revision"] == 4
    assert "001" not in rooms.place(SESSION, "001", "")["placements"], "no spot puts the ID back among the unplaced"


def test_a_spot_taken_meanwhile_or_missing_is_refused(rooms):
    room = rooms.create_room("Aula 4a", ROOM)
    rooms.use_room(SESSION, room["id"], 0)
    rooms.place(SESSION, "1", "a.0.0")
    with pytest.raises(Conflict) as taken:
        rooms.place(SESSION, "2", "a.0.0")
    assert taken.value.current["placements"] == {"1": "a.0.0"}
    with pytest.raises(ValueError, match="spot_missing"):
        rooms.place(SESSION, "2", "z.0.0")
    with pytest.raises(ValueError, match="no_room"):
        rooms.place("grade-5-session-1", "2", "a.0.0")


def test_a_room_edited_later_reaches_a_session_only_when_brought_in_and_keeps_its_ids(rooms):
    room = rooms.create_room("Aula 4a", ROOM)
    rooms.use_room(SESSION, room["id"], 0)
    rooms.place(SESSION, "1", "a.0.0")
    rooms.place(SESSION, "2", "b.0.1")
    fewer = {**ROOM, "pieces": [piece if piece["id"] != "b" else {**piece, "tablets": 1} for piece in ROOM["pieces"]]}
    rooms.update_room(room["id"], 1, fewer)
    assert rooms.session_map(SESSION)["room_revision"] == 1, "the session keeps its copy until asked"
    refreshed = rooms.use_room(SESSION, room["id"], 3)
    assert refreshed["room_revision"] == 2 and refreshed["placements"] == {"1": "a.0.0"}, "the ID whose spot went is unplaced"


def test_a_session_map_change_based_on_an_old_copy_is_refused(rooms):
    room = rooms.create_room("Aula 4a", ROOM)
    rooms.use_room(SESSION, room["id"], 0)
    with pytest.raises(Conflict):
        rooms.use_room(SESSION, room["id"], 0)


def test_deleting_a_room_leaves_the_sessions_copies_alone(rooms):
    room = rooms.create_room("Aula 4a", ROOM)
    rooms.use_room(SESSION, room["id"], 0)
    rooms.place(SESSION, "1", "a.0.0")
    rooms.delete_room(room["id"], 1)
    kept = rooms.session_map(SESSION)
    assert kept["placements"] == {"1": "a.0.0"} and len(kept["pieces"]) == 4


# -- The Rooms page's endpoints -------------------------------------------------------------------------------------

def token(client):
    return client.get("/dashboard/classrooms.json").get_json()["csrf"]


def test_the_rooms_need_a_researcher(app):
    configure(app)
    client = app.test_client()
    assert client.get("/dashboard/classrooms.json").status_code == 401
    assert client.get("/dashboard/classrooms").status_code in (302, 303)
    assert client.post("/dashboard/classrooms", data={"name": "x", "room": json.dumps(ROOM)}).status_code in (400, 401)


def test_a_room_is_drawn_changed_and_deleted_through_the_dashboard(app):
    client, _ = signed_in(app)
    page = client.get("/dashboard/classrooms?lang=it")
    assert page.status_code == 200 and b'id="room-editor"' in page.data and "Banco doppio".encode() in page.data
    refused = client.post("/dashboard/classrooms", data={"name": "Aula 4a", "room": json.dumps(ROOM)})
    assert refused.status_code == 400 and refused.get_json()["error"] == "csrf_error"
    made = client.post("/dashboard/classrooms", data={"csrf": token(client), "name": "Aula 4a", "room": json.dumps(ROOM)}).get_json()
    room = made["room"]
    assert room["name"] == "Aula 4a" and len(room["pieces"]) == 4 and made["rooms"][0]["spots"] == 7
    assert client.get(f"/dashboard/classrooms/{room['id']}.json").get_json()["room"]["pieces"] == room["pieces"]
    bad = client.post("/dashboard/classrooms", data={"csrf": token(client), "name": "Aula 4a", "room": json.dumps({**ROOM, "width": 5})})
    assert bad.status_code == 400 and bad.get_json()["error"] == "invalid_room"
    changed = client.post(f"/dashboard/classrooms/{room['id']}", data={"csrf": token(client), "revision": 1, "name": "Aula 4b",
                                                                       "room": json.dumps({**ROOM, "width": 900})})
    assert changed.status_code == 200 and changed.get_json()["room"]["name"] == "Aula 4b"
    stale = client.post(f"/dashboard/classrooms/{room['id']}", data={"csrf": token(client), "revision": 1, "name": "Aula 4c",
                                                                     "room": json.dumps(ROOM)})
    assert stale.status_code == 409 and stale.get_json()["error"] == "room_changed" and stale.get_json()["room"]["width"] == 900
    assert client.post(f"/dashboard/classrooms/{room['id']}/delete", data={"csrf": token(client), "revision": 1}).status_code == 409
    gone = client.post(f"/dashboard/classrooms/{room['id']}/delete", data={"csrf": token(client), "revision": 2})
    assert gone.status_code == 200 and gone.get_json()["rooms"] == []
    assert client.get(f"/dashboard/classrooms/{room['id']}.json").status_code == 404


def test_reading_the_rooms_writes_nothing(app):
    client, _ = signed_in(app)
    rooms_file = Path(app.config["RESEARCH_STATE_DIR"]) / "rooms.sqlite3"
    client.post("/dashboard/classrooms", data={"csrf": token(client), "name": "Aula 4a", "room": json.dumps(ROOM)})
    before = rooms_file.read_bytes()
    for _ in range(3):
        client.get("/dashboard/classrooms")
        client.get("/dashboard/classrooms.json")
    assert rooms_file.read_bytes() == before
