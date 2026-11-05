"""Logout checks disclose only whether this browser has private recovery."""
import pytest

from research_dashboard import editor_recovery
from research_dashboard.editor_recovery import EditorRecovery, TTL_SECONDS
from research_dashboard.state import identity
from .test_research_dashboard import app, csrf, login

CHECK = '/dashboard/editor/logout-check'


def test_logout_check_is_private_and_does_not_disclose_recovery_text(app):
    client = app.test_client()
    assert client.get(CHECK).status_code == 401
    login(client)
    assert client.get(CHECK).json['has_recovery'] is False
    owner = client.get_cookie('sol_research_editor', path='/dashboard').value
    store = EditorRecovery(app.config['RESEARCH_STATE_DIR'])
    credential = identity(app.config['RESEARCH_PASSWORD_HASH'])
    store.save(owner, credential, 'questions:synthetic:', {'question_0': 'PRIVATE TEXT'}, 0)
    response = client.get(CHECK)
    assert response.json == {'has_recovery': True, 'csrf': csrf(client.get('/dashboard'))}
    assert b'PRIVATE' not in response.data and b'questions:' not in response.data
    assert 'no-store' in response.headers['Cache-Control']
    other = app.test_client()
    login(other)
    assert other.get(CHECK).json['has_recovery'] is False
    token = csrf(client.get('/dashboard'))
    client.post('/dashboard/logout', data={'csrf': token})
    assert client.get(CHECK).status_code == 401
    assert not store.has_copies(owner, credential)


def test_logout_copy_check_excludes_expiry_tombstones_and_other_credentials(tmp_path, monkeypatch):
    now = 1800000000.0
    monkeypatch.setattr(editor_recovery.time, 'time', lambda: now)
    store = EditorRecovery(tmp_path)
    one = store.save('owner', 'credential', 'questions:one', {'question_0': 'One'}, 0)
    assert store.has_copies('owner', 'credential')
    assert not store.has_copies('other', 'credential')
    assert not store.has_copies('owner', 'other')
    store.clear('owner', 'credential', 'questions:one', one['sequence'])
    assert not store.has_copies('owner', 'credential')
    store.save('owner', 'credential', 'questions:two', {'question_0': 'Two'}, 0)
    now += TTL_SECONDS
    assert not store.has_copies('owner', 'credential')


def test_optional_copy_check_failure_never_prevents_actual_logout(app, monkeypatch):
    client = app.test_client()
    login(client)
    token = csrf(client.get('/dashboard'))
    monkeypatch.setattr(EditorRecovery, 'has_copies', lambda *args: (_ for _ in ()).throw(OSError('synthetic')))
    assert client.get(CHECK).status_code == 503
    assert client.post('/dashboard/logout', data={'csrf': token}).status_code == 302
    assert client.get('/dashboard').status_code == 302
