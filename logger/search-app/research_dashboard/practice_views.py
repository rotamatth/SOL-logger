"""Settings › Practice question: the question a group tries before choosing its ID.

The engine itself is set in the server's env file (VERTEX_PROVA_*); this page shows whether it is set and
lets a researcher try a search on it. The topic and question are stored apart from the study settings
(practice_settings.py). Nothing a child does in the practice is stored, so there is nothing to show of it.
"""
from flask import redirect, request

PRACTICE_ERRORS = frozenset(("practice_changed", "practice_topic_invalid", "practice_question_invalid",
                             "invalid_practice"))
TEST_QUERY_MAX = 200
TEST_RESULTS = 5


def _domain(link):
    return link.split("://", 1)[-1].split("/", 1)[0]


def register_practice_routes(dash):
    app, bp, state = dash.app, dash.bp, dash.state

    def engine_status():
        status = app.config.get("PRACTICE_ENGINE_STATUS")
        return status() if status else {"configured": False, "shared_with_theme": False}

    def try_search(query):
        """(results, problem) for the test search: the first few titles and sites, nothing kept."""
        query = " ".join(query.split())
        if not query or len(query) > TEST_QUERY_MAX:
            return [], "practice_test_query_invalid"
        search = app.config.get("PRACTICE_SEARCH")
        if search is None or not engine_status()["configured"]:
            return [], "practice_engine_missing"
        try:
            _, results, _, _ = search(query)
        except Exception as error:  # Provider messages can contain credentials: name the type only.
            app.logger.warning("Practice test search failed (%s)", type(error).__name__)
            return [], "practice_test_failed"
        shown = [{"title": result.get("title") or result.get("link", ""), "domain": _domain(result.get("link", ""))}
                 for result in results[:TEST_RESULTS] if isinstance(result, dict)]
        return shown, None if shown else "practice_test_empty"

    @bp.route("/settings/practice", methods=["GET", "POST"])
    def practice_page():
        current = state.practice()
        values = {key: current[key] for key in ("enabled", "topic", "question")}
        revision, error, test = current["revision"], None, None
        if request.method == "POST":
            action = request.form.get("action")
            if action == "save":
                values = {"enabled": request.form.get("enabled") == "1",
                          "topic": request.form.get("topic", ""), "question": request.form.get("question", "")}
                try:
                    revision = int(request.form.get("revision", ""))
                    state.save_practice(values, revision)
                except ValueError as exc:
                    error = str(exc) if str(exc) in PRACTICE_ERRORS else "invalid_practice"
                else:
                    return redirect(dash.u("practice_page", saved="1"))
            elif action == "test":
                query = request.form.get("test_query", "")
                results, problem = try_search(query)
                test = {"query": query, "results": results, "problem": problem}
            else:
                error = "invalid_practice"
        return dash.page("practice", practice=values, revision=revision, error=error, test=test,
                         engine=engine_status(), active_section="practice", research_area="settings",
                         history_grade=request.args.get("grade", "4"), history_year=request.args.get("year", "")
                         ), 400 if error else 200
