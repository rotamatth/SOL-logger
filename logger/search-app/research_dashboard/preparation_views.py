"""One session's preparation page, and the status words shared with the session list."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import abort, redirect, request

from .participants import (GRADES, participant_sort_key, roster, school_year_for, valid_school_year,
                           year_contains)
from .question_versions import published_questions, working_questions
from .state import SETTING_FIELDS, make_study_session, normalize_session_name
from .study_config import assignment_for, question_set_problem, session_readiness

DETAIL_ERRORS = frozenset(("settings_changed", "invalid_date", "invalid_session_name", "session_year_mismatch",
                           "session_year_has_records", "overlapping_dates", "session_limit",
                           "prepare_session_changed", "invalid_sessions"))


def preparation_session(settings, session_id):
    if not session_id:
        return None
    selected = next((item for item in settings['sessions']
                     if item['id'] == session_id and not item.get('removed')), None)
    if selected is None:
        abort(404)
    return selected


def import_choices(settings, year, grade):
    """Active children not in this class this year, grouped by their class this year.

    Children not enrolled this year come last, with their most recent class and year.
    """
    registry, enrollments = settings.get('participant_registry') or {}, settings.get('enrollments', {})
    groups = {}
    for uid in sorted((uid for uid, person in registry.items() if person['active']), key=participant_sort_key):
        current = enrollments.get(year, {}).get(uid)
        if current and current['grade'] == grade:
            continue
        last = None if current else next(((other, enrollments[other][uid]['grade'])
                                          for other in sorted(enrollments, reverse=True)
                                          if uid in enrollments[other]), None)
        groups.setdefault(current['grade'] if current else None, []).append({'id': uid, 'last': last})
    return [{'grade': key, 'people': groups[key]} for key in (*GRADES, None) if key in groups]


def preparation_status(study_session, readiness, today):
    """Describe access timing separately from question/configuration readiness."""
    complete = bool(readiness and readiness.get('complete'))
    if not study_session or not study_session.get('date') or not valid_school_year(study_session.get('school_year')):
        code = 'setup_incomplete'
    elif study_session['date'] < today:
        code = 'date_passed'
    elif study_session['date'] > today:
        # Published means confirmed and ready for its date: every child can start.
        code = 'scheduled' if complete else 'setup_incomplete'
    elif complete:
        code = 'available_today'
    elif readiness and readiness.get('ready', 0):
        code = 'partly_available_today'
    else:
        code = 'setup_incomplete'
    tone = ('success' if code in ('available_today', 'scheduled')
            else 'warning' if code in ('setup_incomplete', 'partly_available_today') else 'neutral')
    return {'code': code, 'title': 'session_state_' + code,
            'hint': 'session_state_' + code + '_hint', 'tone': tone}


def session_needs(study_session, readiness):
    """What still stops children from starting: any of 'date', 'ids' and 'questions'."""
    needs = []
    study_date, year = study_session.get('date'), study_session.get('school_year')
    if not study_date or not valid_school_year(year) or not year_contains(year, study_date):
        needs.append('date')
    if not readiness['count']:
        needs.append('ids')
    shared = study_session.get('question_set')
    individual = study_session.get('participant_questions', {})
    question_sets = [individual.get(person['id'], shared) for person in readiness['participants']] or [shared]
    if any(question_set_problem(item) for item in question_sets):
        needs.append('questions')
    return needs


def session_group(study_session, readiness, today):
    """Where a session belongs in the session list: 'past', 'today', 'published' or 'draft'."""
    study_date = study_session.get('date')
    if not study_date or not valid_school_year(study_session.get('school_year')):
        return 'draft'
    if study_date < today:
        return 'past'
    if study_date == today:
        return 'today' if readiness['ready'] else 'draft'
    return 'published' if readiness['complete'] else 'draft'


def is_placeholder(study_session):
    """A numbered slot nobody has filled in yet: Create uses it instead of skipping its number."""
    return not any(study_session.get(key) for key in (
        'date', 'name', 'removed', 'question_set', 'question_draft',
        'participant_questions', 'participant_question_drafts'))


def zurich_today():
    return datetime.now(ZoneInfo('Europe/Zurich')).date().isoformat()


def session_review_url(dash, study_session, fallback_year=None):
    """Where to see a session's saved state after someone else changed it: its page or the restore panel."""
    year = study_session.get('school_year') or fallback_year
    if study_session.get('removed'):
        return dash.u('sessions_page', grade=study_session['grade'], year=year, removed='1',
                      _anchor='removed-sessions')
    return dash.u('prepare_page', grade=study_session['grade'], year=year, session=study_session['id'])


