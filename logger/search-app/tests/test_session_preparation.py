"""Task-based researcher preparation uses the same enrollment/admission services."""
from copy import deepcopy
from urllib.parse import parse_qs, urlsplit

import pytest

from .test_research_dashboard import app, csrf, login, configure
from .test_study_enrollment import student_modules
from .test_permanent_participants import confirm, change
from .test_session_question_editor import EditorFields
from research_dashboard.state import roster

PREP = '/dashboard/prepare?grade=4&year=2026/2027&session=grade-4-session-1'
IDS = '/dashboard/settings/enrollment?grade=4&year=2026/2027&prepare_session=grade-4-session-1'
QUESTIONS = '/dashboard/settings/questions/grade-4-session-1?prepare_session=grade-4-session-1'


def details(client, state, url=PREP, **values):
    return client.post(url, data={'csrf':csrf(client.get(url)), 'revision':state.settings()['revision'],
                                 'action':'save_details','name':'Research visit','date':'2026-10-20', **values})


def test_login_and_bare_dashboard_start_with_session_preparation_without_writing(app):
    client = app.test_client()
    result = login(client)
    assert '/prepare' in result.location
    state = app.extensions['research']['state']
    before = state.settings()
    for url in ('/dashboard', '/dashboard?lang=it', '/dashboard/prepare'):
        page = client.get(url)
        assert page.status_code == 200
        assert 'name="action" value="save_details"' in page.text
        assert 'id="prepare-details"' in page.text
        assert 'id="prepare-participants"' in page.text
    assert state.settings() == before
    data = client.get('/dashboard?collection=study&grade=4')
    assert 'id="participants-heading"' in data.text


def test_first_setup_saves_own_session_year_and_initial_enrollment_together(app):
    client = app.test_client()
    login(client)
    state = app.extensions['research']['state']
    before = state.settings()
    keys = before['participant_registry']
    result = details(client,state)
    assert result.status_code == 302 and '#prepare-participants' in result.location
    saved = state.settings()
    assert saved['revision'] == before['revision']+1
    assert saved['current_school_year'] == saved['sessions'][0]['school_year'] == '2026/2027'
    assert saved['participant_registry'] == keys
    assert roster(saved)['1'] == '4'
    assert all(item['school_year'] == '' for item in saved['sessions'][1:])


def test_readiness_drafts_and_ids_stay_in_the_selected_session(app):
    configure(app)
    state = app.extensions['research']['state']
    settings = state.settings()
    settings['sessions'][0]['question_set'] = {'approved':False, 'questions':[{'id':'q1','topic':'Sky','question':'Why is the sky blue?'}]}
    state.save_settings(settings,settings['revision'])
    client = app.test_client()
    login(client)
    page = client.get(PREP)
    assert 'Why is the sky blue?' in page.text and 'Continue editing draft' in page.text
    assert 'prepare_session=grade-4-session-1' in page.text
    assert '0 / 20' in page.text
    editor = client.get(QUESTIONS)
    assert '1 · Session details' in editor.text and '2 · Participant IDs' in editor.text
    assert 'session=grade-4-session-1' in editor.text


def test_new_id_review_and_confirmation_returns_to_the_same_session(app):
    configure(app)
    state = app.extensions['research']['state']
    client = app.test_client()
    login(client)
    before = state.settings()
    preview = client.post(IDS, data={'csrf':csrf(client.get(PREP)), 'revision':before['revision'],
                                   'operation':'add','ids':'41, 42','year':'2026/2027','grade':'4'})
    assert preview.status_code == 200 and state.settings() == before
    result = confirm(client,IDS,preview)
    assert result.status_code == 302
    query = parse_qs(urlsplit(result.location).query)
    assert query['session'] == ['grade-4-session-1'] and query['grade'] == ['4']
    assert query['year'] == ['2026/2027']
    assert roster(state.settings())['41'] == '4'
    assert '22' in client.get(result.location).text


def test_enrolling_existing_ids_preserves_keys_and_previous_year(app):
    configure(app)
    state = app.extensions['research']['state']
    client = app.test_client()
    login(client)
    settings = state.settings()
    original_keys = deepcopy(settings['participant_registry'])
    original_enrollments = deepcopy(settings['enrollments']['2026/2027'])
    next_session = state.add_study_session('5','2027-10-20',settings['revision'], school_year='2027/2028')
    url = '/dashboard/settings/enrollment?year=2027/2028&grade=5&prepare_session='+next_session['id']
    preview = client.post(url,data={'csrf':csrf(client.get(url)), 'revision':state.settings()['revision'],
                                  'operation':'enroll','ids':'1, 2','year':'2027/2028','grade':'5'})
    assert preview.status_code == 200
    assert confirm(client,url,preview).status_code == 302
    saved = state.settings()
    assert saved['participant_registry'] == original_keys
    assert saved['enrollments']['2026/2027'] == original_enrollments
    assert roster(saved,'2027/2028') == {'1':'5','2':'5'}


def test_unknown_or_inactive_existing_id_rolls_back_whole_enrollment(app):
    configure(app)
    state = app.extensions['research']['state']
    before = state.settings()
    with pytest.raises(ValueError,match='participant_not_registered'):
        change(state,'enroll',ids=['1','unknown'],year='2027/2028',grade='5')
    assert state.settings() == before
    change(state,'update',uid='2',year='2026/2027',grade='4',active=False)
    before = state.settings()
    with pytest.raises(ValueError,match='participant_inactive'):
        change(state,'enroll',ids=['1','2'],year='2027/2028',grade='5')
    assert state.settings() == before


