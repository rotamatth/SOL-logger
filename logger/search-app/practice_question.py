"""The practice question ("prova") between the welcome page and the ID. It records nothing.

A group tries the whole flow once on a topic no class studies: the question, a first answer (stars or
"Non lo so"), the search, a page, a final answer and a picture with both answers. Then it chooses its ID
and the experiment starts as before.

Nothing is recorded, by construction:
- It comes before the ID, so this browser has no participant, run or log yet. Every route here refuses
  to run once a run exists, and the run's own routes keep refusing a browser without one.
- Its pages load practice-page.js instead of logger.js: no event is kept, stored in the browser or sent.
- Its answers stay in this browser's session only, to draw the last picture, and leave it when the
  group goes on to the ID page (choosing an ID clears the session anyway).
- Its search uses its own engine (VERTEX_PROVA_*). Without that engine, or when the dashboard turns the
  practice off, Inizia leads straight to the ID page.
"""
import secrets

from flask import jsonify, redirect, render_template, request, session, url_for

# The name search_backend gives the practice engine (search_backend.PRACTICE_THEME); a test keeps them equal.
PRACTICE_THEME = "practice"
PRACTICE_ROUTES = {"search": "practice_search", "result": "practice_result", "webpage": "practice_webpage",
                   "autocomplete": "practice_autocomplete", "iframe_check": "practice_iframe_check",
                   "end": "practice_end"}
STATE_KEY = "practice"
# What the shared search pages keep in the session while a question is searched.
SEARCH_KEYS = ("nav_stack", "results_by_query", "search_results", "query", "raw_query",
               "corrected_query", "query_correction_source")
ANSWER_MAX = 5000
FIRST_ANSWER_ERROR = "Scrivi una risposta e scegli quanto è giusta, oppure conferma “Non lo so”."


