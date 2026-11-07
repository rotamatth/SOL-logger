import html
import json

import requests
import math
import os
import csv
import re
import socket
import ipaddress
import search_backend
import uuid
import random
from copy import deepcopy
import sqlite3
import tempfile

from flask import Flask, abort, render_template, url_for, request, session, redirect, jsonify
from markupsafe import Markup, escape
from flask_session import Session
from forms import SearchForm
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlparse
from research_dashboard.participants import participant_sort_key
from research_dashboard.permanent_test import (TEST_EXPERIMENTS, TEST_RUNS_FOLDER, assignment_for_test_id,
                                               is_test_participant)
from research_dashboard import init_dashboard
from research_dashboard.collection import record_run, publish_metadata
from research_dashboard.log_store import LogStore, UploadConflict
from research_dashboard.runtime import configure_runtime
from research_dashboard.study_config import scheduled_assignment
from study_progress import init_progress, SubmissionConflict
from student_progress import SessionUnavailable, StudentProgress
from student_recap import StudentRecap

app = Flask(__name__)

# -------------------------------------------------
# 1. Core app + session configuration FIRST
# -------------------------------------------------
configure_runtime(app)

app.config.update(
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "0") == "1",
    SESSION_COOKIE_SAMESITE="Lax",
    # A late read-only request must not recreate a browser session after recap exit.
    SESSION_REFRESH_EACH_REQUEST=False,
)

app.config["SESSION_TYPE"] = "filesystem"   # or "redis"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True

# Initialize server-side sessions
Session(app)

# All student pages and their scripts are same-origin; no cross-origin access (CORS)
# is granted. Uploads are bounded; the dashboard sets its own tighter limits.
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

SEARCH_BACKEND = os.getenv("SEARCH_BACKEND", "vertex").lower()

LOG_DIR = os.getenv("SOL_LOG_DIR", "logs_v2")
LOG_TIME_ZONE = ZoneInfo("Europe/Zurich")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_REGISTRY_PATH = os.path.join(LOG_DIR, 'log_registry.jsonl')
LOG_STORE = LogStore(LOG_DIR)
TEST_LOG_STORE = LogStore(os.path.join(LOG_DIR, TEST_RUNS_FOLDER))

SERP_QUERY_FIELD_EVENTS = {
    'querySubmitted',
    'searchResultGenerated',
    'clickedResult',
    'cursorEnteredSnippet',
    'cursorLeftSnippet',
    'pageNavigationClicked',
    'resultExposureStarted',
    'resultExposureEnded',
    'searchNoResults',
    'generatedDidYouMean',
    'hoverOverDidYouMean',
    'clickedDidYouMeanSuggestion',
}


def _sanitize_for_filename(value):
    cleaned = re.sub(r'[^A-Za-z0-9._-]', '_', str(value))
    return cleaned[:64] or "anon"

def sanitize_query(query):
    if SEARCH_BACKEND == "vertex":
        cleaned_query =  query
    else:
        # if using pyterrier for retrieval, then query must be cleaned before any other processing
        cleaned_query =  re.sub(r'[^\w\s]', '', query)
    return cleaned_query

def load_user_topics(filepath='data/user_topics.csv'):
    topics = {}
    with open(filepath, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',')
        for row in reader:
            user = row['uid']
            topics[user] = {
                '1_short': row['topic1_keyword'],
                '1_full': row['topic1_question'],
                '1_gif': row.get('topic1_gif', '').strip(),
                '2_short': row['topic2_keyword'],
                '2_full': row['topic2_question'],
                '2_gif': row.get('topic2_gif', '').strip(),
                '3_short': row['topic3_keyword'],
                '3_full': row['topic3_question'],
                '3_gif': row.get('topic3_gif', '').strip(),
                'full_gif': row.get('full_gif', '').strip(),
            }
    return topics

USER_TOPICS = load_user_topics()
app.config["STUDENT_TOPICS"] = USER_TOPICS
RESEARCH_STATE = init_dashboard(app)
PROGRESS = StudentProgress(app, RESEARCH_STATE, init_progress(app), LOG_STORE,
                           lambda *args: _prepare_upload(*args), lambda **kw: idle_session_expired(**kw),
                           test_logs=TEST_LOG_STORE, theme_of=lambda attempt: review_artwork_theme(attempt))
app.config["SOL_RECAP_BACKGROUND"] = os.getenv("SOL_RECAP_BACKGROUND")
RECAP = StudentRecap(app, PROGRESS)


@app.get('/health/ready')
def ready():
    """Check collection dependencies without exposing configuration or secrets."""
    try:
        RESEARCH_STATE.settings()
        with RESEARCH_STATE.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.rollback()
        if os.getenv("SOL_ENV") == "production" and not app.extensions["research"]["credential_ready"]():
            raise RuntimeError("Research authentication is unconfigured")
        LOG_STORE.recover()
        PROGRESS.recover_pending()
        for directory in (LOG_DIR, RESEARCH_STATE.path.parent, app.config["SESSION_FILE_DIR"]):
            fd, name = tempfile.mkstemp(prefix=".health-", dir=directory)
            try:
                with os.fdopen(fd, 'wb') as probe:
                    probe.write(b'ready')
                    probe.flush()
                    os.fsync(probe.fileno())
            finally:
                os.unlink(name)
        return jsonify(status="ok")
    except (OSError, ValueError, RuntimeError, sqlite3.Error):
        app.logger.exception("Collection readiness check failed")
        return jsonify(status="unavailable"), 503

