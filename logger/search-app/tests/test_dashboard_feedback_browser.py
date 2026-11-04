"""Researcher feedback of 3 November 2026 in a real browser: logout, ID pop-ups, run selection."""
from urllib.parse import parse_qs

from .test_dashboard_ux_browser import PREPARE, answer_logout, confirmation_page
from .test_editor_browser import app, live, until  # noqa: F401 - shared synthetic fixture
from .test_research_dashboard import write_run

YEAR = "2026/2027"


def test_logo_goes_home_and_logout_asks_si_or_no_first(live):
    page, _ = confirmation_page(live)
    page.goto(live.base + "/dashboard/settings?section=year&grade=4&lang=it")
    with page.expect_navigation():
        page.locator("a.header-logo").click()
    assert "/dashboard/prepare" in page.url
    page.locator('form[action*="logout"] button').click()
    dialog = page.locator("#logout-dialog")
    dialog.wait_for(state="visible")
    assert page.inner_text("#logout-dialog-text") == "Sei sicuro di voler uscire?"
    assert dialog.locator("button").all_inner_texts() == ["No", "Sì"]
    page.keyboard.press("Escape")  # Esc answers No.
    dialog.wait_for(state="hidden")
    assert answer_logout(page, accept=False) == "Sei sicuro di voler uscire?"
    assert live.context.request.get(live.base + "/dashboard/session").status == 200  # "No" keeps the session.
    with page.expect_navigation():
        answer_logout(page, accept=True)
    assert "/login" in page.url
    assert live.context.request.get(live.base + "/dashboard/session").status == 401
    assert not live.dialogs  # No browser confirmation box any more.


def test_warnings_carry_their_own_colour_and_icon(live):
    page = live.login()
    page.goto(live.base + PREPARE.replace("grade-4-session-1", "grade-4-session-2"))  # Undated: setup incomplete.
    summary = page.locator(".session-status-summary.warning")
    assert summary.count() == 1
    icon = summary.evaluate("(node) => getComputedStyle(node, '::before').maskImage || getComputedStyle(node, '::before').webkitMaskImage")
    assert "icon-warning.svg" in icon
    assert summary.evaluate("(node) => getComputedStyle(node).backgroundColor") == "rgb(253, 238, 230)"


def test_import_pop_up_needs_a_choice_then_moves_the_child_after_review(live):
    page = live.login()
    page.goto(live.base + PREPARE)
    page.locator('[data-open-dialog="import-ids-dialog"]').click()
    dialog = page.locator("#import-ids-dialog")
    assert dialog.evaluate("(node) => node.open")
    submit = dialog.locator("button[type=submit]")
    assert submit.is_disabled()
    dialog.locator('input[value="21"]').check()
    assert submit.is_enabled()
    with page.expect_navigation():
        submit.click()
    assert "ID 21" in page.inner_text("main")
    with page.expect_navigation():
        page.locator('form:has(input[name="action"][value="confirm"]) button[type=submit]').click()
    state = live.app.extensions["research"]["state"]
    assert state.settings()["enrollments"][YEAR]["21"]["grade"] == "4"


def test_create_pop_up_flags_existing_ids_and_escape_discards_them(live):
    page = live.login()
    page.goto(live.base + PREPARE)
    page.locator('[data-open-dialog="create-ids-dialog"]').click()
    page.fill("#create-ids", "41, 21")
    check = page.locator("#create-ids-check")
    assert check.is_visible()
    assert check.inner_text().endswith(" 21")
    page.keyboard.press("Escape")
    assert not page.locator("#create-ids-dialog").evaluate("(node) => node.open")
    assert page.input_value("#create-ids") == ""
    assert until(page, lambda: check.is_hidden())


def test_ticking_runs_offers_and_downloads_only_those(live):
    first = write_run(live.app, suffix="first")[0]
    write_run(live.app, suffix="second")
    page = live.login()
    page.goto(live.base + "/dashboard?collection=study&grade=4&lang=en")
    with page.expect_navigation():
        page.locator("a.dashboard-view:not(.dashboard-manage)").first.click()
    assert page.locator(".run-selection-empty").is_visible()
    assert not page.locator(".run-selection-ready").is_visible()
    page.locator(f'input.run-select[value="{first}"]').check()
    assert page.locator(".run-selection-ready").is_visible()
    with page.expect_request("**/exports/runs**") as request, page.expect_download():
        page.locator(".run-selection-ready").click()
    assert parse_qs(request.value.post_data)["run"] == [first]
