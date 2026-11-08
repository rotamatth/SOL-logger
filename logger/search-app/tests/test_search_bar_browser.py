"""The search row: "Cerca" right after the bar, the ✕ only while there is something to clear, all centred."""
from .test_student_navigation_browser import student_browser  # noqa: F401 - fixture

ROW = """() => {
    const box = element => element.getBoundingClientRect();
    const form = document.getElementById('search-bar');
    const input = box(document.getElementById('search-box'));
    const submit = box(document.getElementById('submit-box'));
    const help = document.getElementById('task-help-btn');
    const clear = document.getElementById('clear-search-btn');
    const area = box(form.parentElement);
    return {left: help ? box(help).left : input.left, right: submit.right, inputRight: input.right,
            submitLeft: submit.left, clear: getComputedStyle(clear).display === 'none' ? null : box(clear).toJSON(),
            areaLeft: area.left, areaRight: area.right};
}"""


def centred(row):
    return abs((row["left"] - row["areaLeft"]) - (row["areaRight"] - row["right"])) <= 2


def test_cerca_sits_after_the_bar_and_the_clear_button_takes_room_only_when_needed(student_browser):
    page = student_browser
    page.fill("#search-box", "")
    empty = page.evaluate(ROW)
    assert empty["clear"] is None and centred(empty)
    assert 0 <= empty["submitLeft"] - empty["inputRight"] <= 20, "Cerca is not next to the bar"
    page.fill("#search-box", "fasi della luna")
    typed = page.evaluate(ROW)
    assert typed["clear"] is not None and centred(typed)
    assert typed["inputRight"] <= typed["clear"]["left"] and typed["clear"]["right"] <= typed["submitLeft"]
    assert abs(typed["left"] - empty["left"]) <= 1 and abs(typed["right"] - empty["right"]) <= 1
    page.click("#clear-search-btn")
    assert page.evaluate(ROW)["clear"] is None and page.input_value("#search-box") == ""
