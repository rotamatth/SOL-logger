"""Session preparation UI composed from the existing study services."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import abort, redirect, request

from .participants import GRADES, school_year_for, valid_school_year
from .state import SETTING_FIELDS, make_study_session, normalize_session_name
from .study_config import session_readiness


def preparation_session(settings, session_id):
    if not session_id:
        return None
    selected = next((item for item in settings['sessions']
                     if item['id'] == session_id and not item.get('removed')), None)
    if selected is None:
        abort(404)
    return selected


def register_preparation_routes(bp, state, page, u):
    @bp.route('/prepare', methods=['GET', 'POST'])
    def prepare_page():
        settings = state.settings()
        grade = request.args.get('grade', '4')
        if grade not in GRADES:
            abort(404)
        today = datetime.now(ZoneInfo('Europe/Zurich')).date().isoformat()
        year = request.args.get('year', settings['current_school_year'] or school_year_for(today))
        if not valid_school_year(year):
            abort(404)
        selected = preparation_session(settings, request.args.get('session'))
        if selected and (selected['grade'] != grade or selected.get('school_year') not in ('', year)):
            if request.method == 'GET' and request.args.get('context_selection') == '1':
                selected = None  # Switching class/year starts with that context's own sessions.
            else:
                abort(404)
        sessions = [item for item in settings['sessions'] if item['grade'] == grade
                    and not item.get('removed') and item.get('school_year') in ('', year)]
        sessions.sort(key=lambda item: (item['date'] or '9999', item['number']))
        creating = request.args.get('new') == '1' and selected is None
        if not selected and sessions and not creating:
            upcoming = next((item for item in sessions if item['date'] and item['date'] >= today), None)
            undated = next((item for item in sessions if not item['date']), None)
            selected = upcoming or undated or sessions[-1]
        error = None
        if request.method == 'POST':
            try:
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
                           'session_has_records', 'overlapping_dates', 'session_limit'}
                error = str(exc) if str(exc) in allowed else 'invalid_settings'
        readiness = session_readiness(settings, selected) if selected else None
        return page('prepare', settings=settings, study_context={'grade': grade, 'school_year': year},
                    research_area='prepare', selected=selected, sessions=sessions, creating=creating,
                    readiness=readiness, error=error, today=today), 400 if error else 200
    return prepare_page
