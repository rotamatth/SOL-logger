import requests, json
import math
import os
import csv
import re
import socket
import ipaddress
import search_backend
import uuid
import random
import traceback
import sqlite3
from time import time

from urllib import response
from flask import Flask, render_template, url_for, request, session, redirect, jsonify
from flask_session import Session
from flask_cors import CORS
from forms import SearchForm
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from research_dashboard import init_dashboard
from research_dashboard.collection import record_run
from research_dashboard.student_config import eligible_students

app = Flask(__name__)

# -------------------------------------------------
# 1. Core app + session configuration FIRST
# -------------------------------------------------
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY") or "OtulwLo7gQ"

app.config.update(
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "0") == "1",
    SESSION_COOKIE_SAMESITE="Lax",
)

app.config["SESSION_TYPE"] = "filesystem"   # or "redis"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True

# Initialize server-side sessions
Session(app)

# -------------------------------------------------
# 2. Enable CORS LAST
# -------------------------------------------------
CORS(app, resources={r"/(?!dashboard(?:/|$)).*": {"origins": "*"}}, supports_credentials=True)
rpp = 10  # results per page for pagination; may be changed later

# cache storage for query autocomplete suggestions
AUTOCOMPLETE_CACHE = {}
CACHE_TTL = 600  # 10 minutes
SEARCH_BACKEND = os.getenv("SEARCH_BACKEND", "vertex").lower()

LOG_DIR = os.getenv("SOL_LOG_DIR", "logs_v2")
LOG_TIME_ZONE = ZoneInfo("Europe/Zurich")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_REGISTRY_PATH = os.path.join(LOG_DIR, 'log_registry.jsonl')

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
PUZZLE_ASSET_DIR = 'puzzle_pieces'

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
    
    print(f"[Task Randomization] user_id={user_id}, session_id={session.get('session_id')}, task_order={task_order}")

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

def current_phase():
    user_id = session.get('user_id')
    if not user_id:
        return 'pre_id'

    task_number = session.get('task_number')
    pieces = session.get('pieces_earned', [])
    tasks_started = session.get('tasks_started', [])
    total_tasks = get_total_tasks(user_id)

    if total_tasks and len(pieces) >= total_tasks:
        return 'completed'
    if not task_number:
        return 'completed'
    if task_number in pieces:
        return 'reward'
    if task_number in tasks_started:
        return 'searching'
    return 'task_intro'

def phase_redirect_url(phase=None):
    if phase is None:
        phase = current_phase()
    if phase == 'pre_id':
        return url_for('welcome')
    if phase == 'task_intro':
        return url_for('task')
    if phase == 'searching':
        return url_for('search_page')
    if phase == 'reward':
        return url_for('reward')
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
    return response

class PuzzleConfigError(Exception):
    pass

#Global constants for template rendering
ERROR_URL = "error.html"
SEARCH_URL = "search.html"
HOME_URL = "home.html"

def render_puzzle_config_error(message):
    return render_template(ERROR_URL, show_search=False,
                           error_title="Puzzle Configuration Error",
                           error_message=message), 500

def get_user_config(user_id):
    user = session.get('task_config') if session.get('user_id') == user_id else None
    if not user:
        user = eligible_students(app, RESEARCH_STATE.settings()).get(user_id)
    if not user:
        raise PuzzleConfigError(
            f"No complete student task assignment found for user '{user_id}'."
        )
    return user

def validate_reward_asset(user_id, csv_field, allow_video=False):
    user = get_user_config(user_id)
    filename = user.get(csv_field, '').strip()
    if not filename:
        raise PuzzleConfigError(
            f"Missing '{csv_field}' in data/user_topics.csv for user '{user_id}'."
        )

    allowed_exts = ('.gif', '.mp4') if allow_video else ('.gif',)
    if os.path.basename(filename) != filename or not filename.lower().endswith(allowed_exts):
        exts_label = ".gif or .mp4" if allow_video else ".gif"
        raise PuzzleConfigError(
            f"Invalid '{csv_field}' value for user '{user_id}': '{filename}'. "
            f"Use a {exts_label} filename stored directly in static/puzzle_pieces."
        )

    static_path = os.path.join(app.static_folder, PUZZLE_ASSET_DIR, filename)
    if not os.path.isfile(static_path):
        raise PuzzleConfigError(
            f"Missing reward asset for user '{user_id}': static/{PUZZLE_ASSET_DIR}/{filename}."
        )
    return f"{PUZZLE_ASSET_DIR}/{filename}"

