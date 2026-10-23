"""Permanent identity, yearly enrollment and migration use isolated synthetic data."""
import json
import sqlite3

import pytest

from research_dashboard.state import State, roster
from research_dashboard.participants import year_contains, resolve_identity, promotion_plan
from research_dashboard.study_config import scheduled_assignment
from html import unescape
import re
from .test_research_dashboard import app, csrf, login, configure, write_run, archive
from research_dashboard.state import identity
from .test_study_enrollment import question_set, student_modules


def configured(tmp_path):
    state = State(tmp_path / 'state')
    settings = state.settings()
    settings['current_school_year'] = '2026/2027'
    settings['sessions'][0].update(date='2026-10-19', school_year='2026/2027', question_set=question_set())
    state.save_settings(settings, settings['revision'])
    return state


def change(state, operation, **arguments):
    return state.change_participants(operation, arguments, state.settings()['revision'])


def test_school_year_uses_september_through_august():
    assert year_contains('2026/2027', '2026-09-01')
    assert year_contains('2026/2027', '2027-08-31')
    assert not year_contains('2026/2027', '2026-08-31')
    assert not year_contains('2026/2027', '2027-09-01')


def test_registry_reserves_inactive_ids_and_explicit_reactivation_keeps_identity(tmp_path):
    state = configured(tmp_path)
    key = state.settings()['participant_registry']['1']['key']
    change(state, 'update', uid='1', year='2026/2027', grade='4', active=False)
    assert '1' not in roster(state.settings())
    with pytest.raises(ValueError, match='reserved'):
        change(state, 'add', ids=['1'], year='2026/2027', grade='3')
    change(state, 'update', uid='1', year='2026/2027', grade='4', active=True)
    assert state.settings()['participant_registry']['1']['key'] == key


def test_promotion_preserves_ids_old_enrollment_and_session_year(tmp_path):
    state = configured(tmp_path)
    before = state.settings()
    change(state, 'promote', source_year='2026/2027', target_year='2027/2028')
    after = state.settings()
    assert after['enrollments']['2026/2027'] == before['enrollments']['2026/2027']
    assert after['participant_registry'] == before['participant_registry']
    assert roster(after)['1'] == '5'
    assert '21' not in roster(after)  # End of supported grades; ID stays reserved.
    assert after['sessions'][0]['school_year'] == '2026/2027'
    assert after['current_school_year'] == '2027/2028'


def test_conflicting_promotion_rolls_back_every_participant_and_revision(tmp_path):
    state = configured(tmp_path)
    change(state, 'update', uid='2', year='2027/2028', grade='3', active=True)
    before = state.settings()
    with pytest.raises(ValueError, match='enrollment_conflict'):
        change(state, 'promote', source_year='2026/2027', target_year='2027/2028')
    assert state.settings() == before


def test_missing_year_never_admits_and_future_current_year_does_not_relabel_session(tmp_path):
    from datetime import date
    state = State(tmp_path / 'state')
    settings = state.settings()
    settings['sessions'][0].update(date='2026-10-19', question_set=question_set())
    state.save_settings(settings, settings['revision'])
    assert scheduled_assignment(state.settings(), '1', date(2026,10,19)) is None
    settings = state.settings()
    settings['current_school_year'] = '2026/2027'
    settings['sessions'][0]['school_year'] = '2026/2027'
    state.save_settings(settings, settings['revision'])
    change(state, 'promote', source_year='2026/2027', target_year='2027/2028')
    assignment = scheduled_assignment(state.settings(), '1', date(2026,10,19))
    assert assignment['enrollment']['grade'] == '4'
    assert assignment['enrollment']['school_year'] == '2026/2027'


