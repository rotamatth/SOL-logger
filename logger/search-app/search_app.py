from urllib import response
from flask import Flask, render_template, url_for, request, session, redirect, jsonify
import requests, json
from forms import SearchForm
from flask_cors import CORS
import math
import os
import csv
from datetime import datetime
import re

from google.cloud import discoveryengine_v1 as discoveryengine
from google.api_core.client_options import ClientOptions


app = Flask(__name__)

# Allow cross-origin requests if frontend/backend are served separately
CORS(app)

# Flask session configuration
app.config['SECRET_KEY'] = 'OtulwLo7gQ'       # Please set a secret key
app.config.update(
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_SAMESITE='Lax',
)

# --- Vertex AI Search (Discovery Engine) configuration ---
def load_vertex_config():
    """Load Vertex AI Search config from API_keys.json or env vars."""
    project = os.getenv('VERTEX_PROJECT_NUMBER')
    location = os.getenv('VERTEX_LOCATION', 'global')
    engine_id = os.getenv('VERTEX_ENGINE_ID')
    language_code = os.getenv('VERTEX_LANGUAGE_CODE', 'it')

    if not project or not engine_id:
        config_path = os.path.join(os.path.dirname(__file__), 'API_keys.json')
        if os.path.exists(config_path):
            with open(config_path) as f:
                data = json.load(f)
            cfg = data.get('vertex_ai', {})
            project = project or cfg.get('project_number')
            location = cfg.get('location', location)
            engine_id = engine_id or cfg.get('engine_id')
            language_code = cfg.get('language_code', language_code)

    return project, location, engine_id, language_code

VERTEX_PROJECT, VERTEX_LOCATION, VERTEX_ENGINE_ID, VERTEX_LANGUAGE = load_vertex_config()

# Build the serving config path used by the Discovery Engine API
VERTEX_SERVING_CONFIG = (
    f"projects/{VERTEX_PROJECT}/locations/{VERTEX_LOCATION}"
    f"/collections/default_collection/engines/{VERTEX_ENGINE_ID}"
    f"/servingConfigs/default_search"
)

# Initialize the Discovery Engine search client
# Use global endpoint for global location, regional otherwise
client_options = None
if VERTEX_LOCATION and VERTEX_LOCATION != "global":
    client_options = ClientOptions(api_endpoint=f"{VERTEX_LOCATION}-discoveryengine.googleapis.com")

search_client = discoveryengine.SearchServiceClient(client_options=client_options)

# Number of results shown per page in the UI
rpp = 10

# Folder where interaction logs are saved
LOG_DIR = 'logs'
os.makedirs(LOG_DIR, exist_ok=True)


def sanitize_query(query):
    # Keep only letters, digits, and spaces before sending query to the search engine
    return re.sub(r'[^\w\s]', '', query)


def load_user_topics(filepath='data/user_topics.csv'):
    # Load task topics/questions associated with each user ID
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

# Preload user-task mapping at startup
USER_TOPICS = load_user_topics()

@app.context_processor
def base():
    # Make the search form available in all templates
    form = SearchForm()
    return dict(form=form)

@app.route("/")
def home():
    # Prevent access to the search page if the user has not started the study flow
    if 'user_id' not in session:
        return redirect(url_for('start_page'))
    form = SearchForm()
    # Reminder shown in the sidebar for the current task
    reminder = USER_TOPICS.get(session.get('user_id'), {}).get(str(session.get('task_number'))+'_full')  # Change reminder here if needed (Reminder: shown in sidebar)
    return render_template("home.html", form=form, show_search=True, reminder=reminder)

@app.route('/welcome', methods=['GET', 'POST'])
def welcome():
    # Landing page shown before the ID entry page
    return render_template("welcome.html", show_search=False)

@app.route('/start', methods=['GET', 'POST'])
def start_page():
    if request.method == 'POST':
        # Store participant ID and initialize the first task
        user_id = request.form.get('user_id')
        session['user_id'] = user_id
        session['task_number'] = '1'
        # return redirect(url_for('task'))
        return redirect(url_for('home'))
    # Load the list of valid IDs to suggest/validate in the form
    with open("data/uids.txt") as f:
        val_ids = [line.strip() for line in f if line.strip()]
    return render_template('start.html', show_search=False, valid_ids = val_ids)

@app.route('/task', methods=['GET', 'POST'])
def task():
    # Read current user and task information from the session
    user_id = session.get('user_id')
    task_number = session.get('task_number')

    # Fetch the full question and short title for the current task
    topic = USER_TOPICS.get(user_id, {}).get(str(task_number)+'_full')
    topic_title = USER_TOPICS.get(user_id, {}).get(str(task_number)+'_short')

    return render_template("task.html", show_search=False, task_number = task_number, topic = topic, topic_title = topic_title, user_id = user_id)