def get_unlocked_piece(user_id, task_number, display_task_number=None):
    try:
        task_num = int(task_number)
    except (TypeError, ValueError):
        raise PuzzleConfigError(f"Invalid task number for puzzle reward: '{task_number}'.")

    label_number = display_task_number if display_task_number is not None else task_num

    labels = {
        1: "primo",
        2: "secondo",
        3: "ultimo",
    }
    return {
        'task_num': task_num,
        'label': labels.get(label_number, str(label_number)),
        'static_filename': validate_reward_asset(user_id, f'{task_num}_gif'),
    }

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

    # Check session TTL — expire after 60 minutes of inactivity
    last_active = session.get('last_active')
    if last_active:
        elapsed = (datetime.now() - datetime.fromisoformat(last_active)).total_seconds()
        if elapsed > 3600:  # 60 minutes
            session.clear()
            return redirect(url_for('welcome'))
    session['last_active'] = datetime.now().isoformat()

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
def start_page():
    enrollment_settings = RESEARCH_STATE.settings()
    student_configs = eligible_students(app, enrollment_settings)
    val_ids = list(student_configs)
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        if user_id not in student_configs:
            return render_template('start.html', show_search=False, valid_ids=val_ids,
                                   start_error="Questo ID non è disponibile. Chiedi al ricercatore di controllare l'assegnazione dei compiti."), 400
        session.clear()
        session['user_id'] = user_id
        session['task_config'] = dict(student_configs[user_id])
        session['session_id'] = str(uuid.uuid4())
        session['log_id'] = generate_log_id()
        session['pieces_earned'] = []
        session['tasks_started'] = []
        session['reward_shown_logged'] = []
        session['last_active'] = datetime.now().isoformat()
        
        assign_random_task_order(user_id)

        try:
            record_run(LOG_DIR, RESEARCH_STATE, user_id, session['session_id'],
                       session['log_id'], session['task_order'], session['task_config'],
                       settings=enrollment_settings)
        except (OSError, ValueError, sqlite3.Error):
            # Research metadata failure must not discard student interaction logs.
            app.logger.warning("Could not record research run metadata", exc_info=True)
        
        return redirect(url_for('task'))

    if current_phase() != 'pre_id':
        return redirect(phase_redirect_url())
    
    return render_template('start.html', show_search=False, valid_ids=val_ids)

@app.route('/task', methods=['GET', 'POST'])
def task():
    phase = current_phase()
    if phase != 'task_intro':
        return redirect(phase_redirect_url(phase))

    user_id = session.get('user_id')
    task_number = session.get('task_number')

    try:
        user = get_user_config(user_id)
    except PuzzleConfigError as err:
        return render_puzzle_config_error(str(err))

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
            corrected_query, raw_results, _, query_correction_source = search_backend.search(query, page, rpp)
        except Exception:
            if ALLOW_ANSWER_WITHOUT_RESULTS_FOR_TESTING:
                return render_no_results("Modalità test: nessun risultato disponibile, ma puoi comunque scrivere una risposta.", query_correction_source=query_correction_source)
            return render_template(ERROR_URL, show_search=False,
                                   error_title="Connection Error",
                                   error_message="Could not connect to the search engine. Please try again later.",
                                   is_search_engine_error=True), 503

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
    url = request.args.get("url", "")
    query = request.args.get("query", "")
    page = request.args.get("page", "1")
    if not url:
        return redirect(url_for('search_page'))
    return render_template("webpage.html", url=url, query=query, page=page, show_search=False)

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

@app.route("/iframe_check")
def iframe_check():
    """Probe a target URL's headers to predict whether it can be embedded in an iframe.
    Used by webpage.html to log webpageLoadSucceeded / webpageLoadFailed.
    """
    url = request.args.get("url", "")
    if not url:
        return jsonify({"blocked": None, "reason": "empty-url"})

    safe, ssrf_reason = _is_safe_iframe_url(url)
    if not safe:
        return jsonify({"blocked": None, "reason": f"ssrf-rejected:{ssrf_reason}"})

    try:
        r = requests.head(url, allow_redirects=True, timeout=3)
        if r.status_code == 405:
            r = requests.get(url, allow_redirects=True, timeout=3, stream=True)
            r.close()
        headers = {k.lower(): v for k, v in r.headers.items()}
        xfo = headers.get("x-frame-options", "").lower()
        csp = headers.get("content-security-policy", "").lower()
        if "deny" in xfo or "sameorigin" in xfo:
            return jsonify({"blocked": True, "reason": f"x-frame-options:{xfo}"})
        if "frame-ancestors" in csp:
            return jsonify({"blocked": True, "reason": "csp:frame-ancestors"})
        return jsonify({"blocked": False, "reason": None})
    except requests.RequestException as e:
        return jsonify({"blocked": None, "reason": f"request-error:{type(e).__name__}"})