class PracticeQuestion:
    def __init__(self, app, *, settings, engine_ready, phase, resume_url, search_results, frame_check,
                 autocomplete, is_web_address):
        self.settings, self.engine_ready, self.phase, self.resume_url = settings, engine_ready, phase, resume_url
        self.search_results, self.frame_check = search_results, frame_check
        self.autocomplete_response, self.is_web_address = autocomplete, is_web_address
        for rule, endpoint, view, methods in (
                ("/prova", "practice_intro", self.intro, ["GET"]),
                ("/prova/domanda", "practice_question", self.question, ["GET", "POST"]),
                ("/prova/cerca", "practice_search", self.search, ["GET"]),
                ("/prova/risultati", "practice_result", self.result, ["GET", "POST"]),
                ("/prova/pagina", "practice_webpage", self.webpage, ["GET"]),
                ("/prova/controllo-pagina", "practice_iframe_check", self.iframe_check, ["GET"]),
                ("/prova/suggerimenti", "practice_autocomplete", self.autocomplete, ["GET"]),
                ("/prova/fine", "practice_end", self.end, ["POST"]),
                ("/prova/finita", "practice_done", self.done, ["GET"]),
                ("/prova/esci", "practice_leave", self.leave, ["POST"])):
            app.add_url_rule(rule, endpoint, view, methods=methods)

    # -- Where this browser stands ------------------------------------------------------------

    def offered(self):
        """On in the dashboard and an engine to search. Otherwise Inizia goes straight to the ID page."""
        return bool(self.settings()["enabled"] and self.engine_ready())

    @staticmethod
    def state():
        return session.get(STATE_KEY)

    @staticmethod
    def step(state):
        if state is None:
            return "intro"
        if state["first"] is None:
            return "question"
        return "search" if state["final"] is None else "done"

    @staticmethod
    def forget():
        for key in (STATE_KEY, *SEARCH_KEYS):
            session.pop(key, None)

    def begin(self):
        """A new practice, with the question as the dashboard has it now: a later edit does not change it."""
        current = self.settings()
        state = {"id": secrets.token_hex(8), "csrf": secrets.token_urlsafe(32), "topic": current["topic"],
                 "question": current["question"], "first": None, "final": None}
        for key in SEARCH_KEYS:
            session.pop(key, None)
        session[STATE_KEY] = state
        return state

    def blocked(self):
        """A redirect when this browser may not be in the practice now, else None."""
        if self.phase() != "pre_id":
            return redirect(self.resume_url())
        if not self.offered():
            self.forget()
            return redirect(url_for("start_page"))
        return None

    def step_url(self, state):
        return url_for({"intro": "practice_intro", "question": "practice_question",
                        "search": "practice_search", "done": "practice_done"}[self.step(state)])

    def searching(self):
        """The practice state when this browser may search in it now, else None."""
        state = self.state()
        if self.phase() != "pre_id" or not self.offered() or self.step(state) != "search":
            return None
        return state

    @staticmethod
    def valid_token(state, token):
        return isinstance(token, str) and secrets.compare_digest(token, state["csrf"])

    @staticmethod
    def page_values(state):
        return {"practice": True, "practice_csrf": state["csrf"], "session_id": f"prova-{state['id']}",
                "search_first_answer": state["first"], "child_routes": PRACTICE_ROUTES}

    # -- Pages --------------------------------------------------------------------------------

    def intro(self):
        if refused := self.blocked():
            return refused
        state = self.state()
        if state is not None:
            return redirect(self.step_url(state))
        return render_template("practice_intro.html", next_url=url_for("practice_question"))

    def question(self):
        if refused := self.blocked():
            return refused
        state = self.state() or self.begin()
        if self.step(state) not in ("question", "search"):
            return redirect(self.step_url(state))
        if request.method == "POST":
            return self.submit_first(state)
        return self.first_page(state)

    def first_page(self, state, error=None, text="", confidence=None, status=200):
        return render_template("first_answer.html", practice=True, task_number=None, topic=state["question"],
                               attempt_id=state["id"], first_answer=state["first"], error=error,
                               draft_text=text, draft_confidence=confidence, csrf_token=state["csrf"],
                               submit_url=url_for("practice_question"),
                               search_url=url_for("practice_search")), status

    def submit_first(self, state):
        if not self.valid_token(state, request.form.get("csrf_token")):
            return jsonify(error="Conferma scaduta: ricarica la pagina."), 403
        if state["first"] is not None:
            return redirect(url_for("practice_question"), code=303)
        outcome = request.form.get("outcome")
        text = request.form.get("text", "")
        confidence = request.form.get("confidence")
        confidence = int(confidence) if confidence in ("1", "2", "3") else None
        if outcome == "unknown":
            first = {"outcome": "unknown", "text": None, "confidence": None}
        elif outcome == "answered" and text.strip() and len(text) <= ANSWER_MAX and confidence is not None:
            first = {"outcome": "answered", "text": text, "confidence": confidence}
        else:
            return self.first_page(state, FIRST_ANSWER_ERROR, text[:ANSWER_MAX], confidence, 400)
        session[STATE_KEY] = {**state, "first": first}
        return redirect(url_for("practice_question"), code=303)

    def search(self):
        if refused := self.blocked():
            return refused
        state = self.state()
        if self.step(state) != "search":
            return redirect(self.step_url(state))
        return render_template("home.html", show_search=True, reminder=state["question"], **self.page_values(state))

    def result(self):
        if refused := self.blocked():
            return refused
        state = self.state()
        if self.step(state) != "search":
            return redirect(self.step_url(state))
        values = self.page_values(state)
        return self.search_results(theme=PRACTICE_THEME, reminder=state["question"],
                                   routes=values.pop("child_routes"), **values)

    def webpage(self):
        if refused := self.blocked():
            return refused
        state = self.state()
        if self.step(state) != "search":
            return redirect(self.step_url(state))
        url = request.args.get("url", "")
        if not self.is_web_address(url):
            return redirect(url_for("practice_search"))
        return render_template("webpage.html", url=url, query=request.args.get("query", ""),
                               page=request.args.get("page", "1"), show_search=False, **self.page_values(state))

    def iframe_check(self):
        if self.searching() is None:
            return jsonify({"blocked": None, "reason": "no-active-search"})
        return self.frame_check(request.args.get("url", ""))

    def autocomplete(self):
        if self.searching() is None:
            return jsonify({"suggestions": [], "source": "none", "query_model": None})
        return self.autocomplete_response(request.args.get("query", "").strip(), PRACTICE_THEME)

    def end(self):
        if refused := self.blocked():
            return refused
        state = self.state()
        if self.step(state) == "done":
            return redirect(url_for("practice_done"), code=303)
        if self.step(state) != "search":
            return redirect(self.step_url(state), code=303)
        if not self.valid_token(state, request.form.get("csrf_token")):
            return jsonify(error="Conferma scaduta: ricarica la pagina."), 403
        answer = request.form.get("answer", "")
        if not answer.strip() or len(answer) > ANSWER_MAX:
            return jsonify(error="Scrivi la tua risposta."), 400
        for key in SEARCH_KEYS:
            session.pop(key, None)
        session[STATE_KEY] = {**state, "final": answer}
        return redirect(url_for("practice_done"), code=303)

    def done(self):
        if refused := self.blocked():
            return refused
        state = self.state()
        if self.step(state) != "done":
            return redirect(self.step_url(state))
        return render_template("practice_done.html", first_answer=state["first"], final_answer=state["final"],
                               csrf_token=state["csrf"])

    def leave(self):
        """On to the ID page: the practice's answers leave the session here."""
        state = self.state()
        if state is not None and not self.valid_token(state, request.form.get("csrf_token")):
            return jsonify(error="Conferma scaduta: ricarica la pagina."), 403
        if self.phase() == "pre_id":
            self.forget()
        return redirect(url_for("start_page"), code=303)
