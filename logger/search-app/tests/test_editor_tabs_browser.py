"""Unsaved work in other dashboard tabs is considered before browser-wide logout."""
import pytest

from .test_editor_browser import EDITOR, Gate, app, live, tone, until  # noqa: F401
from .test_dashboard_ux_browser import confirmation_page

OVERVIEW = '/dashboard?collection=study&grade=4&lang=en'
PREPARE = '/dashboard/prepare?grade=4&year=2026/2027&session=grade-4-session-1&lang=en'


def test_clean_overview_warns_for_other_tab_then_rebinds_text_after_relogin(live):
    editor = live.login()
    editor.goto(live.base + EDITOR)
    editor.fill('[name=question_0]', 'Text in another tab')
    assert until(editor, lambda: tone(editor) == 'ok')
    overview, choice = confirmation_page(live, login=False)
    overview.goto(live.base + OVERVIEW)
    overview.locator('form[action*="logout"] button').click()
    assert until(overview, lambda: bool(live.dialogs))
    assert 'other tabs' in live.dialogs[-1]
    assert overview.url == live.base + OVERVIEW
    assert live.server_copy()['question_0'] == 'Text in another tab'
    choice['accept'] = True
    with overview.expect_navigation():
        overview.locator('form[action*="logout"] button').click()
    assert '/login' in overview.url
    assert until(editor, lambda: tone(editor) == 'error')
    assert editor.input_value('[name=question_0]') == 'Text in another tab'
    # The revoked session cannot save, even with the old CSRF token.
    assert live.context.request.get(live.base + '/dashboard/session').status == 401
    live.login(overview)
    editor.locator('[data-editor-status] button').click()
    assert until(editor, lambda: live.server_copy().get('question_0') == 'Text in another tab')
    assert until(editor, lambda: tone(editor) == 'ok')


@pytest.mark.parametrize('use_channel', [True, False])
def test_logout_warns_for_live_unprotected_plain_form(live, use_channel):
    if not use_channel:
        live.context.add_init_script('window.BroadcastChannel = undefined')
    editing = live.login()
    editing.goto(live.base + PREPARE)
    editing.fill('#prepare-name', 'Not autosaved anywhere')
    overview, _ = confirmation_page(live, login=False)
    overview.goto(live.base + OVERVIEW)
    overview.locator('form[action*="logout"] button').click()
    assert until(overview, lambda: bool(live.dialogs))
    assert 'unsaved changes' in live.dialogs[-1]
    assert editing.input_value('#prepare-name') == 'Not autosaved anywhere'
    flags = editing.evaluate("Object.keys(localStorage).filter(k => k.startsWith('sol-research-unsaved:')).map(k => localStorage.getItem(k))")
    assert flags and all(flag.isdigit() for flag in flags)  # No form text stored client-side.


def test_closed_editor_copy_still_triggers_server_warning(live):
    editor = live.login()
    editor.goto(live.base + EDITOR)
    editor.fill('[name=question_0]', 'Closed tab copy')
    assert until(editor, lambda: tone(editor) == 'ok')
    editor.close()
    overview, _ = confirmation_page(live, login=False)
    overview.goto(live.base + OVERVIEW)
    overview.evaluate("Object.keys(localStorage).filter(k => k.startsWith('sol-research-unsaved:')).forEach(k => localStorage.removeItem(k))")
    overview.locator('form[action*="logout"] button').click()
    assert until(overview, lambda: bool(live.dialogs))
    assert 'private recovery copies' in live.dialogs[-1]
    assert live.server_copy()['question_0'] == 'Closed tab copy'


def test_failed_logout_preflight_warns_but_still_allows_revocation(live):
    page, choice = confirmation_page(live)
    page.goto(live.base + OVERVIEW)
    page.route('**/editor/logout-check**', lambda route: route.abort())
    page.locator('form[action*="logout"] button').click()
    assert until(page, lambda: bool(live.dialogs))
    assert 'Unable to check' in live.dialogs[-1]
    assert live.context.request.get(live.base + '/dashboard/session').status == 200
    choice['accept'] = True
    with page.expect_navigation():
        page.locator('form[action*="logout"] button').click()
    assert live.context.request.get(live.base + '/dashboard/session').status == 401
