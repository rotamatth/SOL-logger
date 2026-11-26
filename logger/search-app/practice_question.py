"""The practice question ("prova") between the ID and the experiment. It records nothing.

An adult sets the tablet's number and hands the tablet over. The group then tries the whole flow once on a
topic no class studies: the question, a first answer (stars or "Non lo so", which can become a written
answer until the first search, as in the real questions), the search, a page, a final answer and a picture
with both answers. Only then does the number's run start, and the experiment goes on as before.

Nothing is recorded, by construction:
- The number only waits in this browser's session, under SETUP_KEY and not user_id, so this browser has no
  participant, run or log yet. Every route here refuses to run once a run exists, and the run's own routes
  keep refusing a browser without one.
- Its pages load practice-page.js instead of logger.js: no event is kept, stored in the browser or sent.
- Its answers stay in this browser's session only, to draw the last picture, and leave it when the group
  goes on (starting the run clears the session anyway).
- Its search uses its own engine (VERTEX_PROVA_*). Without that engine, or when the dashboard turns the
  practice off, the run starts as soon as the number is chosen.
"""
import secrets

from flask import jsonify, redirect, render_template, request, session, url_for

# The name search_backend gives the practice engine (search_backend.PRACTICE_THEME); a test keeps them equal.
PRACTICE_THEME = "practice"
PRACTICE_ROUTES = {"search": "practice_search", "result": "practice_result", "webpage": "practice_webpage",
                   "autocomplete": "practice_autocomplete", "iframe_check": "practice_iframe_check",
                   "end": "practice_end"}
STATE_KEY = "practice"
# The number an adult set on this tablet, until its run starts: {"number", "date", "over"}.
SETUP_KEY = "setup"
# What the shared search pages keep in the session while a question is searched.
SEARCH_KEYS = ("nav_stack", "results_by_query", "search_results", "query", "raw_query",
               "corrected_query", "query_correction_source")
ANSWER_MAX = 5000
FIRST_ANSWER_ERROR = "Scrivi una risposta e scegli quanto è giusta, oppure conferma “Non lo so”."