# ------------------------------------------------------------------------------------------------------------------------------------------
# TEMPORARY TESTING FLAG - If API GOOGLE IS NOT AVAILABLE, SET TO TRUE TO ALLOW ANSWER SUBMISSION WITHOUT SEARCH RESULTS.
# ------------------------------------------------------------------------------------------------------------------------------------------
# True  = allow answer submission even when there are no search results.
# False = production behavior: answer button only appears after valid results.
ALLOW_ANSWER_WITHOUT_RESULTS_FOR_TESTING = False
#-------------------------------------------------------------------------------------------------------------------------------------------

def get_total_tasks(user_id):
    """Return how many tasks this user has (count non-empty topic entries)."""
    user = get_user_config(user_id)
    count = 0
    for i in range(1, 10):
        if user.get(f'{i}_full'):
            count += 1
        else:
            break
    return count

def assign_random_task_order(user_id):
    total_tasks = get_total_tasks(user_id)
    task_order = [str(i) for i in range(1, total_tasks + 1)]

    # Consistent within this experiment session, new order across new sessions
    seed = f"{user_id}-{session.get('session_id')}"
    rng = random.Random(seed)
    rng.shuffle(task_order)

    session["task_order"] = task_order
    session["task_position"] = 0
    session["task_number"] = task_order[0] if task_order else None
    
    app.logger.debug("Task order for session %s: %s", session.get('session_id'), task_order)

    return task_order

def generate_log_id():
    return f"{datetime.now(LOG_TIME_ZONE).strftime('%Y-%m-%d_%H-%M-%S')}_{uuid.uuid4().hex[:8]}"


def advance_to_next_random_task():
    task_order = session.get("task_order", [])
    task_position = session.get("task_position", 0)

    next_position = task_position + 1

    if next_position >= len(task_order):
        return False

    session["task_position"] = next_position
    session["task_number"] = task_order[next_position]
    return True

def legacy_completed_tasks():
    """Read old browser state once without discarding already completed tasks."""
    if 'pieces_earned' in session:
        session['completed_tasks'] = session.pop('pieces_earned')
        session.pop('reward_shown_logged', None)
    return session.get('completed_tasks', [])


def current_phase():
    user_id = session.get('user_id')
    if not user_id:
        return 'pre_id'

    progress = PROGRESS.current()
    if progress:
        task = progress['tasks'][session.get('task_position', 0)]
        if task['final_answer']:
            return 'completed' if progress['status'] == 'completed' else 'question_complete'
        if not task['first_answer']:
            return 'task_intro'
        return 'searching'

    task_number = session.get('task_number')
    completed = legacy_completed_tasks()
    tasks_started = session.get('tasks_started', [])
    total_tasks = get_total_tasks(user_id)

    if total_tasks and len(completed) >= total_tasks:
        return 'completed'
    if not task_number:
        return 'completed'
    if task_number in completed:
        return 'question_complete'
    if task_number in tasks_started:
        return 'searching'
    return 'task_intro'

def phase_redirect_url(phase=None):
    if phase is None:
        phase = current_phase()
    if phase in ('question_complete', 'completed') and (progress := PROGRESS.current()):
        if PROGRESS.pending_review(progress):
            return url_for('task')
    if phase == 'pre_id':
        return url_for('welcome')
    if phase == 'task_intro':
        # The browser's Back reaches here from the introductions, which must not start the question.
        progress = PROGRESS.current()
        return PROGRESS.entry_url(progress) if progress else url_for('task')
    if phase == 'searching':
        return url_for('search_page')
    if phase == 'question_complete':
        return url_for('next_task')
    if phase == 'completed':
        return url_for('thank_you')
    return url_for('welcome')

@app.after_request
def add_no_store_headers(response):
    content_type = response.headers.get('Content-Type', '')
    if content_type.startswith('text/html'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    # Student pages: no MIME sniffing, no framing by other sites, and children's
    # queries in our URLs are never sent as a referrer to the pages they open.
    # (The dashboard sets its own stricter headers.)
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'same-origin')
    return response


RICH_TEXT_TAGS = re.compile(r'&lt;(/?)(b|strong|i|em)&gt;|&lt;br\s*/?&gt;', re.IGNORECASE)


@app.template_filter('rich_text')
def rich_text(value):
    """Render search-engine titles/snippets as text, keeping only emphasis tags.

    The engine highlights matches with <b>; anything else from a web page is
    shown as text, never interpreted as HTML.
    """
    text = str(escape(html.unescape(str(value or ''))))

    def allowed(match):
        return f"<{match.group(1)}{match.group(2).lower()}>" if match.group(2) else "<br>"
    return Markup(RICH_TEXT_TAGS.sub(allowed, text))

class TaskConfigError(Exception):
    pass

#Global constants for template rendering
ERROR_URL = "error.html"
SEARCH_URL = "search.html"
HOME_URL = "home.html"

def render_task_config_error(message):
    return render_template(ERROR_URL, show_search=False,
                           error_title="Sessione non configurata",
                           error_message=message), 500

def get_user_config(user_id):
    user = session.get('task_config') if session.get('user_id') == user_id else None
    if not user:
        assignment = scheduled_assignment(RESEARCH_STATE.settings(), user_id)
        user = assignment['topics'] if assignment else None
    if not user:
        raise TaskConfigError(
            f"Mancano le domande per il numero {user_id}. Chiedi al ricercatore."
        )
    return user


def untouched_run_for(user_id):
    """This browser already holds today's admitted run for the ID, and no task has been searched yet."""
    if not user_id or session.get('user_id') != user_id or not session.get('session_id'):
        return False
    if session.get('tasks_started') or legacy_completed_tasks() or session.get('task_position', 0):
        return False
    if (session.get('study_session') or {}).get('date') != datetime.now(LOG_TIME_ZONE).date().isoformat():
        return False
    try:
        return RESEARCH_STATE.attempt_metadata(session['session_id']) is not None
    except (OSError, sqlite3.Error):
        return False