@app.route("/result", methods=['GET', 'POST'])
def result():

    # POST = new query submission, GET = pagination/navigation
    if request.method == "POST":
        query = request.form['query']
        page = 1
    else:
        query = request.args.get("query")
        page = int(request.args.get("page", 1))
    
    query = sanitize_query(query)
    rpp = 10

    # Task reminder shown together with search results
    reminder = USER_TOPICS.get(session.get('user_id'), {}).get(str(session.get('task_number'))+'_full')

    # --- Vertex AI Discovery Engine search ---
    try:
        search_request = discoveryengine.SearchRequest(
            serving_config=VERTEX_SERVING_CONFIG,
            query=query,
            page_size=rpp,
            offset=(page - 1) * rpp,
            query_expansion_spec=discoveryengine.SearchRequest.QueryExpansionSpec(
                condition=discoveryengine.SearchRequest.QueryExpansionSpec.Condition.AUTO,
            ),
            spell_correction_spec=discoveryengine.SearchRequest.SpellCorrectionSpec(
                mode=discoveryengine.SearchRequest.SpellCorrectionSpec.Mode.AUTO,
            ),
            language_code=VERTEX_LANGUAGE,
        )

        response = search_client.search(search_request)

    except Exception as e:
        print(f"[Vertex AI Search Error] {e}")  # server log only
        return f"Search error — please try again. ({type(e).__name__})"

    # Map Vertex AI results to the format expected by search.html
    search_results = []
    total_results_estimate = response.total_size

    for result_item in response.results:
        doc_data = dict(result_item.document.derived_struct_data)

        # Extract fields from the document's derived_struct_data
        title = str(doc_data.get("title", ""))
        link = str(doc_data.get("link", ""))
        snippet = ""

        # Snippets may be in 'snippets' array or 'snippet' field
        snippets = doc_data.get("snippets")
        if snippets:
            snippet_list = list(snippets)
            if snippet_list:
                snippet_data = dict(snippet_list[0])
                snippet = str(snippet_data.get("htmlSnippet", snippet_data.get("snippet", "")))
        if not snippet:
            snippet = str(doc_data.get("snippet", ""))

        # Extract displayed link (domain)
        displayed_link = link
        if "://" in link:
            displayed_link = link.split("://", 1)[1].split("/", 1)[0]

        # Extract thumbnail if available from pagemap
        thumbnail = None
        pagemap = doc_data.get("pagemap")
        if pagemap:
            pagemap_dict = dict(pagemap)
            cse_thumb = pagemap_dict.get("cse_thumbnail")
            if cse_thumb:
                thumb_list = list(cse_thumb)
                if thumb_list:
                    thumbnail = str(dict(thumb_list[0]).get("src", ""))

        search_results.append({
            "title": title,
            "snippet": snippet,
            "link": link,
            "displayed_link": displayed_link,
            "docid": str(result_item.document.id) if result_item.document.id else link,
            "thumbnail": thumbnail,
        })

    # Render a dedicated page when no results are returned
    if len(search_results) == 0:
        return render_template("no_result.html", title="No results found", query=query, show_search=True, reminder=reminder)
    else:
        total_pages = min(10, math.ceil(total_results_estimate / rpp)) if total_results_estimate > 0 else 1
        return render_template("search.html", title="Search Results", search_results=search_results, query=query, page=page, total_pages=total_pages, show_search=True, reminder=reminder)
    
@app.route('/log_session', methods=['POST'])
def log_session():
    # Receive interaction logs from logger.js and save them to disk
    print("Received /log_session request")
    data = request.get_json(force=False, silent=False)
    print(f"Request JSON data: {data}")

    session_id = data.get('session_id')
    logs = data.get('logs')
    
    # Associate logs with the current study user/task stored in the Flask session
    user_id = session.get('user_id')
    task_number = session.get('task_number')
    print(f"user_id: {user_id}, task_number: {task_number}, session_id: {session_id}")
    if not (user_id and task_number and logs):
        print("Missing required data: user_id, task_number or logs")
        return jsonify({"error": "Missing session_id or logs"}), 400

    # Generate one log file per completed task/session
    filename = f"{user_id}_task{task_number}_{datetime.now():%Y-%m-%d_%H-%M-%S.%f}.log"
    filepath = os.path.join(LOG_DIR, filename)

    # Store each event as one JSON line
    with open(filepath, 'w', encoding='utf-8') as f:
        for entry in logs:
            f.write(json.dumps(entry) + '\n')

    return jsonify({"status": "logged", "file": filename}), 200

@app.route('/end', methods=['POST'])
def end_task():
    task_number = session.get('task_number')
    if task_number == '1':
        session['task_number'] = '2'
        # return redirect(url_for('task'))
        return redirect(url_for('home'))
    elif task_number == '2':
        session['task_number'] = '3'
        # return redirect(url_for('task'))
        return redirect(url_for('home'))
    else:
        session.clear()
        return redirect(url_for('thank_you'))

@app.route('/thank_you')
def thank_you():
    # Final page shown after the task is completed
    return render_template('end.html')

if __name__ == '__main__':
    # Run the search app Flask server
    app.run(host='0.0.0.0', port=7001, threaded=True, debug=True)