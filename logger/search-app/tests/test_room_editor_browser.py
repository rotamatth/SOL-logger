"""In a real browser: the Rooms page draws a classroom to scale, moves and turns its pieces, undoes, and saves safely."""
from .test_editor_browser import app, live, until  # noqa: F401

PAGE = "/dashboard/classrooms?lang=en"
ROOM = {"width": 800, "depth": 600, "pieces": [
    {"id": "a", "kind": "desk", "x": 200, "y": 300, "rotation": 0, "tablets": 1},
    {"id": "b", "kind": "desk", "x": 500, "y": 450, "rotation": 0, "tablets": 1},
]}


def rooms(live):
    return live.app.extensions["research"]["rooms"]


def opened(live, path=PAGE):
    page = live.login()
    page.set_viewport_size({"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(live.base + path)
    page.wait_for_selector("#room-floor .room-floor-area")
    return page, errors


def client_point(page, x, y):
    """Centimetres in the room to the page's pixels."""
    return page.evaluate("([x, y]) => { const p = new DOMPoint(x, y).matrixTransform(document.getElementById('room-floor')"
                         ".getScreenCTM()); return [p.x, p.y]; }", [x, y])


def drag(page, start, end, alt=False):
    page.mouse.move(*client_point(page, *start))
    page.mouse.down()
    if alt:
        page.keyboard.down("Alt")
    page.mouse.move(*client_point(page, *end), steps=8)
    page.mouse.up()
    if alt:
        page.keyboard.up("Alt")


def test_a_first_room_is_drawn_named_and_saved(live):
    page, errors = opened(live)
    assert "No room yet" in page.inner_text("#room-message")
    page.click("#room-palette [data-kind=island][data-desks='4']")
    assert page.locator("#room-floor .room-kind-island .room-desk").count() == 4
    assert page.inner_text("#room-props h3").startswith("Island of 4 desks")
    page.locator("#room-props .room-segmented", has=page.locator("button", has_text="2")).last.locator("button", has_text="2").click()
    assert page.locator("#room-floor .room-spot-outline").count() == 8, "two tablet spots on each of the four desks"
    page.click("#room-save")
    assert "Give the room a name" in page.inner_text("#room-message")
    page.fill("#room-name", "Aula 4a")
    page.click("#room-save")
    assert until(page, lambda: page.inner_text("#room-message") == "Room saved.", seconds=4)
    saved = rooms(live).rooms()
    assert len(saved) == 1 and saved[0]["name"] == "Aula 4a" and saved[0]["spots"] == 8
    page.reload()
    page.wait_for_selector("#room-floor .room-kind-island")
    assert "Aula 4a" in page.inner_text("#room-list") and "8 × 6 m · 4 desks" in page.inner_text("#room-list")
    assert errors == []


def test_a_piece_dragged_near_another_lines_up_with_it_and_turns_by_15_degrees(live):
    room = rooms(live).create_room("Aula 4a", ROOM)
    page, errors = opened(live, PAGE.replace("?", f"?room={room['id']}&"))
    drag(page, (500, 450), (512, 306))
    moved = page.evaluate("document.querySelector('[data-piece=b]').getAttribute('transform')")
    assert moved.startswith("translate(510 300)"), "snapped to 10 cm and lined up with desk a"
    page.keyboard.press("r")
    page.keyboard.press("r")
    assert "rotate(30)" in page.evaluate("document.querySelector('[data-piece=b]').getAttribute('transform')")
    assert page.input_value("#room-rotation") == "30"
    knob = page.locator("[data-handle=b]").bounding_box()
    page.mouse.move(knob["x"] + knob["width"] / 2, knob["y"] + knob["height"] / 2)
    page.mouse.down()
    page.mouse.move(*client_point(page, 610, 300), steps=6)  # Straight to the right of the desk: a quarter turn.
    page.mouse.up()
    assert "rotate(90)" in page.evaluate("document.querySelector('[data-piece=b]').getAttribute('transform')")
    assert errors == []


def test_undo_and_redo_walk_back_and_forth_through_the_changes(live):
    room = rooms(live).create_room("Aula 4a", ROOM)
    page, _ = opened(live, PAGE.replace("?", f"?room={room['id']}&"))
    page.locator("[data-piece=a]").click()
    page.keyboard.press("ArrowRight")
    page.keyboard.press("Shift+ArrowDown")
    assert page.evaluate("document.querySelector('[data-piece=a]').getAttribute('transform')").startswith("translate(210 350)")
    assert "not saved" in page.inner_text("#room-message")
    page.keyboard.press("Control+z")
    page.keyboard.press("Control+z")
    assert page.evaluate("document.querySelector('[data-piece=a]').getAttribute('transform')").startswith("translate(200 300)")
    page.click("#room-redo")
    assert page.evaluate("document.querySelector('[data-piece=a]').getAttribute('transform')").startswith("translate(210 300)")
    page.locator("[data-piece=a]").focus()
    page.keyboard.press("Delete")
    assert page.locator("[data-piece=a]").count() == 0
    page.click("#room-undo")
    assert page.locator("[data-piece=a]").count() == 1


def test_a_piece_dragged_from_the_palette_lands_where_it_is_let_go(live):
    page, _ = opened(live)
    button = page.locator("#room-palette [data-kind=board]").bounding_box()
    page.mouse.move(button["x"] + 20, button["y"] + button["height"] / 2)
    page.mouse.down()
    page.mouse.move(*client_point(page, 400, 20), steps=10)
    page.mouse.up()
    board = page.locator("#room-floor .room-kind-board")
    assert board.count() == 1 and board.get_attribute("transform").startswith("translate(400 20)")


def test_a_change_saved_meanwhile_elsewhere_is_not_overwritten(live):
    room = rooms(live).create_room("Aula 4a", ROOM)
    page, _ = opened(live, PAGE.replace("?", f"?room={room['id']}&"))
    page.click("#room-palette [data-kind=teacher]")
    rooms(live).update_room(room["id"], 1, {**ROOM, "width": 900})  # Another dashboard saved first.
    page.click("#room-save")
    assert until(page, lambda: "Someone else saved this room" in page.inner_text("#room-message"), seconds=4)
    assert page.locator("#room-floor .room-kind-teacher").count() == 0 and page.input_value("#room-width") == "9.0"
    assert rooms(live).room(room["id"])["revision"] == 2


def test_leaving_a_room_with_unsaved_changes_asks_first(live):
    first = rooms(live).create_room("Aula 4a", ROOM)
    rooms(live).create_room("Aula 5b", ROOM)
    page, _ = opened(live, PAGE.replace("?", f"?room={first['id']}&"))
    page.click("#room-palette [data-kind=door]")
    page.locator("#room-list button", has_text="Aula 5b").click()
    assert live.dialogs and "changes not saved" in live.dialogs[-1], "the question was asked and refused"
    assert page.input_value("#room-name") == "Aula 4a" and page.locator("#room-floor .room-kind-door").count() == 1