STUDENT_IDLE_SECONDS = 60 * 60


def idle_session_expired(*, touch=True):
    """Apply the 60-minute idle limit on a page navigation; True once the run has ended.

    Every page the participant opens counts as activity, and every page enforces
    the limit, so a run left open on a device cannot continue days later.
    Only call this from page navigations: background requests (autocomplete, frame
    checks) run in parallel and must not write the session.
    """
    if not session.get('user_id'):
        return False
    try:
        idle = (datetime.now() - datetime.fromisoformat(session.get('last_active', ''))).total_seconds()
    except (TypeError, ValueError):
        idle = 0
    if idle > STUDENT_IDLE_SECONDS:
        session.clear()
        return True
    if touch:
        session['last_active'] = datetime.now().isoformat()
    return False


@app.context_processor
def base():
    form = SearchForm()
    return dict(
        form=form,
        allow_answer_without_results_for_testing=ALLOW_ANSWER_WITHOUT_RESULTS_FOR_TESTING,
        session_id=session.get('session_id', '')
    )

@app.route("/")
def index():
    return redirect(url_for('welcome'))

@app.route("/welcome")
def welcome():
    """Splash page — SOL Search logo + Start button."""
    if request.args.get('reset') == '1':
        session.clear()
        return render_template("welcome.html", show_search=False)
    if current_phase() != 'pre_id':
        return redirect(phase_redirect_url())
    return render_template("welcome.html", show_search=False)

@app.route("/search")
def search_page():
    """Search bar page — the main SOL Search interface."""
    phase = current_phase()
    if phase not in ('task_intro', 'searching'):
        return redirect(phase_redirect_url(phase))

    # Expire after 60 minutes of inactivity (counted across every page).
    if idle_session_expired():
        return redirect(url_for('welcome'))

    # Mark this task as started — phase advances to 'searching'.
    task_number = session.get('task_number')
    tasks_started = session.get('tasks_started', [])
    if task_number not in tasks_started:
        tasks_started.append(task_number)
        session['tasks_started'] = tasks_started

    form = SearchForm()
    reminder = get_user_config(session.get('user_id')).get(str(session.get('task_number'))+'_full')
    return render_template(HOME_URL, form=form, show_search=True, reminder=reminder)

@app.route('/start', methods=['GET', 'POST'])
@PROGRESS.start_route
def start_page():
    enrollment_settings = RESEARCH_STATE.settings()
    resumable = RESEARCH_STATE.progress_ids_for_date(datetime.now(LOG_TIME_ZONE).date().isoformat())
    val_ids = sorted({uid for uid, person in enrollment_settings['participant_registry'].items() if person['active']}
                     | resumable, key=participant_sort_key) + list(TEST_EXPERIMENTS)
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        if untouched_run_for(user_id):
            # Same ID submitted again before any task began (a double tap, a stale
            # start page): continue that run instead of admitting a second, empty one.
            return redirect(url_for('task'))
        previous_session = dict(session)
        for admission_try in range(3):
            assignment = (assignment_for_test_id(user_id, datetime.now(LOG_TIME_ZONE).date())
                          if is_test_participant(user_id) else scheduled_assignment(enrollment_settings, user_id))
            if assignment is None:
                if admission_try:
                    session.clear()
                    session.update(previous_session)
                return render_template('start.html', show_search=False, valid_ids=val_ids,
                                       start_error="La sessione non è disponibile. Chiedi al ricercatore di controllare l’iscrizione, l’anno scolastico, la data e le domande."), 400
            session.clear()
            session['user_id'] = user_id
            session['task_config'] = deepcopy(assignment['topics'])
            session['question_set'] = deepcopy(assignment['question_set'])
            session['study_session'] = {key: deepcopy(assignment['session'][key])
                                        for key in ('id', 'name', 'date', 'theme', 'grade', 'number', 'school_year')
                                        if key in assignment['session']}
            session['assignment_source'] = assignment['source']
            session['session_id'] = str(uuid.uuid4())
            session['log_id'] = generate_log_id()
            session['completed_tasks'] = []
            session['tasks_started'] = []
            session['last_active'] = datetime.now().isoformat()

            assign_random_task_order(user_id)

            try:
                record_run(LOG_DIR, RESEARCH_STATE, user_id, session['session_id'],
                           session['log_id'], session['task_order'], session['task_config'],
                           settings=enrollment_settings,
                           study_session=session['study_session'],
                           question_set=session['question_set'],
                           assignment_source=session['assignment_source'], admit=True, progress_enabled=True)
            except ValueError as error:
                if str(error) == 'settings_changed' and admission_try < 2:
                    # A researcher saved settings during this request. Nothing was
                    # admitted; check eligibility again against the saved version.
                    enrollment_settings = RESEARCH_STATE.settings()
                    continue
                failure = error
            except (OSError, sqlite3.Error) as error:
                failure = error
            else:
                break
            # A committed attempt can republish its sidecar later. Without that
            # durable snapshot, do not admit a new attempt or discard an old one.
            app.logger.error("Could not publish research run metadata", exc_info=failure)
            try:
                durable = RESEARCH_STATE.attempt_metadata(session['session_id'])
            except (OSError, sqlite3.Error):
                durable = None
            if durable is None:
                session.clear()
                session.update(previous_session)
                return render_template('start.html', show_search=False, valid_ids=val_ids,
                                       start_error="Impossibile avviare la sessione in sicurezza. Riprova o chiedi al ricercatore."), 503
            break

        return redirect(url_for('task'))

    if current_phase() != 'pre_id':
        return redirect(phase_redirect_url())
    
    return render_template('start.html', show_search=False, valid_ids=val_ids)

