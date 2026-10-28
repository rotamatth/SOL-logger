"""Logout revocation and editor retries cannot leave a false protection claim."""
from .test_editor_browser import EDITOR, Gate, app, live, tone, until  # noqa: F401
from .test_dashboard_ux_browser import confirmation_page


def test_delayed_logout_invalidates_after_actual_revocation(live):
    editor = live.login()
    editor.goto(live.base + EDITOR)
    editor.fill('[name=question_0]', 'Keep this text')
    assert until(editor, lambda: tone(editor) == 'ok')
    page, choice = confirmation_page(live, login=False)
    page.goto(live.base + '/dashboard?grade=4&lang=en')
    gate = Gate(page, 'POST', '**/logout**')
    choice['accept'] = True
    page.locator('form[action*="logout"] button').click()
    assert until(page, lambda: bool(gate.held))
    # Retry/focus while the server has not yet revoked does not invalidate a live copy.
    editor.evaluate("dispatchEvent(new Event('focus'))")
    assert tone(editor) == 'ok'
    gate.release()
    page.wait_for_url('**/login**')
    assert until(editor, lambda: tone(editor) == 'error')
    assert editor.input_value('[name=question_0]') == 'Keep this text'
    assert live.context.request.get(live.base + '/dashboard/session').status == 401
    live.login(page)
    editor.locator('[data-editor-status] button').click()
    assert until(editor, lambda: live.server_copy().get('question_0') == 'Keep this text')


def test_persisted_pagehide_keeps_dirty_flag_for_suspended_tab(live):
    page = live.login()
    page.goto(live.base + '/dashboard/prepare?grade=4&year=2026/2027&session=grade-4-session-1')
    page.fill('#prepare-name', 'Suspended edits')
    page.evaluate("dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}))")
    assert page.evaluate("Object.keys(localStorage).some(k => k.startsWith('sol-research-unsaved:'))")