def test_legacy_links_are_explicit_date_scoped_and_reversible(tmp_path):
    state = configured(tmp_path)
    assert resolve_identity(state.settings(), 'legacy', '1', '2025-10-01') is None
    link = change(state, 'link', source_id='1', uid='1', date_from='2025-09-01',
                  date_to='2026-08-31', note='Confirmed against synthetic study register')
    resolved = resolve_identity(state.settings(), 'legacy', '1', '2025-10-01')
    assert resolved['id'] == '1' and resolved['link_id'] == link['id']
    assert resolve_identity(state.settings(), 'legacy', '1', '2024-10-01') is None
    with pytest.raises(ValueError, match='identity_link_conflict'):
        change(state, 'link', source_id='1', uid='2', date_from='2025-10-01',
               date_to='2026-07-01', note='Conflicting synthetic test')
    change(state, 'unlink', link_id=link['id'])
    assert resolve_identity(state.settings(), 'legacy', '1', '2025-10-01') is None
    with state.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM participant_links').fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM participant_audit WHERE operation='unlink'").fetchone()[0] == 1


def test_stale_identity_change_cannot_overwrite_newer_settings(tmp_path):
    state = configured(tmp_path)
    revision = state.settings()['revision']
    change(state, 'update', uid='1', year='2026/2027', grade='4', active=False)
    with pytest.raises(ValueError, match='settings_changed'):
        state.change_participants('update', dict(uid='1', year='2026/2027', grade='4', active=True), revision)


def test_migration_reserves_ids_from_prior_settings_without_linking_legacy(tmp_path):
    path = tmp_path / 'state'
    state = configured(tmp_path)
    first = state.settings()
    changed = state.settings()
    changed['ranges'][0]['start'] = 2
    state.save_settings(changed, changed['revision'])
    with state.connect() as db:
        db.execute('DROP TABLE participant_links')
        db.execute('DROP TABLE enrollments')
        db.execute('DROP TABLE participant_audit')
        db.execute('DROP TABLE participants')
        db.execute('PRAGMA user_version=1')
        before = db.execute('SELECT revision,body FROM settings ORDER BY revision').fetchall()
    migrated = State(path)
    assert not migrated.settings()['participant_registry']['1']['active']
    assert not migrated.settings()['participant_links']
    with migrated.connect() as db:
        after = db.execute('SELECT revision,body FROM settings ORDER BY revision').fetchall()
        assert [tuple(row) for row in after[:len(before)]] == [tuple(row) for row in before]
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2


def test_session_date_and_owned_year_must_agree(tmp_path):
    state = configured(tmp_path)
    settings = state.settings()
    settings['sessions'][0]['date'] = '2027-09-01'
    with pytest.raises(ValueError, match='session_year_mismatch'):
        state.save_settings(settings, settings['revision'])



def review(client, state, operation, **fields):
    url = '/dashboard/settings/enrollment?view=' + ('links' if operation in ('link','unlink') else 'promotion' if operation == 'promote' else 'registry')
    result = client.post(url, data={'csrf': csrf(client.get(url)), 'revision': state.settings()['revision'],
                                   'operation': operation, **fields})
    return url, result


def confirm(client, url, response):
    match = re.search(r'name="review_token" value="([^"]+)"', response.text)
    assert match, response.text
    return client.post(url, data={'csrf': csrf(response), 'action': 'confirm', 'review_token': unescape(match[1])})


def test_registry_preview_is_read_only_and_signed_confirmation_is_atomic(app):
    configure(app)
    state = app.extensions['research']['state']
    client = app.test_client()
    login(client)
    before = state.settings()
    url, response = review(client, state, 'add', ids='41, 42', year='2026/2027', grade='3')
    assert response.status_code == 200 and '41, 42' in response.text
    assert state.settings() == before
    assert confirm(client, url, response).status_code == 302
    saved = state.settings()
    assert roster(saved)['41'] == roster(saved)['42'] == '3'
    assert confirm(client, url, response).status_code == 400
    assert state.settings() == saved
    assert '41' in client.get('/dashboard/settings/enrollment?grade=3&lang=it').text