class PracticeQuestion:
    def __init__(self, app, *, settings, engine_ready, phase, resume_url, search_results, frame_check,
                 autocomplete, is_web_address, today):
        self.settings, self.engine_ready, self.phase, self.resume_url = settings, engine_ready, phase, resume_url
        self.today = today
        self.search_results, self.frame_check = search_results, frame_check
        self.autocomplete_response, self.is_web_address = autocomplete, is_web_address
        for rule, endpoint, view, methods in (
                ("/prova", "practice_intro", self.intro, ["GET"]),
                ("/prova/domanda", "practice_question", self.question, ["GET", "POST"]),
                ("/prova/cambia", "practice_change", self.change, ["POST"]),
                ("/prova/cerca", "practice_search", self.search, ["GET"]),
                ("/prova/risultati", "practice_result", self.result, ["GET", "POST"]),
                ("/prova/pagina", "practice_webpage", self.webpage, ["GET"]),
                ("/prova/controllo-pagina", "practice_iframe_check", self.iframe_check, ["GET"]),
                ("/prova/suggerimenti", "practice_autocomplete", self.autocomplete, ["GET"]),
                ("/prova/fine", "practice_end", self.end, ["POST"]),
                ("/prova/finita", "practice_done", self.done, ["GET"]),
                ("/prova/esci", "practice_leave", self.leave, ["POST"])):
            app.add_url_rule(rule, endpoint, view, methods=methods)

    # -- The number set on this tablet --------------------------------------------------------

    def setup(self):
        """The number set on this tablet today, whose run has not started yet, else None."""
        saved = session.get(SETUP_KEY)
        if saved and saved["date"] != self.today():
            session.pop(SETUP_KEY)
            self.forget()
            return None
        return saved

    def choose(self, number, *, over=False):
        """Set the tablet's number. `over`: its run starts without the practice."""
        current = self.setup()
        if current and current["number"] == number:
            over = over or current["over"]
        else:
            # Another group's practice never goes on under a new number.
            self.forget()
        session[SETUP_KEY] = {"number": number, "date": self.today(), "over": over}

    def comes_first(self, setup):
        """The number is set and its group has the practice before its run."""
        return bool(setup and not setup["over"] and self.offered())

    # -- Where this browser stands ------------------------------------------------------------

    def offered(self):
        """On in the dashboard and an engine to search. Otherwise the run starts right after the number."""
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
        if not self.comes_first(self.setup()):
            self.forget()
            return redirect(url_for("start_page"))
        return None

    def step_url(self, state):
        return url_for({"intro": "practice_intro", "question": "practice_question",
                        "search": "practice_search", "done": "practice_done"}[self.step(state)])

    def searching(self):
        """The practice state when this browser may search in it now, else None."""
        state = self.state()
        # A background request: it reads the session and must not write it.
        if not self.comes_first(session.get(SETUP_KEY)) or self.phase() != "pre_id" or self.step(state) != "search":
            return None
        return state

    @staticmethod
    def can_change(state):
        """As in a real question: a confirmed "Non lo so" may become a written answer, once, until the first search."""
        first = state and state["first"]
        return bool(first and first["outcome"] == "unknown" and state["final"] is None
                    and not session.get("results_by_query"))

    @staticmethod
    def valid_token(state, token):
        return isinstance(token, str) and secrets.compare_digest(token, state["csrf"])

    def page_values(self, state):
        return {"practice": True, "practice_csrf": state["csrf"], "session_id": f"prova-{state['id']}",
                "search_first_answer": state["first"], "child_routes": PRACTICE_ROUTES,
                "first_answer_change_url": url_for("practice_question", change=1) if self.can_change(state) else None}

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
        if request.args.get("change") == "1" and self.can_change(state):
            return self.change_page(state)
        return self.first_page(state)

    def first_page(self, state, error=None, text="", confidence=None, status=200):
        return render_template("first_answer.html", practice=True, task_number=None, topic=state["question"],
                               attempt_id=state["id"], first_answer=state["first"], error=error,
                               draft_text=text, draft_confidence=confidence, csrf_token=state["csrf"],
                               submit_url=url_for("practice_question"), search_url=url_for("practice_search"),
                               change_url=url_for("practice_question", change=1) if self.can_change(state) else None
                               ), status

    def change_page(self, state, error=None, text="", confidence=None, status=200):
        return render_template("first_answer.html", practice=True, task_number=None, topic=state["question"],
                               attempt_id=state["id"], first_answer=None, change_mode=True, error=error,
                               draft_text=text, draft_confidence=confidence, csrf_token=state["csrf"],
                               submit_url=url_for("practice_change"), back_url=url_for("practice_question")), status

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

    def change(self):
        """The group replaces its "Non lo so" with a written answer before searching. Only in this session."""
        if refused := self.blocked():
            return refused
        state = self.state()
        if not self.can_change(state):
            return redirect(self.step_url(state), code=303)
        if not self.valid_token(state, request.form.get("csrf_token")):
            return jsonify(error="Conferma scaduta: ricarica la pagina."), 403
        text = request.form.get("text", "")
        confidence = request.form.get("confidence")
        confidence = int(confidence) if confidence in ("1", "2", "3") else None
        if not text.strip() or len(text) > ANSWER_MAX or confidence is None:
            return self.change_page(state, "Scrivi una risposta e scegli quanto è giusta.", text[:ANSWER_MAX],
                                    confidence, 400)
        session[STATE_KEY] = {**state, "first": {"outcome": "answered", "text": text, "confidence": confidence}}
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
        # These values are taken before the search runs; results and pages always follow a search, which ends the change.
        values = {**self.page_values(state), "first_answer_change_url": None}
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
                               page=request.args.get("page", "1"), show_search=False,
                               **{**self.page_values(state), "first_answer_change_url": None})

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
        """On to the run: the practice's answers leave the session here, and the start page starts the number's run."""
        state = self.state()
        if state is not None and not self.valid_token(state, request.form.get("csrf_token")):
            return jsonify(error="Conferma scaduta: ricarica la pagina."), 403
        setup = self.setup()
        if setup and self.phase() == "pre_id" and self.step(state) == "done":
            self.forget()
            session[SETUP_KEY] = {**setup, "over": True}
        return redirect(url_for("start_page"), code=303)