# Powers the search-bar autocomplete dropdown in layout.html.
@app.route("/autocomplete")
def autocomplete():
    query = request.args.get("query")

    if not query or len(query) < 3:
        return jsonify({"suggestions": [], "source": "none", "query_model": None})
    
    cached = AUTOCOMPLETE_CACHE.get(query)
    if cached and time() - cached["time"] < CACHE_TTL:
        return cached["data"]

    try:
        suggestions, source = search_backend.autocomplete(query)
        return jsonify({
            "suggestions": suggestions,
            "source": source,
            "query_model": search_backend.autocomplete_query_model(),
        })
    except Exception:
        traceback.print_exc()
        return jsonify({"suggestions": [], "source": "none", "query_model": None}), 200

def _append_log_registry(*, user_id, session_id, task_number, num_events,
                         saved_log_filename, status, error=None):
    """Append one summary line to logs/log_registry.jsonl. Never raises."""
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
        traceback.print_exc()


def _write_incomplete_recovery(foreign_groups, recovered_from_user):
    """Persist events left behind by a previous, unfinished participant.

    ``foreign_groups`` maps (foreign_uid, client_session_id) -> list of that
    participant's log entries that arrived mixed into another participant's
    submission. Each group is appended to its own deterministic
    ``<uid>_<sid>_INCOMPLETE.log`` file (so repeated recoveries accumulate
    instead of spawning new files) and the file is closed with an
    ``incompleteExperiment`` marker line. Returns a {uid: num_events} summary.
    Never raises.
    """
    recovered_summary = {}
    for (fuid, fsid), entries in foreign_groups.items():
        try:
            safe_fuid  = _sanitize_for_filename(fuid)
            short_fsid = _sanitize_for_filename(fsid)[:8]
            fname = f"{safe_fuid}_{short_fsid}_INCOMPLETE.log"
            fpath = os.path.join(LOG_DIR, fname)
            recovered_at = datetime.now(LOG_TIME_ZONE).isoformat(timespec='milliseconds')
            with open(fpath, 'a', encoding='utf-8') as f:
                for entry in entries:
                    enriched = dict(entry)
                    enriched['recovered']           = True
                    enriched['recovered_from_user'] = recovered_from_user
                    enriched['recovered_at']        = recovered_at
                    f.write(json.dumps(enriched) + '\n')
                f.write(json.dumps({
                    "type": "incompleteExperiment",
                    "uid": fuid,
                    "sessionID": fsid,
                    "recovered_from_user": recovered_from_user,
                    "recovered_at": recovered_at,
                }) + '\n')
            print(
                f"[log] RECOVER incomplete uid={fuid} session={fsid} "
                f"events={len(entries)} file={fname} recovered_from={recovered_from_user}"
            )
            _append_log_registry(
                user_id=fuid, session_id=fsid, task_number=None,
                num_events=len(entries), saved_log_filename=fname,
                status="incomplete", error=f"recovered-from:{recovered_from_user}",
            )
            recovered_summary[fuid] = recovered_summary.get(fuid, 0) + len(entries)
        except Exception:
            traceback.print_exc()
    return recovered_summary


