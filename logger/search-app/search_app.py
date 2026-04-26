from urllib import response
from flask import Flask, render_template, url_for, request, session, redirect, jsonify
import requests, json
from forms import SearchForm
from flask_cors import CORS
import collections
import math
import os
import csv
from datetime import datetime
import re
from spellchecker import SpellChecker
from time import time


app = Flask(__name__)

CORS(app)

app.config['SECRET_KEY'] = 'OtulwLo7gQ'       # Please set a secret key
app.config.update(
    SESSION_COOKIE_SECURE=False,    
    SESSION_COOKIE_SAMESITE='Lax', 
)

db_url = "http://search_engine:7002"
# rpp = 20  # Results per Page (Default: 20) 
rpp = 10  # Results per Page (Default: 20) 

LOG_DIR = 'logs'
os.makedirs(LOG_DIR, exist_ok=True)
spell = SpellChecker(language='en')
# spell = SpellChecker(language='it') # uncomment this when switching to Italian


with open("API_keys.json") as f:
    API_KEY = json.load(f)["serp_api"]["api_key"]

AUTOCOMPLETE_CACHE = {}
CACHE_TTL = 600  # 10 minutes
MAX_SUGGESTIONS = 5



def sanitize_query(query):
    # Removes all characters except letters, numbers, and spaces
    # This is necessary for PyTerrier compatibility
    cleaned_query =  re.sub(r'[^\w\s]', '', query)
    
    # try:
    words = spell.split_words(cleaned_query)
    misspelled = spell.unknown(words)
    corrected_query = ''

    for word in words:
        if word in misspelled:
            corrected_word = spell.correction(word)
            if corrected_word is not None:
                word = corrected_word
        corrected_query += word
        corrected_query += ' '
    # except:
    #     corrected_query = cleaned_query
    
    # f = open("API_keys.json")
    # data = json.load(f)

    # API_KEY = data["serp_api"]["api_key"]
    # SERP_endpoint = data["serp_api"]["SERP_endpoint"]
    # f.close()

    # serpapi_payload = {
    #     "engine": "google",
    #     "q": cleaned_query,
    #     "num": 10,
    #     "filter": 0,
    #     "api_key": API_KEY
    #     }
    
    # serpapi_response = requests.get(url=SERP_endpoint, params=serpapi_payload)

    # serpapi_results = serpapi_response.json()
    # serpapi_query = serpapi_results["search_information"].get("showing_results_for", cleaned_query)

    return cleaned_query, corrected_query.strip()


def load_user_topics(filepath='data/user_topics.csv'):
    topics = {}
    with open(filepath, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',')
        for row in reader:
            user = row['uid']
            topics[user] = {
                '1_short': row['topic1_keyword'],
                '1_full': row['topic1_question'],
                '2_short': row['topic2_keyword'],
                '2_full': row['topic2_question'],
                '3_short': row['topic3_keyword'],
                '3_full': row['topic3_question']
            }
    return topics

USER_TOPICS = load_user_topics()

@app.context_processor
def base():
    form = SearchForm()
    return dict(form=form)

@app.route("/")
def home():
    if 'user_id' not in session:
        return redirect(url_for('start_page'))

    # Check session TTL — expire after 60 minutes of inactivity
    last_active = session.get('last_active')
    if last_active:
        elapsed = (datetime.now() - datetime.fromisoformat(last_active)).total_seconds()
        if elapsed > 3600:  # 60 minutes
            session.clear()
            return redirect(url_for('start_page'))
    session['last_active'] = datetime.now().isoformat()

    form = SearchForm()
    reminder = USER_TOPICS.get(session.get('user_id'), {}).get(str(session.get('task_number'))+'_full')
    return render_template("home.html", form=form, show_search=True, reminder=reminder)

@app.route('/welcome', methods=['GET', 'POST'])
def welcome():
    return render_template("welcome.html", show_search=False)

