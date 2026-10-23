"""Session preparation UI composed from the existing study services."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import abort, redirect, request

from .participants import GRADES, participant_sort_key, roster, school_year_for, valid_school_year
from .question_versions import published_questions, working_questions
from .settings_views import session_review_url
from .state import SETTING_FIELDS, make_study_session, normalize_session_name
from .study_config import assignment_for, question_set_problem, session_readiness
from .year_controls import school_year_bounds, school_year_choices


def preparation_session(settings, session_id):
    if not session_id:
        return None
    selected = next((item for item in settings['sessions']
                     if item['id'] == session_id and not item.get('removed')), None)
    if selected is None:
        abort(404)
    return selected


def preparation_status(study_session, readiness, today):
    """Describe access timing separately from question/configuration readiness."""
    if not study_session or not study_session.get('date') or not valid_school_year(study_session.get('school_year')):
        code = 'setup_incomplete'
    elif study_session['date'] < today:
        code = 'date_passed'
    elif not (readiness and (readiness.get('complete') or readiness.get('ready', 0))):
        # Nobody could start on the date yet: report missing setup, not the schedule.
        code = 'setup_incomplete'
    elif study_session['date'] > today:
        code = 'scheduled'
    elif readiness.get('complete'):
        code = 'available_today'
    else:
        code = 'partly_available_today'
    complete = bool(readiness and readiness.get('complete'))
    tone = ('success' if code == 'available_today'
            else 'warning' if code in ('setup_incomplete', 'partly_available_today')
            or (code == 'scheduled' and not complete) else 'neutral')
    return {'code': code, 'title': 'session_state_' + code,
            'hint': 'session_state_' + code + '_hint', 'tone': tone}


def register_preparation_routes(dash):
    bp, state, page, u = dash.bp, dash.state, dash.page, dash.u

    @bp.route('/prepare', methods=['GET', 'POST'])
    def prepare_page():
        settings = state.settings()
        grade = request.args.get('select_grade', request.args.get('grade', '4'))
        if grade not in GRADES:
            abort(404)
        today = datetime.now(ZoneInfo('Europe/Zurich')).date().isoformat()
        year = request.args.get('year', settings['current_school_year'] or school_year_for(today))
        if not valid_school_year(year):
            abort(404)
        # A session removed or moved to another class/year while this form was open:
        # reject the save but keep the typed details instead of answering 404.
        rejected = None
        if request.method == 'POST' and request.args.get('session'):
            known = next((item for item in settings['sessions'] if item['id'] == request.args['session']), None)
            if known and (known.get('removed') or known['grade'] != grade or known.get('school_year') not in ('', year)):
                rejected = known
        selected = None if rejected else preparation_session(settings, request.args.get('session'))
        if selected and (selected['grade'] != grade or selected.get('school_year') not in ('', year)):
            if request.method == 'GET' and request.args.get('context_selection') == '1':
                selected = None  # Switching class/year starts with that context's own sessions.
            else:
                abort(404)
        sessions = [item for item in settings['sessions'] if item['grade'] == grade
                    and not item.get('removed') and item.get('school_year') in ('', year)]
        sessions.sort(key=lambda item: (item['date'] or '9999', item['number']))
        creating = request.args.get('new') == '1' and selected is None and rejected is None
        if not selected and sessions and not creating and not rejected:
            upcoming = next((item for item in sessions if item['date'] and item['date'] >= today), None)
            undated = next((item for item in sessions if not item['date']), None)
            selected = upcoming or undated or sessions[-1]
        error = None
        if request.method == 'POST':
            try:
                if rejected:
                    raise ValueError('prepare_session_changed')
                revision = int(request.form['revision'])
                if revision != settings['revision']:
                    raise ValueError('settings_changed')
                if request.form.get('action') != 'save_details':
                    raise ValueError('invalid_settings')
                if not settings['current_school_year']:
                    # Initial enrollment and session setup must share one revision.
                    updated = deepcopy({key: settings[key] for key in SETTING_FIELDS})
                    updated['current_school_year'] = year
                else:
                    updated = deepcopy({key: settings[key] for key in SETTING_FIELDS})
                name, study_date = request.form.get('name', ''), request.form.get('date', '')
                if not study_date:
                    raise ValueError('invalid_date')
                if selected and not creating:
                    target = next(item for item in updated['sessions'] if item['id'] == selected['id'])
                    target.update(name=normalize_session_name(name), date=study_date, school_year=year)
                    state.save_settings(updated, revision)
                    session_id = target['id']
                else:
                    target = make_study_session(updated, grade, study_date, name, year)
                    session_id = target['id']
                    updated['sessions'].append(target)
                    state.save_settings(updated, revision)
                return redirect(u('prepare_page', grade=grade, year=year, session=session_id,
                                  saved='1', _anchor='prepare-participants'))
            except (ValueError, KeyError) as exc:
                allowed = {'settings_changed', 'invalid_date', 'invalid_session_name', 'session_year_mismatch',
                           'session_year_has_records', 'overlapping_dates', 'session_limit', 'prepare_session_changed'}
                error = str(exc) if str(exc) in allowed else 'invalid_settings'
        readiness = session_readiness(settings, selected) if selected else None
        working = working_questions(selected) if selected else None
        published = published_questions(selected) if selected else None
        pending_draft = bool(selected and ('question_draft' in selected
                             or published and question_set_problem(published) is not None))
        return page('prepare', settings=settings, study_context={'grade': grade, 'school_year': year,
                    'id': selected['id'] if selected else None},
                    research_area='prepare', selected=selected, sessions=sessions, creating=creating,
                    rejected=rejected, rejected_review_url=session_review_url(dash, settings, rejected) if rejected else None,
                    school_years=school_year_choices(settings, year), date_bounds=school_year_bounds(year),
                    readiness=readiness, error=error, today=today,
                    session_status=preparation_status(selected, readiness, today),
                    working_questions=working, published_questions=published,
                    has_working_draft=pending_draft,
                    pending_individual_drafts=len(selected.get('participant_question_drafts', {})) if selected else 0), 400 if error else 200

    @bp.get('/prepare/<session_id>/preview')
    def student_preview(session_id):
        """Render researcher-only question content without entering student collection."""
        settings = state.settings()
        study_session = preparation_session(settings, session_id)
        participant = request.args.get('participant', '')
        mode = request.args.get('mode', 'working')
        try:
            number = int(request.args.get('question', '1'))
        except ValueError:
            abort(404)
        if mode not in ('working', 'published') or number not in (1, 2, 3):
            abort(404)
        ids = sorted((uid for uid, grade in roster(settings, study_session.get('school_year')).items()
                      if grade == study_session['grade']), key=participant_sort_key)
        if participant and participant not in ids:
            abort(404)
        assignment = assignment_for(settings, participant, session_id) if participant else None
        source = assignment['source'] if assignment else 'shared'
        if mode == 'published':
            question_set = assignment['question_set'] if assignment else published_questions(study_session)
            if question_set and not question_set.get('approved'):
                question_set = None
        else:
            individual = (participant in study_session.get('participant_question_drafts', {})
                          or participant in study_session.get('participant_questions', {}))
            question_set = working_questions(study_session, participant if individual else '')
            source = 'participant' if individual else 'shared'
        questions = question_set.get('questions', []) if question_set else []
        question = questions[number - 1] if len(questions) >= number else None
        return page('student_preview', settings=settings, study_session=study_session,
                    study_context=study_session, research_area='prepare',
                    participant=participant, participant_ids=ids, mode=mode, number=number,
                    preview_question=question, preview_set=question_set, question_source=source)
    dash.prepare_view = prepare_page