@app.route('/log_session', methods=['POST'])
def log_session():
    data = request.get_json(force=False, silent=True) or {}

    session_id = data.get('session_id')
    logs = data.get('logs')
    num_events = len(logs) if isinstance(logs, list) else 0

    user_id = session.get('user_id')
    task_number = session.get('task_number')
    server_session_id = session.get('session_id')

    if not (user_id and task_number and session_id and isinstance(logs, list) and logs):
        print(f"[log] ERROR missing-data user={user_id} session={session_id} task={task_number}")
        _append_log_registry(
            user_id=user_id, session_id=session_id, task_number=task_number,
            num_events=num_events, saved_log_filename=None,
            status="error", error="missing-data",
        )
        return jsonify({"error": "Missing user_id, task_number, session_id or logs"}), 400

    if session_id != server_session_id:
        print(
            f"[log] REJECT session-mismatch user={user_id} "
            f"client={session_id} server={server_session_id}"
        )
        _append_log_registry(
            user_id=user_id, session_id=session_id, task_number=task_number,
            num_events=num_events, saved_log_filename=None,
            status="error", error="session-mismatch",
        )
        return jsonify({"error": "Session mismatch"}), 409

    # If events from a different participant (a previous, unfinished session on
    # the same device) arrived mixed into this submission, never reject the
    # batch — the old behaviour lost the real participant's data too. Keep the
    # current participant's events (and uid-less / generic ones) for the normal
    # log, and recover the other participant's events into their own
    # incomplete-experiment log instead of discarding them.
    own_logs = []
    foreign_groups = {}
    for entry in logs:
        euid = entry.get('uid') if isinstance(entry, dict) else None
        if euid and euid != user_id:
            esid = entry.get('sessionID') or 'nosession'
            foreign_groups.setdefault((euid, esid), []).append(entry)
        else:
            own_logs.append(entry)

    recovered_incomplete = {}
    if foreign_groups:
        recovered_incomplete = _write_incomplete_recovery(foreign_groups, user_id)
        logs = own_logs
        num_events = len(logs)
        if not logs:
            # The whole batch belonged to a previous participant; it has been
            # recovered. Return OK so the client clears its buffer and the
            # study can proceed.
            return jsonify({
                "status": "logged",
                "saved_events": 0,
                "recovered_incomplete": recovered_incomplete,
            }), 200

    warn_logging_contract_issues(logs, task_number)

    log_id = session.get('log_id')
    if not log_id:
        log_id = generate_log_id()
        session['log_id'] = log_id

    visible_task_number = session.get("task_position", 0) + 1
    actual_topic_number = task_number
    task_order          = session.get("task_order", [])

    safe_user = _sanitize_for_filename(user_id)
    combined_filename = f"{safe_user}_{log_id}_FULL.log"
    task_filename     = f"{safe_user}_{log_id}_task{visible_task_number}_topic{actual_topic_number}.log"

    combined_path = os.path.join(LOG_DIR, combined_filename)
    task_path     = os.path.join(LOG_DIR, task_filename)

    with open(combined_path, 'a', encoding='utf-8') as full_f, \
         open(task_path, 'a', encoding='utf-8') as task_f:
        for entry in logs:
            enriched = dict(entry)
            enriched['task_number']         = visible_task_number
            enriched['actual_topic_number'] = actual_topic_number
            enriched['task_order']          = task_order
            if server_session_id:
                enriched['sessionID'] = server_session_id
            if not enriched.get('uid') and user_id:
                enriched['uid'] = user_id

            line = json.dumps(enriched) + '\n'
            full_f.write(line)
            task_f.write(line)

    is_last_task = bool(task_order) and session.get("task_position", 0) >= len(task_order) - 1
    is_session_end = any(
        isinstance(e, dict) and e.get("type") == "experimentFinished"
        for e in logs
    )

    if is_session_end:
        marker = "SESSION_END"
    elif is_last_task:
        marker = "LAST_TASK"
    else:
        marker = None

    if marker:
        print(
            f"[log] OK {marker} user={user_id} session={session_id} "
            f"task={visible_task_number}/{len(task_order) or '?'} events={num_events} "
            f"task_file={task_filename} full_file={combined_filename}"
        )
    else:
        print(
            f"[log] OK user={user_id} session={session_id} "
            f"task={visible_task_number} events={num_events} file={task_filename}"
        )
    _append_log_registry(
        user_id=user_id, session_id=session_id, task_number=visible_task_number,
        num_events=num_events, saved_log_filename=task_filename,
        status="success", error=None,
    )

    return jsonify({
        "status":        "logged",
        "combined_file": combined_filename,
        "task_file":     task_filename,
        "recovered_incomplete": recovered_incomplete,
    }), 200

def warn_logging_contract_issues(logs, default_task_number):
    previous_query_submit = None

    for index, entry in enumerate(logs, start=1):
        if not isinstance(entry, dict):
            print(f"[Logging WARN] log entry {index} is not an object: {entry}")
            previous_query_submit = None
            continue

        event_type = entry.get('type')

        if event_type == 'querySubmitted':
            marker = (
                entry.get('task_number') or default_task_number,
                (entry.get('query') or '').strip(),
            )
            if marker == previous_query_submit:
                print(
                    "[Logging WARN] duplicate consecutive querySubmitted "
                    f"for task/query at log entry {index}: {entry}"
                )
            previous_query_submit = marker
        else:
            previous_query_submit = None

        if event_type == 'webpageClosed':
            missing_fields = [
                field for field in ('url', 'durationMs', 'exitReason')
                if field not in entry
            ]
            if missing_fields:
                print(
                    "[Logging WARN] webpageClosed missing fields "
                    f"{missing_fields} at log entry {index}: {entry}"
                )

        if event_type == 'pageNavigationClicked' and entry.get('toPage') is None:
            print(
                "[Logging WARN] pageNavigationClicked has null toPage "
                f"at log entry {index}: {entry}"
            )

        if event_type in ('browserBackBlocked', 'customBackButtonClicked'):
            missing_fields = [
                field for field in ('fromURL', 'toURL')
                if not entry.get(field)
            ]
            if missing_fields:
                print(
                    f"[Logging WARN] {event_type} missing navigation fields "
                    f"{missing_fields} at log entry {index}: {entry}"
                )

        if event_type in SERP_QUERY_FIELD_EVENTS:
            missing_fields = [
                field for field in ('rawQuery', 'sanitizedQuery')
                if field not in entry
            ]
            if missing_fields:
                print(
                    "[Logging WARN] SERP event missing query fields "
                    f"{missing_fields} at log entry {index}: {entry}"
                )