@app.get('/test-run/restart')
def restart_test_run():
    """Leave a test run, so a test ID can start again. A child's run is never left this way."""
    if session.get('progress_is_test'):
        session.clear()
    return redirect(url_for('start_page'))


@app.route('/task', methods=['GET', 'POST'])
def task():
    if PROGRESS.current():
        if idle_session_expired():
            return redirect(url_for('welcome'))
        return PROGRESS.page()
    phase = current_phase()
    if phase != 'task_intro':
        return redirect(phase_redirect_url(phase))
    if idle_session_expired():
        return redirect(url_for('welcome'))

    user_id = session.get('user_id')
    task_number = session.get('task_number')

    try:
        user = get_user_config(user_id)
    except TaskConfigError as err:
        return render_task_config_error(str(err))

    topic = user.get(str(task_number)+'_full')
    topic_title = user.get(str(task_number)+'_short')
    
    display_task_number  = session.get("task_position", 0) + 1
    
    return render_template(
        'task.html',
        show_search=False,
        task_number=display_task_number,
        actual_topic_number=task_number,
        topic=topic,
        topic_title=topic_title,
        user_id=user_id
    )

@app.route("/result", methods=['GET', 'POST'])
def result():
    phase = current_phase()
    if phase != 'searching':
        return redirect(phase_redirect_url(phase))
    if idle_session_expired():
        return redirect(url_for('welcome'))

    reminder = get_user_config(session.get('user_id')).get(str(session.get('task_number'))+'_full')
    form = SearchForm()
    page = 1

    if request.method == "POST":
        raw_query = request.form.get('query', '').strip()
    else:
        raw_query = (request.args.get("query") or session.get("query") or '').strip()
        try:
            page = max(1, int(request.args.get("page", 1)))
        except (TypeError, ValueError):
            page = 1

    if not raw_query:
        return render_template(HOME_URL,
                               form=form,
                               show_search=True,
                               reminder=reminder,
                               search_error="Inserisci una domanda prima di cercare.")

    rpp = 10 # results per page; may be changed later
    query = sanitize_query(raw_query)
    corrected_query = query
    query_correction_source = "none"

    if not query.strip():
        return render_template(HOME_URL,
                               form=form,
                               show_search=True,
                               reminder=reminder,
                               search_error="Inserisci una domanda prima di cercare.")

    # ---- Custom "Indietro" back-navigation history -----------------------
    # nav_stack: ordered list of {"q","page"} views the participant actually
    #            saw, chronological. Drives the back button.
    # results_by_query: exact normalized result set per query in this task,
    #            so going back replays what was shown (never a re-search).
    back_nav = request.args.get("back") == "1"
    nav_stack = list(session.get("nav_stack", []))
    results_by_query = session.get("results_by_query", {})
    NAV_STACK_CAP = 50

    def record_view(view_query, view_page):
        nonlocal nav_stack
        if back_nav:
            if nav_stack:
                nav_stack = nav_stack[:-1]
        else:
            top = nav_stack[-1] if nav_stack else None
            if (not top) or top.get("q") != view_query or top.get("page") != view_page:
                nav_stack.append({"q": view_query, "page": view_page})
                if len(nav_stack) > NAV_STACK_CAP:
                    del nav_stack[:-NAV_STACK_CAP]
        session["nav_stack"] = nav_stack

    def back_url():
        # Invariant: after record_view(), nav_stack[-1] is the current view.
        if len(nav_stack) >= 2:
            prev = nav_stack[-2]
            return url_for('result', query=prev["q"], page=prev["page"], back=1)
        return url_for('search_page')

    def cache_query_results(results, total_pages, no_results_message=None):
        results_by_query[query] = {
            "results": results,
            "raw_query": raw_query,
            "corrected_query": corrected_query,
            "query_correction_source": query_correction_source,
            "total_pages": total_pages,
            "no_results_message": no_results_message,
        }
        session["results_by_query"] = results_by_query

    def render_no_results(message, query_correction_source):
        session["search_results"] = []
        session["query"] = query
        session["raw_query"] = raw_query
        session["corrected_query"] = corrected_query
        session["query_correction_source"] = query_correction_source
        cache_query_results([], 0, message)
        record_view(query, 1)
        return render_template(SEARCH_URL, title="Search Results",
                               search_results=[], query=query,
                               raw_query=raw_query,
                               corrected_query=corrected_query, query_correction_source=query_correction_source, page=page,
                               total_pages=0, show_search=True,
                               reminder=reminder,
                               no_results_message=message,
                               back_url=back_url())

    def normalize_result(result):
        if not isinstance(result, dict):
            return {}
        result.setdefault("displayed_link", result.get("source_title") or result.get("link", ""))
        result.setdefault("title", "")
        result.setdefault("snippet", "")
        result.setdefault("docid", "")
        result.setdefault("link", "")
        return result

    cached_for_query = results_by_query.get(query)
    use_cached_results = request.method == "GET" and isinstance(cached_for_query, dict)

    if use_cached_results:
        all_results = [normalize_result(r) for r in cached_for_query.get("results", [])]
        raw_query = cached_for_query.get("raw_query", raw_query)
        corrected_query = cached_for_query.get("corrected_query", corrected_query)
        query_correction_source = cached_for_query.get("query_correction_source", query_correction_source)
        cached_no_results_message = cached_for_query.get("no_results_message")
        # Keep the legacy single-slot mirror in sync for any other reader.
        session["search_results"] = all_results
        session["query"] = query
        session["raw_query"] = raw_query
        session["corrected_query"] = corrected_query
        session["query_correction_source"] = query_correction_source
    else:
        cached_no_results_message = None
        try:
            corrected_query, raw_results, _, query_correction_source = search_backend.search(query, page, rpp, theme=run_theme())
        except Exception:
            if ALLOW_ANSWER_WITHOUT_RESULTS_FOR_TESTING:
                return render_no_results("Modalità test: nessun risultato disponibile, ma puoi comunque scrivere una risposta.", query_correction_source=query_correction_source)
            return render_template(ERROR_URL, show_search=False,
                                   error_title="Ricerca non disponibile",
                                   error_message="Il motore di ricerca non risponde. Riprova tra poco.",
                                   is_search_engine_error=True, search_error_log="Connection Error"), 503

        all_results = [normalize_result(r) for r in raw_results]
        session["search_results"] = all_results
        session["query"] = query
        session["raw_query"] = raw_query
        session["corrected_query"] = corrected_query
        session["query_correction_source"] = query_correction_source

    if len(all_results) == 0:
        return render_no_results(
            cached_no_results_message or "Non ci sono risultati per la vostra domanda. Provate a fare un'altra domanda!",
            query_correction_source=query_correction_source)

    total_results = len(all_results)
    total_pages = min(10, math.ceil(total_results / rpp))
    page = min(page, total_pages)
    if not use_cached_results:
        cache_query_results(all_results, total_pages)
    record_view(query, page)
    start = (page - 1) * rpp
    end = start + rpp
    return render_template(SEARCH_URL, title="Search Results",
                           search_results=all_results[start:end],
                           query=query, raw_query=raw_query,
                           corrected_query=corrected_query,
                           page=page, total_pages=total_pages,
                           show_search=True, reminder=reminder, query_correction_source=query_correction_source,
                           back_url=back_url())

