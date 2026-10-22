"""Isolated real-template UI preview; never reads or writes study data.

Run with `python tests/ui_fixture.py`, then open http://127.0.0.1:7002/search.
Search, autocomplete and log persistence use synthetic local responses only.
"""
from pathlib import Path
from types import SimpleNamespace
import os

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

APP_ROOT = Path(__file__).resolve().parents[1]
app = Flask(__name__, template_folder=str(APP_ROOT / "templates"),
            static_folder=str(APP_ROOT / "static"))
app.secret_key = "isolated-responsive-fixture"
app.config["TEMPLATES_AUTO_RELOAD"] = True
QUESTION = "Come si forma un buco nero e quali sono le sue caratteristiche?"


@app.before_request
def fixture_identity():
    session.update(user_id="UI-TEST", task_number="1", task_position=0)


@app.context_processor
def context():
    return dict(session_id="issue11-ui-fixture", show_search=False,
                allow_answer_without_results_for_testing=False)


@app.get("/welcome")
def welcome():
    return render_template("welcome.html")


@app.route("/start", methods=["GET", "POST"])
def start_page():
    if request.method == "POST":
        return redirect(url_for("task"))
    return render_template("start.html", valid_ids=["UI-TEST"])


@app.get("/task")
def task():
    return render_template("task.html", task_number=1, actual_topic_number="1",
                           topic=QUESTION, topic_title="Spazio", user_id="UI-TEST")


@app.get("/search")
def search_page():
    return render_template("home.html", form=SimpleNamespace(hidden_tag=lambda: ""),
                           reminder=QUESTION)


@app.route("/result", methods=["GET", "POST"])
def result():
    query = request.values.get("query", "spazio")
    return render_template("search.html", form=SimpleNamespace(hidden_tag=lambda: ""),
        query=query, raw_query=query, corrected_query=query,
        page=int(request.args.get("page", 1)), total_pages=4, reminder=QUESTION,
        search_results=[dict(docid="ui-1", title="Come si forma un buco nero",
            snippet="Un buco nero si forma quando una stella molto grande termina la sua vita.",
            displayed_link="example.test/spazio", link=url_for("article", _external=True))])


@app.get("/webpage")
def webpage():
    return render_template("webpage.html", url=url_for("article"), query="spazio", page=1)


@app.get("/article")
def article():
    return "<h1>Articolo di prova locale</h1><p>Informazioni sullo spazio.</p>"


@app.get("/autocomplete")
def autocomplete():
    return jsonify(suggestions=["spazio e formazione dei buchi neri con parole semplici",
                                "spazio e stelle", "spazio e pianeti"], source="local-fixture")


@app.post("/log_session")
def log_session():
    return jsonify(status="logged", saved_events=len(request.json.get("logs", [])))


@app.get("/iframe_check")
def iframe_check():
    return jsonify(blocked=False)


@app.post("/end")
def end_task():
    return redirect(url_for("reward"))


@app.get("/reward")
def reward():
    return "<p>Conferma ricevuta dalla fixture locale.</p>"


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("SOL_UI_FIXTURE_PORT", "7002")),
            use_reloader=False)