@app.route('/start', methods=['GET', 'POST'])
def start_page():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        session['user_id'] = user_id
        session['task_number'] = '1'
        session['pieces_earned'] = []
        return redirect(url_for('task'))
    with open("data/uids.txt") as f:
        val_ids = [line.strip() for line in f if line.strip()]
    return render_template('start.html', show_search=False, valid_ids = val_ids)

@app.route('/task', methods=['GET', 'POST'])
def task():
    user_id = session.get('user_id')
    task_number = session.get('task_number')

    topic = USER_TOPICS.get(user_id, {}).get(str(task_number)+'_full')
    topic_title = USER_TOPICS.get(user_id, {}).get(str(task_number)+'_short')

    return render_template("task.html", show_search=False, task_number = task_number, topic = topic, topic_title = topic_title, user_id = user_id)


@app.route("/result", methods=['GET', 'POST'])
def result():

    if request.method == "POST":
        query = request.form['query']
        page = 1
    else:
        query = request.args.get("query")
        page = int(request.args.get("page", 1))
    
    url = "/ranking?query="
    url_affix = "&rpp="
    maxres = '100' # max 10 pages with max 10 results each
    rpp = 10 # results per page; may be changed later
    query, serpapi_query = sanitize_query(query)

    end_query = db_url + url + query + url_affix + maxres
    
    try:
        response = requests.get(end_query)
    except requests.ConnectionError:
        return render_template('error.html', show_search=False,
                               error_title="Connection Error",
                               error_message="Could not connect to the search engine. Please try again later."), 503

    reminder = USER_TOPICS.get(session.get('user_id'), {}).get(str(session.get('task_number'))+'_full')

    if response.status_code != 200:
        return render_template("no_result.html", title="No results found", query=query, serpapi_query=serpapi_query, show_search=True, reminder=reminder)

    try:
        search_results = response.json()
    except (ValueError, KeyError):
        return render_template("no_result.html", title="No results found", query=query, serpapi_query=serpapi_query, show_search=True, reminder=reminder)

    if len(search_results.get("itemlist", [])) == 0:
            return render_template("no_result.html", title="No results found", query= query, serpapi_query=serpapi_query, show_search=True, reminder=reminder)
    else:
        total_results = len(search_results["itemlist"])
        total_pages = min(10, math.ceil(total_results / rpp))
        start = (page - 1) * rpp
        end = start + rpp
        return render_template("search.html", title="Search Results", search_results = search_results['itemlist'][start:end], query=query, serpapi_query = serpapi_query, page=page, total_pages = total_pages, show_search=True, reminder=reminder)

    # f = open("API_keys.json")
    # data = json.load(f)

    # API_KEY = data["serp_api"]["api_key"]
    # SERP_endpoint = data["serp_api"]["SERP_endpoint"]
    # f.close()

    # print(API_KEY, SERP_endpoint)

    # payload = {

    #     "engine": "google",
    #     "q": query,
    #     "start": page * 10,
    #     "num": 10,
    #     "filter": 0,
    #     "api_key": API_KEY

    #     }

    # SERP_response = requests.get(url=SERP_endpoint, params=payload)

    # search_results = SERP_response.json()

    # if len(search_results["organic_results"]) == 0:
    #         return render_template("no_result.html", title="No results found", query= query, show_search=True, reminder=reminder)
    # else:
    #     total_results = len(search_results["organic_results"])
    #     total_pages = min(10, math.ceil(total_results / rpp))
    #     start = (page - 1) * rpp
    #     end = start + rpp
    #     return render_template("search.html", title="Search Results", search_results = search_results['itemlist'][start:end], query=query, page=page, total_pages = total_pages, show_search=True, reminder=reminder)

@app.route("/webpage")
def webpage():
    """Embedded web viewer — renders external page in a sandboxed iframe."""
    url = request.args.get("url", "")
    query = request.args.get("query", "")
    page = request.args.get("page", "1")
    if not url:
        return redirect(url_for('home'))
    return render_template("webpage.html", url=url, query=query, page=page, show_search=False)