@app.route("/webpage")
def webpage():
    """Embedded web viewer — renders external page in a sandboxed iframe."""
    phase = current_phase()
    if phase != 'searching':
        return redirect(phase_redirect_url(phase))
    if idle_session_expired():
        return redirect(url_for('welcome'))
    url = request.args.get("url", "")
    query = request.args.get("query", "")
    page = request.args.get("page", "1")
    # Only web addresses: a javascript:/data: URL would run inside our own origin.
    if not _is_web_address(url):
        return redirect(url_for('search_page'))
    return render_template("webpage.html", url=url, query=query, page=page, show_search=False)

def _is_web_address(url):
    """True for a well-formed http(s) address with a host; malformed input is simply refused."""
    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _is_safe_iframe_url(url):
    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return False, "malformed-url"
    if parsed.scheme not in ("http", "https"):
        return False, f"scheme-not-allowed:{parsed.scheme}"
    host = parsed.hostname
    if not host:
        return False, "no-host"
    try:
        for _, _, _, _, sockaddr in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False, f"private-ip:{ip}"
    except (socket.gaierror, ValueError) as e:
        return False, f"dns-error:{type(e).__name__}"
    return True, None


IFRAME_PROBE_MAX_REDIRECTS = 5


def _probe_frame_headers(url):
    """HEAD (or GET) the page, re-checking every redirect target before following it."""
    for _ in range(IFRAME_PROBE_MAX_REDIRECTS + 1):
        safe, reason = _is_safe_iframe_url(url)
        if not safe:
            return None, f"ssrf-rejected:{reason}"
        r = requests.head(url, allow_redirects=False, timeout=3)
        if r.status_code == 405:
            r = requests.get(url, allow_redirects=False, timeout=3, stream=True)
            r.close()
        location = r.headers.get("location")
        if r.is_redirect and location:
            try:
                url = urljoin(url, location)
            except ValueError:
                return None, "ssrf-rejected:malformed-url"
            continue
        return r, None
    return None, "too-many-redirects"


def _shown_result_link(url):
    """Our stored copy of a result link shown in this task, so the server never fetches
    an address of the browser's choosing (results are cleared when the task ends)."""
    for cached in session.get("results_by_query", {}).values():
        for result in cached.get("results", []):
            if result.get("link") == url:
                return result["link"]
    return None

@app.route("/iframe_check")
def iframe_check():
    """Probe a target URL's headers to predict whether it can be embedded in an iframe.
    Used by webpage.html to log webpageLoadSucceeded / webpageLoadFailed.
    """
    # Only a participant who is currently searching can make the server probe a URL.
    if current_phase() != 'searching':
        return jsonify({"blocked": None, "reason": "no-active-search"})
    url = request.args.get("url", "")
    if not url:
        return jsonify({"blocked": None, "reason": "empty-url"})
    link = _shown_result_link(url)
    if link is None:
        return jsonify({"blocked": None, "reason": "not-a-search-result"})

    try:
        r, problem = _probe_frame_headers(link)
        if r is None:
            return jsonify({"blocked": None, "reason": problem})
        headers = {k.lower(): v for k, v in r.headers.items()}
        xfo = headers.get("x-frame-options", "").lower()
        csp = headers.get("content-security-policy", "").lower()
        if "deny" in xfo or "sameorigin" in xfo:
            return jsonify({"blocked": True, "reason": f"x-frame-options:{xfo}"})
        if "frame-ancestors" in csp:
            return jsonify({"blocked": True, "reason": "csp:frame-ancestors"})
        return jsonify({"blocked": False, "reason": None})
    except (requests.RequestException, ValueError) as e:
        # requests can parse Location even with allow_redirects=False and raise
        # a plain ValueError before returning the response.
        return jsonify({"blocked": None, "reason": f"request-error:{type(e).__name__}"})

