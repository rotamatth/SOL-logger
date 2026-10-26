"""Selection and edit-loss regressions against isolated synthetic dashboards."""
from urllib.parse import parse_qs

import pytest

from .test_editor_browser import EDITOR, app, live, tone, until  # noqa: F401
from .test_research_dashboard import write_run

PREPARE = "/dashboard/prepare?grade=4&year=2026/2027&session=grade-4-session-1&lang=en"


def confirmation_page(live, login=True):
    choice = {"accept": False}
    page = live.context.new_page()

    def confirm(dialog):
        live.dialogs.append(dialog.message)
        dialog.accept() if choice["accept"] else dialog.dismiss()

    page.on("dialog", confirm)
    return live.login(page) if login else page, choice


@pytest.mark.parametrize("language,touch", [("en", False), ("it", True)])
def test_bulk_selection_counts_only_available_rows_and_submits_them(live, language, touch):
    write_run(live.app, uid="1", suffix="selection-one")
    write_run(live.app, uid="2", suffix="selection-two")
    if touch:
        browser = live.context.browser
        live.context.close()
        live.context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
    page = live.login()
    page.goto(f"{live.base}/dashboard?collection=study&grade=4&lang={language}")
    rows = page.locator('input[name="participant"]')
    master = page.locator('[data-select-all]')
    assert rows.count() == 2  # The other enrolled IDs have no logs to select.
    assert page.inner_text('[data-selection-count]') == "0"
    rows.first.check()
    assert page.inner_text('[data-selection-count]') == "1"
    assert master.evaluate('(input) => input.indeterminate')
    master.check()
    assert page.inner_text('[data-selection-count]') == "2"
    assert not master.evaluate('(input) => input.indeterminate')
    assert rows.evaluate_all('(inputs) => inputs.every(input => input.checked)')
    master.uncheck()
    assert page.inner_text('[data-selection-count]') == "0"
    assert page.locator('.dashboard-selection-empty').is_visible()
    rows.last.check()
    with page.expect_request('**/exports/selection**') as request, page.expect_download():
        page.locator('.dashboard-selection-ready').click()
    submitted = parse_qs(request.value.post_data)
    assert submitted['participant'] == [rows.last.input_value()]
    assert submitted['mode'] == ['selected']


def test_keyboard_skip_link_reaches_main_content(live):
    page = live.login()
    page.goto(live.base + '/dashboard?collection=study&grade=4&lang=it')
    page.keyboard.press('Tab')
    assert page.locator('.skip-link').evaluate('(link) => link === document.activeElement')
    assert page.locator('.skip-link').inner_text() == 'Vai al contenuto'
    page.keyboard.press('Enter')
    assert page.locator('#main-content').evaluate('(main) => main === document.activeElement')


@pytest.mark.parametrize('submit_ids', [True, False])
def test_submitting_one_preparation_form_warns_about_the_other(live, submit_ids):
    page, choice = confirmation_page(live)
    page.goto(live.base + PREPARE)
    page.fill('#prepare-name', 'Details to keep')
    page.locator('.preparation-add summary').click()
    page.fill('#prepare-ids', 'SYNTH-NEW')
    before = page.url
    target = '.preparation-add' if submit_ids else '.preparation-details'
    page.locator(target + ' button[type=submit]').click()
    assert live.dialogs and 'unsaved changes' in live.dialogs[-1]
    assert page.url == before  # The fixture dismisses the warning.
    assert page.input_value('#prepare-name') == 'Details to keep'
    assert page.input_value('#prepare-ids') == 'SYNTH-NEW'
    # Accepting the warning still submits the chosen form normally.
    choice['accept'] = True
    with page.expect_navigation():
        page.locator(target + ' button[type=submit]').click()
    assert page.url != before
    if not submit_ids:
        assert live.app.extensions['research']['state'].settings()['sessions'][0]['name'] == 'Details to keep'


def test_logout_warns_before_deleting_protected_unsaved_edits(live):
    page, choice = confirmation_page(live)
    page.goto(live.base + EDITOR)
    page.fill('[name=question_0]', 'Protected text to keep')
    assert until(page, lambda: tone(page) == 'ok')
    page.locator('form[action*="logout"] button').click()
    assert until(page, lambda: bool(live.dialogs))
    assert 'unsaved changes' in live.dialogs[-1]
    assert page.url == live.base + EDITOR
    assert live.server_copy()['question_0'] == 'Protected text to keep'
    choice['accept'] = True
    with page.expect_navigation():
        page.locator('form[action*="logout"] button').click()
    assert '/login' in page.url
    live.login(page)
    assert live.server_copy() == {}
