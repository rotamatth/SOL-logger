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


app = Flask(__name__)

# Allow cross-origin requests if frontend/backend are served separately
CORS(app)

# Flask session configuration
app.config['SECRET_KEY'] = 'OtulwLo7gQ'       # Please set a secret key
app.config.update(
    SESSION_COOKIE_SECURE=False,    
    SESSION_COOKIE_SAMESITE='Lax', 
)

# Internal URL of the search engine service
db_url = "http://search_engine:7002"

# Number of results shown per page in the UI
# rpp = 20  # Results per Page (Default: 20) 
rpp = 10  # Results per Page (Default: 20) 

# Folder where interaction logs are saved
LOG_DIR = 'logs'
os.makedirs(LOG_DIR, exist_ok=True)


def sanitize_query(query):
    # Keep only letters, digits, and spaces before sending query to the search engine
    # This avoids issues with unsupported special characters
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

    ## uncomment when using datasets from ir_datasets
    
    # query = "vaccine"
    # url = "/ranking?query="
    # url_affix = "&rpp="
    # maxres = '100' # max 10 pages with max 10 results each
    # rpp = 10 # results per page; may be changed later
    # query = sanitize_query(query)
    # end_query = db_url + url + query + url_affix + maxres
    
    # try:
    #     response = requests.get(end_query)
    # except requests.ConnectionError:
    #     return "Connection Error" 

    # search_results = response.json()

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
    
    # Build request to the search engine service
    url = "/ranking?query="
    url_affix = "&rpp="
    maxres = '100' # max 10 pages with max 10 results each
    rpp = 10 # results per page; may be changed later
    query = sanitize_query(query)
    end_query = db_url + url + query + url_affix + maxres
    
    try:
        response = requests.get(end_query)
        search_results = response.json()
    except requests.ConnectionError:
        return "Connection Error"
    except Exception:
        return "Search engine error — please rebuild the index and try again."

    # Task reminder shown together with search results
    reminder = USER_TOPICS.get(session.get('user_id'), {}).get(str(session.get('task_number'))+'_full')
    
    # Render a dedicated page when no results are returned
    if len(search_results["itemlist"]) == 0:
            return render_template("no_result.html", title="No results found", query= query, show_search=True, reminder=reminder)
    else:
        # Paginate locally over the returned ranked list
        total_results = len(search_results["itemlist"])
        total_pages = min(10, math.ceil(total_results / rpp))
        start = (page - 1) * rpp
        end = start + rpp
        return render_template("search.html", title="Search Results", search_results = search_results['itemlist'][start:end], query=query, page=page, total_pages = total_pages, show_search=True, reminder=reminder)


    # Alternative Google/SERP API implementation kept for reference
    
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