def test_registry_cannot_confirm_unsigned_changes_and_requires_auth_csrf(app):
    client = app.test_client()
    url = '/dashboard/settings/enrollment'
    assert client.get(url).status_code == 302
    login(client)
    state = app.extensions['research']['state']
    before = state.settings()
    assert client.post(url, data={'operation':'add','ids':'41','year':'2026/2027','grade':'3'}).status_code == 400
    assert client.post(url, data={'csrf':csrf(client.get(url)), 'action':'confirm','review_token':'forged'}).status_code == 400
    assert state.settings() == before


def test_reviewed_promotion_preserves_session_year_and_individual_history(app):
    configure(app)
    state = app.extensions['research']['state']
    client = app.test_client()
    login(client)
    before = state.settings()
    url, preview = review(client, state, 'promote', source_year='2026/2027', target_year='2027/2028')
    assert preview.status_code == 200 and 'no next-year enrollment' in preview.text
    assert state.settings() == before
    assert confirm(client, url, preview).status_code == 302
    assert state.settings()['sessions'] == before['sessions']
    assert '2026/2027' in client.get('/dashboard/settings/enrollment?edit=1').text


def test_explicit_legacy_link_unifies_history_export_and_preserves_original_sources(app):
    configure(app)
    state = app.extensions['research']['state']
    current, _, _ = write_run(app, uid='1')
    old, root, _ = write_run(app, collection='legacy', uid='old-8', date='2025-10-01', metadata=False)
    originals = {path: path.read_bytes() for path in root.iterdir()}
    change(state, 'update', uid='1', year='2025/2026', grade='3', active=True)
    client = app.test_client()
    login(client)
    url, preview = review(client, state, 'link', source_id='old-8', uid='1', date_from='2025-09-01',
                          date_to='2026-08-31', note='Verified synthetic register')
    assert preview.status_code == 200
    assert confirm(client, url, preview).status_code == 302
    history = client.get('/dashboard/participants/study/' + identity('1') + '?view=logs')
    assert history.status_code == 200 and 'old-8' in history.text
    _, manifest = archive(client.get('/dashboard/exports/participant?collection=study&participant=' + identity('1')))
    assert {run['run_id'] for run in manifest['runs']} == {current, old}
    linked = next(run for run in manifest['runs'] if run['run_id'] == old)
    assert linked['participant_id'] == 'old-8' and linked['study_participant_id'] == '1'
    assert linked['collection'] == 'legacy' and linked['identity_link_id']
    assert linked['grade'] == '3' and linked['school_year'] == '2025/2026'
    assert linked['grade_source'] == linked['school_year_source'] == 'enrollment'
    assert linked['identity_link_revision'] == state.settings()['revision']
    assert all(path.read_bytes() == value for path,value in originals.items())
    url, preview = review(client, state, 'unlink', link_id=linked['identity_link_id'])
    assert confirm(client, url, preview).status_code == 302
    _, after = archive(client.get('/dashboard/exports/participant?collection=study&participant=' + identity('1')))
    assert {run['run_id'] for run in after['runs']} == {current}


def test_legacy_links_require_observed_source_and_never_guess_equal_numbers(app):
    configure(app)
    write_run(app, collection='legacy', uid='1', date='2025-10-01')
    state = app.extensions['research']['state']
    client = app.test_client()
    login(client)
    before = state.settings()
    _, error = review(client, state, 'link', source_id='invented', uid='1', date_from='2025-09-01',
                      date_to='2026-08-31', note='Not observed')
    assert error.status_code == 400 and state.settings() == before
    index = app.extensions['research']['index']
    index.refresh(force=True)
    assert index.summaries(before)[0]['study_participant_id'] is None


def test_unrecorded_grade_is_not_inferred_from_present_enrollment(app):
    configure(app)
    write_run(app, uid='1', metadata=False, date='2024-10-01')
    index = app.extensions['research']['index']
    state = app.extensions['research']['state']
    index.refresh(force=True)
    before = index.summaries(state.settings())[0]
    change(state, 'promote', source_year='2026/2027', target_year='2027/2028')
    after = index.summaries(state.settings())[0]
    assert before['grade'] is after['grade'] is None
    assert before['school_year'] is after['school_year'] is None
    assert before['participant_key'] == after['participant_key']


