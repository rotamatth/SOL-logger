"""An accepted save with a lost response can reconcile without a false conflict."""
from .test_editor_browser import (EDITOR, RECOVERY, action, app, leave_by_link, live,
                                  tone, until)  # noqa: F401 - pytest fixtures


def test_accepted_autosave_with_a_lost_response_reconciles_before_leaving(live):
    page = live.login()
    page.goto(live.base + EDITOR)
    assert until(page, lambda: tone(page) == "muted")
    accepted = []
    conflicts = []

    def lose_first_save_response(route):
        if route.request.method == "POST" and action(route.request) == "save":
            response = route.fetch()  # Commit the write before dropping its response.
            if not accepted:
                assert response.status == 200
                accepted.append(response.json()["recovery"]["sequence"])
                route.abort()
                return
            if response.status == 409:
                conflicts.append(response.json())
            route.fulfill(response=response)
        else:
            route.continue_()

    page.route("**" + RECOVERY + "**", lose_first_save_response)
    page.fill("[name=question_0]", "Accepted write whose response was lost")
    assert until(page, lambda: tone(page) == "error")
    assert live.server_copy()["question_0"] == "Accepted write whose response was lost"
    leave_by_link(page)
    page.wait_for_url("**/dashboard/?lang=en", timeout=8000)
    assert len(accepted) == len(conflicts) == 1
    assert live.dialogs == []
    assert live.server_copy()["question_0"] == "Accepted write whose response was lost"


def test_a_different_edit_after_a_lost_response_does_not_adopt_the_previous_copy(live):
    page = live.login()
    page.goto(live.base + EDITOR)
    assert until(page, lambda: tone(page) == "muted")
    accepted = []

    def lose_first_save_response(route):
        if route.request.method == "POST" and action(route.request) == "save" and not accepted:
            response = route.fetch()
            assert response.status == 200
            accepted.append(True)
            route.abort()
        else:
            route.continue_()

    page.route("**" + RECOVERY + "**", lose_first_save_response)
    page.fill("[name=question_0]", "Accepted earlier version")
    assert until(page, lambda: tone(page) == "error")
    page.fill("[name=question_0]", "Different current text must remain visible")
    assert until(page, lambda: "Another tab" in page.inner_text("[data-editor-status]"))
    assert page.input_value("[name=question_0]") == "Different current text must remain visible"
    assert live.server_copy()["question_0"] == "Accepted earlier version"