def save_session_details(state, settings, grade, selected, name, study_date, revision):
    """Save a session's name and date, creating it when none is selected, and return it."""
    # The school year follows from the date (September–August); it is never typed.
    session_year = school_year_for(study_date)
    if not session_year:
        raise ValueError('invalid_date')
    updated = deepcopy({key: settings[key] for key in SETTING_FIELDS})
    if not settings['current_school_year']:
        # Initial enrollment and session setup must share one revision.
        updated['current_school_year'] = session_year
    target = (next(item for item in updated['sessions'] if item['id'] == selected['id']) if selected else
              next((item for item in sorted(updated['sessions'], key=lambda item: item['number'])
                    if item['grade'] == grade and is_placeholder(item)), None))
    if target:
        target.update(name=normalize_session_name(name), date=study_date, school_year=session_year)
    else:
        target = make_study_session(updated, grade, study_date, name, session_year)
        updated['sessions'].append(target)
    state.save_settings(updated, revision)
    return target


def register_preparation_routes(dash):
    bp, state, page, u = dash.bp, dash.state, dash.page, dash.u

    @bp.route('/prepare', methods=['GET', 'POST'])
    def prepare_page():
        settings = state.settings()
        grade = request.args.get('grade', '4')
        if grade not in GRADES:
            abort(404)
        today = zurich_today()
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
            abort(404)
        if not selected and not rejected:
            # The session list is where a session is chosen or created.
            if request.args.get('new') == '1':
                return redirect(u('create_session_page', grade=grade))
            return redirect(u('sessions_page', grade=request.args.get('grade'), year=request.args.get('year')))
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
                target = save_session_details(state, settings, grade, selected, request.form.get('name', ''),
                                              request.form.get('date', ''), revision)
                return redirect(u('prepare_page', grade=grade, year=target['school_year'], session=target['id'],
                                  saved='1', _anchor='prepare-participants'))
            except (ValueError, KeyError) as exc:
                error = str(exc) if str(exc) in DETAIL_ERRORS else 'invalid_settings'
        readiness = session_readiness(settings, selected) if selected else None
        working = working_questions(selected) if selected else None
        published = published_questions(selected) if selected else None
        pending_draft = bool(selected and ('question_draft' in selected
                             or published and question_set_problem(published) is not None))
        return page('prepare', settings=settings, study_context={'grade': grade, 'school_year': year,
                    'id': selected['id'] if selected else None},
                    research_area='sessions', selected=selected,
                    rejected=rejected, rejected_review_url=session_review_url(dash, rejected) if rejected else None,
                    readiness=readiness, error=error, today=today,
                    session_status=preparation_status(selected, readiness, today),
                    session_needs=session_needs(selected, readiness) if selected else [],
                    working_questions=working, published_questions=published,
                    has_working_draft=pending_draft,
                    pending_individual_drafts=len(selected.get('participant_question_drafts', {})) if selected else 0,
                    import_groups=import_choices(settings, year, grade) if selected else [],
                    known_ids=sorted(settings.get('participant_registry') or {}, key=participant_sort_key)), 400 if error else 200

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
                    study_context=study_session, research_area='sessions',
                    participant=participant, participant_ids=ids, mode=mode, number=number,
                    preview_question=question, preview_set=question_set, question_source=source)
