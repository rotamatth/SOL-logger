"""Researcher preview never becomes a student attempt or changes study state."""
from copy import deepcopy
from pathlib import Path

import pytest

from .test_research_dashboard import app, configure, login
from .test_study_enrollment import question_set
from research_dashboard.preparation_views import preparation_status
from research_dashboard.question_versions import save_question_draft
from research_dashboard.study_config import session_readiness


SESSION = 'grade-4-session-1'
PREVIEW = '/dashboard/prepare/' + SESSION + '/preview'
PREP = '/dashboard/prepare?grade=4&year=2026/2027&session=' + SESSION


@pytest.mark.parametrize('study_date,complete,expected', [
    ('', False, 'setup_incomplete'),
    ('2026-10-19', True, 'date_passed'),
    ('2026-10-21', True, 'scheduled'),
    # A future date with nothing approved is missing setup, not merely scheduled.
    ('2026-10-21', False, 'setup_incomplete'),
    ('2026-10-20', True, 'available_today'),
    ('2026-10-20', False, 'setup_incomplete'),
])
def test_access_state_separates_date_from_configuration(study_date, complete, expected):
    session = {'date': study_date, 'school_year': '2026/2027'}
    assert preparation_status(session, {'complete': complete}, '2026-10-20')['code'] == expected
    session['school_year'] = ''
    assert preparation_status(session, {'complete': complete}, '2026-10-20')['code'] == 'setup_incomplete'


def test_preview_requires_research_access_and_never_enters_a_student_route(app):
    configure(app)
    client = app.test_client()
    assert client.get(PREVIEW).status_code == 302
    login(client)
    page = client.get(PREVIEW)
    assert page.status_code == 200
    assert '/start' not in page.text
    assert 'logger.js' not in page.text and 'log_session' not in page.text
    assert 'name="user_id"' not in page.text


def test_future_partial_readiness_is_scheduled_with_a_warning():
    session = {'date': '2026-10-25', 'school_year': '2026/2027'}
    status = preparation_status(session, {'complete': False, 'ready': 5, 'count': 20}, '2026-10-20')
    assert status['code'] == 'scheduled' and status['tone'] == 'warning'
    status = preparation_status(session, {'complete': True, 'ready': 20, 'count': 20}, '2026-10-20')
    assert status['code'] == 'scheduled' and status['tone'] == 'neutral'


def test_partial_readiness_does_not_claim_every_id_is_blocked():
    session = {'date': '2026-10-20', 'school_year': '2026/2027'}
    status = preparation_status(session, {'complete': False, 'ready': 18, 'count': 20}, '2026-10-20')
    assert status['code'] == 'partly_available_today'


def test_future_preview_displays_working_and_published_versions_without_writes(app):
    configure(app)
    state = app.extensions['research']['state']
    settings = state.settings()
    session = settings['sessions'][0]
    session['date'] = '2027-06-15'
    session['question_set'] = question_set()
    approved = deepcopy(session['question_set'])
    draft = deepcopy(approved)
    draft['questions'][0]['question'] = 'Working question for next summer?'
    save_question_draft(session, draft)
    state.save_settings(settings, settings['revision'])
    before = state.settings()
    before_files = {str(path.relative_to(Path(app.config['RESEARCH_LOG_DIR'])))
                    for path in Path(app.config['RESEARCH_LOG_DIR']).rglob('*')}
    with state.connect() as db:
        before_attempts = db.execute('SELECT COUNT(*) FROM study_attempts').fetchone()[0]
    client = app.test_client()
    login(client)
    working = client.get(PREVIEW)
    published = client.get(PREVIEW + '?mode=published')
    assert working.status_code == published.status_code == 200
    assert 'Working question for next summer?' in working.text
    assert 'Working question for next summer?' not in published.text
    assert approved['questions'][0]['question'] in published.text
    assert '2027-06-15' in working.text
    assert state.settings() == before
    with state.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM study_attempts').fetchone()[0] == before_attempts
    assert {str(path.relative_to(Path(app.config['RESEARCH_LOG_DIR'])))
            for path in Path(app.config['RESEARCH_LOG_DIR']).rglob('*')} == before_files


def test_preview_resolves_individual_versions_and_exact_class_ids(app):
    configure(app)
    state = app.extensions['research']['state']
    settings = state.settings()
    session = settings['sessions'][0]
    session['question_set'] = question_set()
    individual = question_set()
    individual['questions'][0]['question'] = 'Approved individual text?'
    session['participant_questions'] = {'1': individual}
    changed = deepcopy(individual)
    changed['questions'][0]['question'] = 'Unpublished individual text?'
    save_question_draft(session, changed, '1')
    state.save_settings(settings, settings['revision'])
    before = state.settings()
    client = app.test_client()
    login(client)
    working = client.get(PREVIEW + '?participant=1')
    published = client.get(PREVIEW + '?participant=1&mode=published')
    class_default = client.get(PREVIEW + '?participant=2&mode=published')
    assert 'Unpublished individual text?' in working.text
    assert 'Approved individual text?' in published.text
    assert session['question_set']['questions'][0]['question'] in class_default.text
    assert 'Approved individual text?' not in class_default.text
    for query in ('?participant=001', '?participant=21', '?participant=unknown', '?mode=unknown',
                  '?question=0', '?question=4', '?question=text'):
        assert client.get(PREVIEW + query).status_code == 404
    assert client.get('/dashboard/prepare/unknown/preview').status_code == 404
    assert state.settings() == before


def test_preparation_shows_the_working_draft_without_hiding_live_approval(app):
    configure(app)
    state = app.extensions['research']['state']
    settings = state.settings()
    session = settings['sessions'][0]
    session['question_set'] = question_set()
    changed = deepcopy(session['question_set'])
    changed['questions'][0]['question'] = 'Saved work still awaiting approval?'
    save_question_draft(session, changed)
    state.save_settings(settings, settings['revision'])
    before = state.settings()
    client = app.test_client()
    login(client)
    page = client.get(PREP)
    assert page.status_code == 200
    assert 'Saved work still awaiting approval?' in page.text
    assert '/prepare/' + SESSION + '/preview' in page.text
    assert 'Continue editing draft' in page.text
    assert '20 / 20' in page.text
    assert session_readiness(before, before['sessions'][0])['complete'] is True
    assert state.settings() == before


def test_removed_session_cannot_be_previewed(app):
    configure(app)
    state = app.extensions['research']['state']
    settings = state.settings()
    settings['sessions'][0]['removed'] = True
    state.save_settings(settings, settings['revision'])
    client = app.test_client()
    login(client)
    assert client.get(PREVIEW).status_code == 404