@app.route('/end', methods=['POST'])
def end_task():
    phase = current_phase()
    if phase != 'searching':
        return redirect(phase_redirect_url(phase))
    task_number = session.get('task_number')

    # Record the earned puzzle piece for the current task
    pieces = session.get('pieces_earned', [])
    if task_number not in pieces:
        pieces.append(task_number)
        session['pieces_earned'] = pieces

    return redirect(url_for('reward'))

@app.route('/next_task')
def next_task():
    phase = current_phase()
    if phase != 'reward':
        return redirect(phase_redirect_url(phase))
    
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

@app.route('/reward')
def reward():
    phase = current_phase()
    if phase not in ('reward', 'completed'):
        return redirect(phase_redirect_url(phase))
    user_id = session.get('user_id')
    task_number = session.get('task_number')
    pieces = session.get('pieces_earned', [])
    total_tasks = get_total_tasks(user_id)
    is_last = len(pieces) >= total_tasks
    display_task_number = session.get("task_position", 0) + 1
    reward_log_key = f"{display_task_number}:{task_number}"
    reward_shown_logged = session.get('reward_shown_logged', [])
    try:
        unlocked_piece = get_unlocked_piece(user_id, task_number, display_task_number)
    except PuzzleConfigError as err:
        return render_puzzle_config_error(str(err))

    log_id = session.get('log_id')
    if log_id and user_id and reward_log_key not in reward_shown_logged:
        try:
            safe_user = _sanitize_for_filename(user_id)
            combined_path = os.path.join(LOG_DIR, f"{safe_user}_{log_id}_FULL.log")
            task_path = os.path.join(LOG_DIR, f"{safe_user}_{log_id}_task{display_task_number}_topic{task_number}.log")
            entry = {
                "type": "rewardShown",
                "uid": user_id,
                "sessionID": session.get("session_id"),
                "task_number": display_task_number,
                "actual_topic_number": task_number,
                "task_order": session.get("task_order", []),
                "piecesEarned": pieces,
                "totalTasks": total_tasks,
                "isLast": is_last,
                "timestamp": datetime.now(LOG_TIME_ZONE).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3],
                "source": "server"
            }
            line = json.dumps(entry) + '\n'
            for path in (combined_path, task_path):
                with open(path, 'a', encoding='utf-8') as f:
                    f.write(line)
            reward_shown_logged.append(reward_log_key)
            session['reward_shown_logged'] = reward_shown_logged
        except Exception as exc:
            app.logger.warning("Failed to write server-side rewardShown: %s", exc)

    return render_template('reward.html',
                           show_search=False,
                           task_number=display_task_number,
                           actual_topic_number=task_number,
                           pieces_earned=pieces,
                           unlocked_piece=unlocked_piece,
                           total_tasks=total_tasks,
                           is_last=is_last)

@app.route('/thank_you')
def thank_you():
    phase = current_phase()
    if phase != 'completed':
        return redirect(phase_redirect_url(phase))
    user_id = session.get('user_id')
    pieces = session.get('pieces_earned', [])
    total_tasks = get_total_tasks(user_id)
    try:
        full_puzzle_static_filename = validate_reward_asset(user_id, 'full_gif', allow_video=True)
    except PuzzleConfigError as err:
        return render_puzzle_config_error(str(err))
    # Don't clear session yet — the "Finish Experiment" button needs
    # user_id/task_number to send final logs via /log_session.
    # Session will be cleared client-side via clearClientData().
    return render_template('end.html', show_search=False,
                           pieces_earned=pieces,
                           total_tasks=total_tasks,
                           full_puzzle_static_filename=full_puzzle_static_filename)

@app.errorhandler(404)
def page_not_found(e):
    return render_template(ERROR_URL, show_search=False,
                           error_title="Page Not Found",
                           error_message="The page you are looking for does not exist."), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template(ERROR_URL, show_search=False,
                           error_title="Server Error",
                           error_message="Something went wrong on our end. Please try again."), 500

if __name__ == '__main__':
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host='0.0.0.0', port=7001, threaded=True, debug=debug)
