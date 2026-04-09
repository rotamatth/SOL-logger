"""
Minimal mock server for testing the logger without the full backend.

This server mimics the search-app routes needed to test back navigation logging.
"""

from flask import Flask, jsonify, request, session, redirect, url_for
import os

app = Flask(__name__,
            static_folder=os.path.join(os.path.dirname(__file__), '..', 'static'),
            static_url_path='/static')
app.secret_key = 'test-secret-key'

# Mock search results
MOCK_RESULTS = [
    {
        "docid": "1001",
        "title": "Test Result 1 - Climate Change Effects",
        "snippet": "This is a test snippet about climate change and its effects.",
        "link": "https://example.com/article1",
        "displayed_link": "example.com",
    },
    {
        "docid": "1002",
        "title": "Test Result 2 - Renewable Energy",
        "snippet": "Information about renewable energy sources and sustainability.",
        "link": "https://example.com/article2",
        "displayed_link": "example.com",
    },
    {
        "docid": "1003",
        "title": "Test Result 3 - Environmental Policy",
        "snippet": "Overview of environmental policies and climate action.",
        "link": "https://example.com/article3",
        "displayed_link": "example.com",
    },
]


def render_page(title, content, show_search=True):
    """Render a page with the standard layout."""
    search_form = """
        <form id="search-bar" action="/result" method="POST" class="mb-4">
            <div class="input-group">
                <input type="text" id="search-box" name="query" class="form-control" placeholder="Search...">
                <button type="submit" class="btn btn-primary">Search</button>
            </div>
        </form>
    """ if show_search else ""

    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css">
</head>
<body>
    <nav class="navbar navbar-light bg-light">
        <div class="container">
            <a class="navbar-brand" href="/" id="app-home">Test Search</a>
            <button id="end-task-btn" class="btn btn-outline-secondary">End Task</button>
        </div>
    </nav>
    <div class="container mt-4">
        {search_form}
        {content}
    </div>
    <script src="/static/logger.js"></script>
</body>
</html>
"""


@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('start'))
    content = '<div class="alert alert-info">Welcome! Enter a search query above.</div>'
    return render_page("Home", content)


@app.route('/start', methods=['GET', 'POST'])
def start():
    if request.method == 'POST':
        session['user_id'] = request.form.get('user_id', 'test_user')
        session['task_number'] = '1'
        return redirect(url_for('home'))

    content = """
    <div class="card">
        <div class="card-body">
            <h5 class="card-title">Enter your ID</h5>
            <form id="enter-id-form" action="/start" method="POST">
                <input type="text" id="id-box" name="user_id" class="form-control mb-2" placeholder="Participant ID">
                <button type="submit" class="btn btn-primary">Start</button>
            </form>
        </div>
    </div>
    """
    return render_page("Start", content, show_search=False)


@app.route('/result', methods=['GET', 'POST'])
def result():
    if request.method == 'POST':
        query = request.form.get('query', 'test')
        page = 1
    else:
        query = request.args.get('query', 'test')
        page = int(request.args.get('page', 1))

    total_pages = 2

    # Build results HTML
    results_html = f'<small class="container-info"><p><b>Search Results</b> for: [ {query} ]</p></small><hr>'

    for i, s in enumerate(MOCK_RESULTS, 1):
        rank = i + 10 * (page - 1)
        results_html += f"""
        <article class="media content-section" id="result-{i}" base_ir="{s['docid']}" query="{query}" page="{page}">
            <div class="media-body">
                <h4>
                    <span>{rank}.
                        <a class="result-link" href="{s['link']}" id="abstract-link-{i}" result_rank="{i}">{s['title']}</a>
                    </span>
                </h4>
                <p class="article-content" id="abstract-preview-{i}">
                    {s['snippet']}
                    <a class="result-link" href="{s['link']}" id="readmore-link-{i}" result_rank="{i}">Read More</a>
                </p>
                <div class="article-metadata">
                    <small class="text-muted">{s['displayed_link']}</small>
                </div>
            </div>
        </article>
        """

    # Pagination
    if total_pages > 1:
        prev_disabled = 'disabled' if page == 1 else ''
        next_disabled = 'disabled' if page == total_pages else ''

        page_links = ""
        for p in range(1, total_pages + 1):
            active = 'active' if p == page else ''
            page_links += f'<li class="page-item {active}"><a class="page-link" href="/result?query={query}&page={p}">{p}</a></li>'

        results_html += f"""
        <nav aria-label="Page navigation" class="mt-4">
            <ul class="pagination justify-content-center">
                <li class="page-item {prev_disabled}">
                    <a class="page-link" href="/result?query={query}&page={page-1}">&laquo; Previous</a>
                </li>
                {page_links}
                <li class="page-item {next_disabled}">
                    <a class="page-link" href="/result?query={query}&page={page+1}">Next &raquo;</a>
                </li>
            </ul>
        </nav>
        """

    return render_page("Search Results", results_html)


@app.route('/log_session', methods=['POST'])
def log_session():
    data = request.get_json()
    print(f"[LOG] Received {len(data.get('logs', []))} log entries")
    return jsonify({"status": "logged"}), 200


if __name__ == '__main__':
    print("=" * 60)
    print("Mock Search Server for Testing")
    print("=" * 60)
    print("Starting on http://localhost:7001")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    app.run(host='0.0.0.0', port=7001, debug=False)