@app.route("/autocomplete")

def autocomplete():
    query = request.args.get("query")

    if not query or len(query) < 3:
        return jsonify([])

    # ---- Cache lookup ----
    cached = AUTOCOMPLETE_CACHE.get(query)
    if cached and time() - cached["time"] < CACHE_TTL:
        return jsonify(cached["data"])

    try:
        response = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google_autocomplete",
                "q": query,
                "api_key": API_KEY,
                # uncomment for italian:
                # "hl": "it",
            },
            timeout=5
        )

        response.raise_for_status()
        data = response.json()

        suggestions = [
            s["value"] for s in data.get("suggestions", [])
        ][:MAX_SUGGESTIONS]

        # ---- Store in cache ----
        AUTOCOMPLETE_CACHE[query] = {
            "time": time(),
            "data": suggestions
        }

        return jsonify(suggestions)

    except requests.RequestException as e:
        # graceful fallback (no retries)
        return jsonify([]), 200



@app.route('/log_session', methods=['POST'])
def log_session():
    print("Received /log_session request")
    data = request.get_json(force=False, silent=False)
    print(f"Request JSON data: {data}")

    session_id = data.get('session_id')
    logs = data.get('logs')
    
    user_id = session.get('user_id')
    task_number = session.get('task_number')
    print(f"user_id: {user_id}, task_number: {task_number}, session_id: {session_id}")
    if not (user_id and task_number and logs):
        print("Missing required data: user_id, task_number or logs")
        return jsonify({"error": "Missing session_id or logs"}), 400

    filename = f"{user_id}_task{task_number}_{datetime.now():%Y-%m-%d_%H-%M-%S.%f}.log"
    filepath = os.path.join(LOG_DIR, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        for entry in logs:
            f.write(json.dumps(entry) + '\n')

    return jsonify({"status": "logged", "file": filename}), 200

@app.route('/end', methods=['POST'])
def end_task():
    task_number = session.get('task_number')

    # Record the earned puzzle piece for the current task
    pieces = session.get('pieces_earned', [])
    if task_number not in pieces:
        pieces.append(task_number)
        session['pieces_earned'] = pieces

    return redirect(url_for('reward'))


def get_total_tasks(user_id):
    """Return how many tasks this user has (count non-empty topic entries)."""
    user = USER_TOPICS.get(user_id, {})
    count = 0
    for i in range(1, 10):  # support up to 9 tasks
        if user.get(f'{i}_full'):
            count += 1
        else:
            break
    return count


@app.route('/next_task')
def next_task():
    """Advance to the next task number and redirect to the Scenario Page."""
    task_number = session.get('task_number')
    next_num = str(int(task_number) + 1)
    session['task_number'] = next_num
    return redirect(url_for('task'))


@app.route('/reward')
def reward():
    user_id = session.get('user_id')
    task_number = session.get('task_number')
    pieces = session.get('pieces_earned', [])
    total_tasks = get_total_tasks(user_id)
    is_last = len(pieces) >= total_tasks

    return render_template('reward.html',
                           show_search=False,
                           task_number=task_number,
                           pieces_earned=pieces,
                           total_tasks=total_tasks,
                           is_last=is_last)


@app.route('/thank_you')
def thank_you():
    pieces = session.get('pieces_earned', [])
    total_tasks = get_total_tasks(session.get('user_id'))
    # Don't clear session yet — the "Finish Experiment" button needs
    # user_id/task_number to send final logs via /log_session.
    # Session will be cleared client-side via clearClientData().
    return render_template('end.html', show_search=False,
                           pieces_earned=pieces,
                           total_tasks=total_tasks)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', show_search=False,
                           error_title="Page Not Found",
                           error_message="The page you are looking for does not exist."), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('error.html', show_search=False,
                           error_title="Server Error",
                           error_message="Something went wrong on our end. Please try again."), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7001, threaded=True, debug=True)