def test_workflow_review_cannot_be_confirmed_for_another_session(app):
    configure(app)
    client = app.test_client()
    login(client)
    state = app.extensions['research']['state']
    before = state.settings()
    preview = client.post(IDS,data={'csrf':csrf(client.get(IDS)), 'revision':before['revision'],
                                  'operation':'add','ids':'41','year':'2026/2027','grade':'4'})
    other = IDS.replace('grade-4-session-1','grade-4-session-2')
    assert confirm(client,other,preview).status_code == 400
    assert state.settings() == before


def test_save_and_return_keeps_draft_and_preparation_context(app):
    configure(app)
    client = app.test_client()
    login(client)
    state = app.extensions['research']['state']
    fields = EditorFields(client.get(QUESTIONS)).fields
    fields.update(action='save_draft_return',topic_0='Sky',question_0='Why is the sky blue?')
    result = client.post(QUESTIONS,data=fields)
    assert result.status_code == 302 and '/prepare?' in result.location
    assert parse_qs(urlsplit(result.location).query)['session'] == ['grade-4-session-1']
    page = client.get(result.location)
    assert 'Why is the sky blue?' in page.text and 'Continue editing draft' in page.text
    saved = state.settings()['sessions'][0]
    assert saved['question_draft']['approved'] is False and 'question_set' not in saved


def test_preparation_requires_csrf_and_preserves_stale_input(app):
    client = app.test_client()
    login(client)
    state = app.extensions['research']['state']
    before = state.settings()
    assert client.post(PREP,data={'action':'save_details','revision':before['revision']}).status_code == 400
    fields = {'csrf':csrf(client.get(PREP)), 'revision':before['revision'],
              'action':'save_details','date':'2026-10-20','name':'Keep my draft'}
    changed = state.settings()
    changed['current_school_year'] = '2026/2027'
    state.save_settings(changed,changed['revision'])
    saved = state.settings()
    result = client.post(PREP,data=fields)
    assert result.status_code == 400 and 'Keep my draft' in result.text and 'another tab or by another researcher' in result.text
    assert state.settings() == saved


def test_preparation_works_when_reporting_cache_is_unavailable(app,monkeypatch):
    client = app.test_client()
    login(client)
    def unavailable(*args,**kwargs):
        raise OSError('synthetic reporting failure')
    monkeypatch.setattr(app.extensions['research']['index'],'refresh',unavailable)
    assert client.get('/dashboard').status_code == 200
    assert client.get('/dashboard/prepare').status_code == 200
    assert client.get('/dashboard?collection=study&grade=4').status_code == 503


def test_context_picker_changes_class_without_retaining_a_foreign_session(app):
    configure(app)
    client=app.test_client()
    login(client)
    before=app.extensions['research']['state'].settings()
    url='/dashboard/prepare?grade=5&year=2026/2027&session=grade-4-session-1'
    assert client.get(url).status_code == 404
    changed=client.get(url+'&context_selection=1')
    assert changed.status_code == 200
    assert 'prepare_session=grade-5-session-' in changed.text
    assert app.extensions['research']['state'].settings() == before




def test_prepare_approve_and_admit_use_the_same_year_ids_and_questions(student_modules,tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from werkzeug.security import generate_password_hash
    from .test_research_dashboard import PASSWORD
    from .enrollment_helpers import school_year
    module=student_modules()
    module.app.config.update(RESEARCH_PASSWORD_HASH=generate_password_hash(PASSWORD,method='pbkdf2:sha256:1000'),
                             RESEARCH_PASSWORD_HASH_FILE='')
    researcher=module.app.test_client()
    student=module.app.test_client()
    login(researcher)
    today=datetime.now(ZoneInfo('Europe/Zurich')).date()
    year=school_year(today)
    state=module.RESEARCH_STATE
    prep='/dashboard/prepare?grade=4&year='+year+'&session=grade-4-session-1'
    assert details(researcher,state,url=prep,date=today.isoformat()).status_code == 302
    editor='/dashboard/settings/questions/grade-4-session-1?prepare_session=grade-4-session-1'
    fields=EditorFields(researcher.get(editor)).fields
    fields.update(action='approve_questions')
    for number in range(3):
        fields[f'topic_{number}']=f'Current topic {number}'
        fields[f'question_{number}']=f'Current question {number}?'
    approved=researcher.post(editor,data=fields)
    assert approved.status_code == 302 and '/prepare?' in approved.location
    assert '20 / 20' in researcher.get(approved.location).text
    assert student.post('/start',data={'user_id':'1'}).status_code == 302
    with student.session_transaction() as active:
        metadata=state.attempt_metadata(active['session_id'])
    assert metadata['school_year_at_collection'] == year
    assert metadata['participant_key'] == state.settings()['participant_registry']['1']['key']
    assert {item['question'] for item in metadata['tasks']} == {f'Current question {i}?' for i in range(3)}


def test_every_session_automatically_uses_the_class_ids(app):
    configure(app)
    state=app.extensions['research']['state']
    change(state,'add',ids=['NEW-41'],year='2026/2027',grade='4')
    client=app.test_client()
    login(client)
    from research_dashboard.study_config import session_readiness
    settings=state.settings()
    sessions=[item for item in settings['sessions'] if item['grade']=='4']
    for study_session in sessions:
        assert {item['id'] for item in session_readiness(settings,study_session)['participants']} == set(roster(settings)) - {str(n) for n in range(21,41)}
        page=client.get('/dashboard/prepare?grade=4&year=2026/2027&session='+study_session['id'])
        assert page.status_code == 200 and 'NEW-41' in page.text
    assert state.settings() == settings