# Powers the search-bar autocomplete dropdown in layout.html.
@app.route("/autocomplete")
def autocomplete():
    query = request.args.get("query", "").strip()
    empty_response = {"suggestions": [], "source": "none", "query_model": None}

    # Suggestions call the paid search API: only for a participant in a session.
    if not session.get('user_id') or len(query) < 3:
        return jsonify(empty_response)

    try:
        suggestions, source = search_backend.autocomplete(query, theme=run_theme())
        if not suggestions:
            return jsonify(empty_response)
        return jsonify({
            "suggestions": suggestions,
            "source": source,
            "query_model": search_backend.autocomplete_query_model(),
        })
    except Exception as error:
        # Provider exceptions can contain the query or credentials; omit their text.
        app.logger.warning("Autocomplete failed (%s)", type(error).__name__)
        return jsonify(empty_response)

def _append_log_registry(*, user_id, session_id, task_number, num_events,
                         saved_log_filename, status, error=None):
    """Append one summary line to logs/log_registry.jsonl. Never raises."""
    if is_test_participant(user_id):
        return
    try:
        entry = {
            "timestamp": datetime.now(LOG_TIME_ZONE).isoformat(timespec='milliseconds'),
            "user_id": user_id,
            "session_id": session_id,
            "task_number": task_number,
            "num_events": num_events,
            "saved_log_filename": saved_log_filename,
            "status": status,
            "error": error,
        }
        with open(LOG_REGISTRY_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        app.logger.exception("Could not append to the log registry")


def _recovery_files(groups, recovered_from_user, files, recovered_incomplete):
    """Add events of an unfinished experiment, grouped by (uid, sessionID), to INCOMPLETE logs."""
    for (fuid, fsid), entries in groups.items():
        fname = f"{_sanitize_for_filename(fuid)}_{_sanitize_for_filename(fsid)}_INCOMPLETE.log"
        recovered_at = datetime.now(LOG_TIME_ZONE).isoformat(timespec='milliseconds')
        recovery = [{**entry, "recovered": True, "recovered_from_user": recovered_from_user,
                     "recovered_at": recovered_at} for entry in entries]
        recovery.append({"type": "incompleteExperiment", "uid": fuid, "sessionID": fsid,
                         "recovered_from_user": recovered_from_user, "recovered_at": recovered_at})
        files[fname] = files.get(fname, '') + ''.join(json.dumps(entry) + '\n' for entry in recovery)
        recovered_incomplete[fuid] = recovered_incomplete.get(fuid, 0) + len(entries)


def _prepare_other_session_upload(logs, batch_session_id, user_id):
    """Plan recovery files for a batch saved by a page of an earlier session in this browser."""
    groups = {}
    for entry in logs:
        groups.setdefault((entry.get('uid') or 'unknown', entry.get('sessionID') or batch_session_id), []).append(entry)
    files, recovered_incomplete = {}, {}
    _recovery_files(groups, user_id, files, recovered_incomplete)
    return files, {"status": "logged", "saved_events": 0, "recovered_incomplete": recovered_incomplete}


def _prepare_upload(logs, user_id, server_session_id, log_id, task_number, task_order, task_position):
    """Plan all original-format files before committing the upload receipt."""
    files = {}
    recovered_incomplete = {}
    own_logs, foreign_groups = [], {}
    for entry in logs:
        euid = entry.get('uid')
        if euid and euid != user_id:
            foreign_groups.setdefault((euid, entry.get('sessionID') or 'nosession'), []).append(entry)
        else:
            own_logs.append(entry)
    _recovery_files(foreign_groups, user_id, files, recovered_incomplete)

    visible_task_number = task_position + 1
    actual_topic_number = task_number
    safe_user = _sanitize_for_filename(user_id)
    combined_filename = f"{safe_user}_{log_id}_FULL.log"
    task_filename     = f"{safe_user}_{log_id}_task{visible_task_number}_topic{actual_topic_number}.log"
    lines = []
    for entry in own_logs:
        enriched = dict(entry)
        enriched['task_number'] = visible_task_number
        enriched['actual_topic_number'] = actual_topic_number
        enriched['task_order'] = task_order
        enriched['sessionID'] = server_session_id
        if not enriched.get('uid'):
            enriched['uid'] = user_id
        lines.append(json.dumps(enriched) + '\n')
    if lines:
        files[combined_filename] = ''.join(lines)
        files[task_filename] = ''.join(lines)
    return files, {
        "status": "logged", "saved_events": len(own_logs),
        "combined_file": combined_filename,
        "task_file":     task_filename,
        "recovered_incomplete": recovered_incomplete,
    }


def _accept_other_session_batch(data, batch_session_id, logs, user_id):
    """Keep a batch saved under an earlier session of this browser as recovered data.

    Rejecting it would leave the browser retrying it forever, unable to send any
    newer events. It is stored like events of a previous, unfinished participant.
    """
    try:
        # Events logged before a run has its server ID, such as the choice of ID, say only whose they are.
        metadata = RESEARCH_STATE.attempt_metadata(batch_session_id)
        is_test = (metadata.get('is_test') if metadata else
                   all(is_test_participant(entry.get('uid')) for entry in logs))
        store = TEST_LOG_STORE if is_test else LOG_STORE
        receipt = store.accept(batch_session_id, data.get('batch_id'),
                                   {"session_id": batch_session_id, "logs": logs},
                                   lambda: _prepare_other_session_upload(logs, batch_session_id, user_id))
    except UploadConflict:
        return jsonify(error="Upload identifier already used for different data"), 409
    except (ValueError, TypeError):
        return jsonify(error="Invalid upload"), 400
    except (OSError, sqlite3.Error):
        app.logger.exception("Upload not acknowledged; pending bytes retained for recovery")
        return jsonify(error="Saving temporarily unavailable. Keep this page open and retry."), 503
    _append_log_registry(user_id=user_id, session_id=batch_session_id, task_number=None,
                         num_events=len(logs), saved_log_filename=None, status="incomplete",
                         error="batch-from-other-session")
    return jsonify(receipt), 200


@app.route('/log_session', methods=['POST'])
def log_session():
    data = request.get_json(force=False, silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Invalid upload"), 400
    session_id = data.get('session_id')
    logs = data.get('logs')
    user_id = session.get('user_id')
    task_number = session.get('task_number')
    server_session_id = session.get('session_id')
    if not (user_id and task_number and isinstance(session_id, str) and isinstance(logs, list) and logs):
        return jsonify(error="Missing user_id, task_number, session_id or logs"), 400
    if any(not isinstance(entry, dict) or not isinstance(entry.get('type'), str)
           or entry.get('uid') is not None and not isinstance(entry['uid'], str)
           or entry.get('sessionID') is not None and not isinstance(entry['sessionID'], str)
           for entry in logs):
        return jsonify(error="Invalid log event"), 400
    if session_id != server_session_id:
        return _accept_other_session_batch(data, session_id, logs, user_id)
    warn_logging_contract_issues(logs, task_number)
    log_id = session.get('log_id')
    if not log_id:
        log_id = generate_log_id()
        session['log_id'] = log_id
    try:
        store = TEST_LOG_STORE if session.get('progress_is_test') else LOG_STORE
        receipt = store.accept(session_id, data.get('batch_id'),
            {"session_id": session_id, "logs": logs},
            lambda: PROGRESS.prepare_logs(logs, lambda entries: _prepare_upload(
                entries, user_id, server_session_id, log_id, task_number,
                session.get('task_order', []), session.get('task_position', 0))))
    except UploadConflict:
        return jsonify(error="Upload identifier already used for different data"), 409
    except SubmissionConflict:
        return jsonify(error="La risposta è già confermata oppure la domanda è cambiata."), 409
    except SessionUnavailable:
        return jsonify(error="La sessione non è disponibile oggi."), 403
    except (ValueError, TypeError):
        return jsonify(error="Invalid upload"), 400
    except (OSError, sqlite3.Error):
        app.logger.exception("Upload not acknowledged; pending bytes retained for recovery")
        return jsonify(error="Saving temporarily unavailable. Keep this page open and retry."), 503
    progress = PROGRESS.current()
    if progress and not PROGRESS.publish(progress):
        return jsonify(error="Saving temporarily unavailable. Keep this page open and retry."), 503
    # Attempt context is already durable in research.sqlite3. A missing sidecar
    # can be recreated without blocking an acknowledgement of saved interactions.
    try:
        metadata = RESEARCH_STATE.attempt_metadata(session_id)
        if metadata:
            publish_metadata(LOG_DIR, metadata)
            RESEARCH_STATE.mark_attempt_published(session_id)
    except (OSError, ValueError, sqlite3.Error):
        app.logger.exception("Run context is pending publication")
    _append_log_registry(user_id=user_id, session_id=session_id,
                         task_number=session.get('task_position', 0) + 1,
                         num_events=len(logs), saved_log_filename=receipt.get('task_file'),
                         status="success", error=None)
    return jsonify(receipt), 200

def warn_logging_contract_issues(logs, default_task_number):
    """Warn about client logging gaps.

    Only the event position and type are written to the server log, never the
    event itself: events contain children's queries and answers.
    """
    def warn(message, index, entry):
        app.logger.warning("%s at log entry %d (type=%s)", message, index,
                           entry.get('type') if isinstance(entry, dict) else type(entry).__name__)

    previous_query_submit = None
    for index, entry in enumerate(logs, start=1):
        if not isinstance(entry, dict):
            warn("[Logging WARN] log entry is not an object", index, entry)
            previous_query_submit = None
            continue

        event_type = entry.get('type')

        if event_type == 'querySubmitted':
            marker = (entry.get('task_number') or default_task_number, (entry.get('query') or '').strip())
            if marker == previous_query_submit:
                warn("[Logging WARN] duplicate consecutive querySubmitted", index, entry)
            previous_query_submit = marker
        else:
            previous_query_submit = None

        if event_type == 'webpageClosed':
            missing = [field for field in ('url', 'durationMs', 'exitReason') if field not in entry]
            if missing:
                warn(f"[Logging WARN] webpageClosed missing fields {missing}", index, entry)

        if event_type == 'pageNavigationClicked' and entry.get('toPage') is None:
            warn("[Logging WARN] pageNavigationClicked has null toPage", index, entry)

        if event_type in ('browserBackBlocked', 'customBackButtonClicked'):
            missing = [field for field in ('fromURL', 'toURL') if not entry.get(field)]
            if missing:
                warn(f"[Logging WARN] {event_type} missing navigation fields {missing}", index, entry)

        if event_type in SERP_QUERY_FIELD_EVENTS:
            missing = [field for field in ('rawQuery', 'sanitizedQuery') if field not in entry]
            if missing:
                warn(f"[Logging WARN] SERP event missing query fields {missing}", index, entry)


@app.route('/end', methods=['POST'])
def end_task():
    progress = PROGRESS.current()
    if progress:
        if not progress['tasks'][session['task_position']]['final_answer']:
            return jsonify(error="Conferma la risposta finale prima di continuare."), 409
        return PROGRESS.next_page()
    phase = current_phase()
    if phase != 'searching':
        return redirect(phase_redirect_url(phase))
    if idle_session_expired():
        return redirect(url_for('welcome'))
    task_number = session.get('task_number')

    # Preserve completion for an admitted pre-upgrade run.
    completed = legacy_completed_tasks()
    if task_number not in completed:
        completed.append(task_number)
        session['completed_tasks'] = completed

    return redirect(url_for('next_task'))


REVIEW_ARTWORK_THEMES = {
    'spazio': 'space', 'tema spazio': 'space', 'sistema solare': 'space', 'space': 'space',
    'corpo umano': 'ear', 'corpo umano (orecchio)': 'ear', 'tema corpo umano (orecchio)': 'ear',
    'orecchio': 'ear', 'udito': 'ear',
}


# The dashed arrow from the first answer to the final one, on the review page's 760 x 420 stage.
_ARROW_LEFT = {"line": "M110 100 C 20 195, 124 318, 205 372", "tip": "M193 373 L205 372 L199 361", "x": 93, "y": 251}
_ARROW_RIGHT = {"line": "M610 112 C 700 200, 680 330, 604 362", "tip": "M615 351 L604 362 L619 365", "x": 669, "y": 258}
_ARROW_FAR_LEFT = {"line": "M165 100 C 80 190, 90 320, 168 360", "tip": "M156 362 L168 360 L161 349", "x": 105, "y": 249}
REVIEW_ARROWS = {'space-1': _ARROW_LEFT, 'ear-1': _ARROW_LEFT, 'space-2': _ARROW_RIGHT, 'ear-2': _ARROW_RIGHT,
                 'space-3': _ARROW_RIGHT, 'ear-3': _ARROW_FAR_LEFT}


def known_theme(*labels):
    for label in labels:
        if isinstance(label, str):
            theme = REVIEW_ARTWORK_THEMES.get(' '.join(label.casefold().split()))
            if theme:
                return theme
    return None


def review_artwork_theme(progress):
    metadata = progress['metadata']
    return known_theme(metadata.get('question_set_theme'), metadata['study_session_snapshot'].get('theme'))


def run_theme():
    """The theme of this browser's run, from what was frozen when the run started."""
    return known_theme((session.get('question_set') or {}).get('theme'),
                       (session.get('study_session') or {}).get('theme'))


def review_illustration(progress):
    theme = review_artwork_theme(progress)
    return f'images/review/{theme}-recap.webp' if theme else None


@app.get('/task-review/<int:number>')
def task_review(number):
    progress = PROGRESS.current()
    if (not progress or progress['status'] == 'retired' or number not in PROGRESS.reviews(progress)
            or progress['metadata']['study_session_snapshot']['date'] != datetime.now(LOG_TIME_ZONE).date().isoformat()):
        abort(404)
    if idle_session_expired():
        return redirect(url_for('welcome'))
    task = progress['tasks'][number - 1]
    theme = review_artwork_theme(progress)
    topic = str(task['snapshot']['topic_id'])
    animation = poster = piece = None
    if theme and topic in ('1', '2', '3'):
        prefix = 'Spazio' if theme == 'space' else 'Orecchio'
        animation = f'videos/review/{prefix}_0{topic}.mp4'
        poster = f'images/review/{theme}-{topic}.webp'
        piece = f'{theme}-{topic}'
    return render_template('study_handoff.html', review_tasks=[task], review_only=True,
                           animation=animation, poster=poster, piece=piece, arrow=REVIEW_ARROWS.get(piece),
                           is_last=number == len(progress['tasks']))


@app.route('/next_task')
def next_task():
    if PROGRESS.current():
        return PROGRESS.next_page(finish_review=True)
    phase = current_phase()
    if phase != 'question_complete':
        return redirect(phase_redirect_url(phase))
    if idle_session_expired():
        return redirect(url_for('welcome'))

    has_next_task = advance_to_next_random_task()
    
    session.pop("search_results", None)
    session.pop("query", None)
    session.pop("raw_query", None)
    session.pop("corrected_query", None)
    session.pop("query_correction_source", None)
    # Reset back-navigation history so a new task can never step back into
    # the previous task's queries/results.
    session.pop("results_by_query", None)
    session.pop("nav_stack", None)
    
    if not has_next_task:
        return redirect(url_for('thank_you'))
    
    return redirect(url_for('task'))

@app.route('/thank_you')
def thank_you():
    progress = PROGRESS.current()
    if progress:
        if idle_session_expired(touch=False):
            return redirect(url_for('welcome'))
        if progress['status'] != 'completed':
            return PROGRESS.next_page()
        if progress['metadata']['study_session_snapshot']['date'] != datetime.now(LOG_TIME_ZONE).date().isoformat():
            return redirect(url_for('welcome', reset=1))
        reviews = PROGRESS.reviews(progress)
        if not all(reviews.values()):
            return redirect(url_for('task'))
        if not reviews.get(3):
            return render_template('study_handoff.html', review_tasks=[], review_only=False)
        return RECAP.page(progress, review_illustration(progress))
    phase = current_phase()
    if phase != 'completed':
        return redirect(phase_redirect_url(phase))
    user_id = session.get('user_id')
    total_tasks = get_total_tasks(user_id)
    # Don't clear session yet — the "Finish Experiment" button needs
    # user_id/task_number to send final logs via /log_session.
    # Session will be cleared client-side via clearClientData().
    return render_template('end.html', show_search=False,
                           total_tasks=total_tasks)

@app.errorhandler(404)
def page_not_found(e):
    return render_template(ERROR_URL, show_search=False,
                           error_title="Pagina non trovata",
                           error_message="Questa pagina non esiste."), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template(ERROR_URL, show_search=False,
                           error_title="Errore",
                           error_message="Qualcosa non ha funzionato. Riprova o chiedi al ricercatore."), 500

if __name__ == '__main__':
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host='0.0.0.0', port=7001, threaded=True, debug=debug)