def test_promotion_and_deactivation_do_not_change_started_attempt(student_modules, tmp_path):
    from .test_study_enrollment import schedule
    module = student_modules()
    settings = schedule(module)
    state = module.RESEARCH_STATE
    student = module.app.test_client()
    assert student.post('/start', data={'user_id':'1'}).status_code == 302
    with student.session_transaction() as active:
        sid = active['session_id']
    before = state.attempt_metadata(sid)
    year = before['school_year_at_collection']
    next_year = f'{int(year[:4])+1}/{int(year[5:])+1}'
    change(state, 'promote', source_year=year, target_year=next_year)
    # Today's session still uses its own prior year, even when planning advances.
    assert module.app.test_client().post('/start', data={'user_id':'2'}).status_code == 302
    change(state, 'update', uid='1', year=next_year, grade='5', active=False)
    assert module.app.test_client().post('/start', data={'user_id':'1'}).status_code == 400
    assert student.get('/task').status_code == 200
    assert state.attempt_metadata(sid) == before
    settings = state.settings()
    next(s for s in settings['sessions'] if s['id'] == before['study_session_at_collection'])['school_year'] = ''
    with pytest.raises(ValueError, match='session_year_has_records'):
        state.save_settings(settings, settings['revision'])


def test_stale_confirmation_keeps_review_visible_without_a_save_button(app):
    configure(app)
    state = app.extensions['research']['state']
    client = app.test_client()
    login(client)
    url, preview = review(client, state, 'add', ids='NEW-41', year='2026/2027', grade='3')
    change(state, 'update', uid='1', year='2026/2027', grade='4', active=False)
    failed = confirm(client, url, preview)
    assert failed.status_code == 400 and 'NEW-41' in failed.text
    assert 'another tab or by another researcher' in failed.text
    assert '>Confirm these changes</button>' not in failed.text
    assert 'NEW-41' not in state.settings()['participant_registry']


def test_initial_ranges_cannot_overwrite_promoted_enrollment(tmp_path):
    state = configured(tmp_path)
    change(state, 'promote', source_year='2026/2027', target_year='2027/2028')
    current = state.settings()
    current['ranges'][0]['end'] = 19
    with pytest.raises(ValueError, match='range_editor_retired'):
        state.save_settings(current, current['revision'])
    assert roster(state.settings())['20'] == '5'


def test_concurrent_enrollment_edits_commit_one_revision(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    state = configured(tmp_path)
    revision = state.settings()['revision']
    def save(uid):
        try:
            state.change_participants('add', dict(ids=[uid], year='2026/2027', grade='3'), revision)
            return 'saved'
        except ValueError as error:
            return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, ['NEW-A','NEW-B'])) == ['saved','settings_changed']
    assert len({'NEW-A','NEW-B'} & state.settings()['participant_registry'].keys()) == 1


@pytest.mark.parametrize('ids', [[], ['duplicate','duplicate'], ['bad/id'], [1], ['x'*33]])
def test_invalid_new_ids_leave_registry_and_revision_unchanged(tmp_path, ids):
    state = configured(tmp_path)
    before = state.settings()
    with pytest.raises(ValueError, match='invalid_participant_ids'):
        change(state, 'add', ids=ids, year='2026/2027', grade='3')
    assert state.settings() == before


def test_enrollment_edits_do_not_depend_on_reporting_cache(app, monkeypatch):
    configure(app)
    state = app.extensions['research']['state']
    client = app.test_client()
    login(client)
    def unavailable(*args, **kwargs):
        raise OSError('synthetic unavailable reporting cache')
    monkeypatch.setattr(app.extensions['research']['index'], 'refresh', unavailable)
    url, preview = review(client, state, 'add', ids='NEW-41', year='2026/2027', grade='3')
    assert preview.status_code == 200
    assert confirm(client, url, preview).status_code == 302
    assert roster(state.settings())['NEW-41'] == '3'
    assert client.get('/dashboard/settings/enrollment?view=links').status_code == 503
