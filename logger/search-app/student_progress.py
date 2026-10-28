"""Connect admitted participant runs to durable first answers and progress."""
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
import fcntl
import secrets
import sqlite3
import time
from zoneinfo import ZoneInfo

from flask import jsonify, redirect, render_template, request, session, url_for

from study_progress import AttemptKey, DraftConflict, SubmissionConflict

ZONE = ZoneInfo("Europe/Zurich")


class SessionUnavailable(ValueError):
    """New answers require today's configured session."""


class StudentProgress:
    def __init__(self, app, state, store, logs, prepare_upload):
        self.app, self.state, self.store, self.logs = app, state, store, logs
        self.prepare_upload = prepare_upload
        app.add_url_rule("/first-answer", "first_answer", self.submit_first, methods=["POST"])
        app.add_url_rule("/first-answer/draft", "first_answer_draft", self.save_first_draft, methods=["POST"])
        app.add_url_rule("/final-answer/draft", "final_answer_draft", self.save_final_draft, methods=["POST"])
        app.before_request(self.guard_search)
        app.context_processor(lambda: {"study_context": self.context(), **self.search_context()})

    @staticmethod
    def key(metadata):
        return AttemptKey(metadata["study_id_at_collection"], metadata["participant_id"],
                          metadata["study_session_at_collection"], metadata.get("is_test", False))

    def current(self):
        if not session.get("progress_id"):
            return None
        key = AttemptKey(session["progress_study_id"], session["user_id"],
                         session["progress_session_id"], session.get("progress_is_test", False))
        return self.store.get_attempt(key, session["progress_id"])

    def context(self):
        if not session.get("progress_id"):
            return None
        return {"attempt_id": session["progress_id"], "task_number": session["task_position"] + 1}

    def search_context(self):
        if request.endpoint not in ("search_page", "result", "webpage"):
            return {}
        attempt = self.current()
        if (not attempt or attempt["status"] != "active"
                or attempt["metadata"]["study_session_snapshot"]["date"] != datetime.now(ZONE).date().isoformat()):
            return {}
        task = attempt["tasks"][session["task_position"]]
        if not task["first_answer"] or task["final_answer"] is not None:
            return {}
        draft = task["drafts"].get("final-answer", {"text": "", "revision": 0})
        return {"search_first_answer": task["first_answer"], "final_answer_draft": {
            **draft, "csrf_token": session["progress_csrf"], "attempt_id": attempt["attempt_id"],
            "question_number": session["task_position"] + 1, "url": url_for("final_answer_draft")}}

    @contextmanager
    def admission_lock(self):
        # Serializes the cross-database handoff, without holding a SQLite writer.
        with open(str(self.store.path) + ".admission.lock", "a+b") as lock:
            deadline = time.monotonic() + 2
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Admission busy") from None
                    time.sleep(0.02)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def restore(self, attempt):
        metadata = attempt["metadata"]
        session.clear()
        session.update(user_id=metadata["participant_id"], session_id=metadata["technical_session_id"],
                       log_id=metadata["log_id"], task_config=metadata["topics_snapshot"],
                       study_session=metadata["study_session_snapshot"],
                       question_set=metadata.get("question_set_snapshot"),
                       assignment_source=metadata.get("assignment_source"),
                       progress_id=attempt["attempt_id"], progress_study_id=attempt["study_id"],
                       progress_session_id=attempt["study_session_id"], progress_is_test=attempt["is_test"],
                       progress_csrf=secrets.token_urlsafe(32),
                       task_order=[task["snapshot"]["topic_id"] for task in attempt["tasks"]],
                       task_position=attempt["question_number"] - 1,
                       task_number=attempt["tasks"][attempt["question_number"] - 1]["snapshot"]["topic_id"],
                       pieces_earned=[], tasks_started=[], last_active=datetime.now().isoformat())
        if attempt["phase"] == "search":
            session["tasks_started"] = [session["task_number"]]

    def start_route(self, function):
        @wraps(function)
        def wrapped():
            if request.method != "POST":
                return function()
            previous = dict(session)
            try:
                with self.admission_lock():
                    metadata = self.state.progress_run_for_date(request.form.get("user_id"),
                                                                datetime.now(ZONE).date().isoformat())
                    if metadata is None:
                        response = self.app.make_response(function())
                        if response.status_code != 302:
                            return response
                        metadata = self.state.attempt_metadata(session["session_id"])
                        if not metadata or not metadata.get("progress_enabled"):
                            return response  # Finish a pre-upgrade run using its original flow.
                    key = self.key(metadata)
                    latest = self.store.latest_attempt(key)
                    if latest and latest["status"] == "retired":
                        return render_template("error.html", error_title="La sessione è cambiata",
                                               error_message="Riapri la sessione con il ricercatore."), 409
                    attempt = self.store.start_or_resume(key, metadata["tasks"], metadata)
                    self.restore(attempt)
                    return redirect(url_for("task"))
            except (OSError, sqlite3.Error):
                session.clear()
                session.update(previous)
                return self.unavailable()
        return wrapped

    @staticmethod
    def unavailable():
        return render_template("error.html", show_search=False, error_title="Salvataggio non disponibile",
                               error_message="Riprova o chiedi al ricercatore. I progressi salvati restano disponibili."), 503

    def publish(self, attempt):
        """An outbox ID is also the log receipt ID: lost acknowledgements cannot duplicate events."""
        metadata = attempt["metadata"]
        key = self.key(metadata)
        try:
            for event in self.store.pending_events(key, attempt["attempt_id"]):
                original = event["payload"]["timestamp"]
                timestamp = datetime.fromisoformat(original).astimezone(ZONE).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
                payload = {**event["payload"], "source": "server", "timestamp": timestamp,
                           "progress_timestamp": original}
                number = payload["task_number"]
                self.logs.accept(metadata["technical_session_id"], "progress:" + event["event_id"], payload,
                    lambda p=payload, n=number: self.prepare_upload(
                        [p], metadata["participant_id"], metadata["technical_session_id"], metadata["log_id"],
                        p["actual_topic_number"], p["task_order"], n - 1))
                self.store.acknowledge_event(key, attempt["attempt_id"], event["event_id"])
            return True
        except (OSError, sqlite3.Error):
            self.app.logger.warning("Progress events remain durably queued for publication")
            return False

    def recover_pending(self):
        for attempt in self.store.unpublished_attempts():
            if not self.publish(attempt):
                raise OSError("Progress publication temporarily unavailable")

    def page(self, error=None, text=None, status=200, *, start_task=True):
        attempt = self.current()
        if attempt["metadata"]["study_session_snapshot"]["date"] != datetime.now(ZONE).date().isoformat():
            session.clear()
            return redirect(url_for("welcome"))
        if attempt["status"] == "retired":
            return render_template("error.html", error_title="La sessione è cambiata",
                                   error_message="Riapri la sessione con il ricercatore."), 409
        self.publish(attempt)
        if attempt["status"] == "completed":
            return redirect(url_for("thank_you"))
        number = session["task_position"] + 1
        if number != attempt["question_number"]:
            return self.next_page()
        task = attempt["tasks"][number - 1]
        if start_task:
            try:
                self.store.mark_task_started(self.key(attempt["metadata"]), attempt["attempt_id"], number)
                self.publish(attempt)
            except (OSError, sqlite3.Error):
                error = "Salvataggio non disponibile. Ricarica la pagina o chiedi al ricercatore."
                status = 503
        draft = task["drafts"].get("first-answer", {})
        return render_template("first_answer.html", task_number=number, topic=task["snapshot"]["question"],
                               attempt_id=attempt["attempt_id"], draft_revision=draft.get("revision", 0),
                               draft_text=text if text is not None else draft.get("text", ""),
                               first_answer=task["first_answer"], error=error,
                               csrf_token=session["progress_csrf"], submit_url=url_for("first_answer"),
                               draft_url=url_for("first_answer_draft"), search_url=url_for("search_page")), status

    def checked_context(self, data):
        token = data.get("csrf_token")
        if (not session.get("progress_csrf") or not isinstance(token, str)
                or not secrets.compare_digest(token, session["progress_csrf"])):
            return None, (jsonify(error="Conferma scaduta: ricarica la pagina."), 403)
        attempt = self.current()
        number = data.get("question_number")
        if (attempt is None or data.get("attempt_id") != attempt["attempt_id"]
                or attempt["status"] == "retired"
                or str(number) not in ("1", "2", "3")
                or int(number) != session["task_position"] + 1):
            return None, (jsonify(error="La domanda è cambiata. Ricarica la pagina."), 409)
        if attempt["metadata"]["study_session_snapshot"]["date"] != datetime.now(ZONE).date().isoformat():
            return None, (jsonify(error="La sessione non è disponibile oggi."), 403)
        return attempt, None

    def submit_first(self):
        attempt, error = self.checked_context(request.form)
        if error:
            return error
        try:
            outcome = request.form.get("outcome")
            if outcome not in ("answered", "unknown"):
                raise ValueError("Choose an explicit outcome")
            self.store.submit_first_answer(self.key(attempt["metadata"]), attempt["attempt_id"],
                                           int(request.form["question_number"]), request.form.get("text"),
                                           unknown_confirmed=outcome == "unknown")
        except SubmissionConflict:
            return self.page("La risposta è già stata confermata. Ricarica la pagina.", status=409)
        except ValueError:
            return self.page("Scrivi una risposta oppure conferma “Non lo so”.", request.form.get("text", ""), 400)
        except (OSError, sqlite3.Error):
            return self.page("Salvataggio non riuscito. La risposta è ancora qui: riprova.",
                             request.form.get("text", ""), 503, start_task=False)
        self.publish(attempt)
        return redirect(url_for("task"), code=303)

    def save_first_draft(self):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Bozza non valida"), 400
        attempt, error = self.checked_context(data)
        if error:
            return error
        try:
            saved = self.store.save_draft(self.key(attempt["metadata"]), attempt["attempt_id"],
                                          int(data["question_number"]), "first-answer", data.get("text"),
                                          data.get("revision"))
        except (DraftConflict, SubmissionConflict):
            return jsonify(error="La bozza è cambiata. Conserva il testo e ricarica la pagina."), 409
        except ValueError:
            return jsonify(error="Bozza non valida"), 400
        except (OSError, sqlite3.Error):
            return jsonify(error="Salvataggio non riuscito. Conserva il testo e riprova."), 503
        return jsonify(saved)

    def save_final_draft(self):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Bozza non valida"), 400
        try:
            attempt, error = self.checked_context(data)
            if error:
                return error
            number = int(data["question_number"])
            task = attempt["tasks"][number - 1]
            if (attempt["status"] != "active" or attempt["phase"] != "search"
                    or attempt["question_number"] != number or not task["first_answer"] or task["final_answer"]):
                raise SubmissionConflict("Final draft requires the current search phase")
            saved = self.store.save_draft(self.key(attempt["metadata"]), attempt["attempt_id"],
                                          number, "final-answer", data.get("text"), data.get("revision"))
        except (DraftConflict, SubmissionConflict):
            return jsonify(error="La bozza o la domanda è cambiata. Conserva il testo e ricarica la pagina."), 409
        except ValueError:
            return jsonify(error="Bozza non valida"), 400
        except (OSError, sqlite3.Error):
            return jsonify(error="Salvataggio non riuscito. Conserva il testo e riprova."), 503
        return jsonify(saved)

    def guard_search(self):
        if request.endpoint not in ("search_page", "result", "webpage", "autocomplete", "iframe_check"):
            return None
        attempt = self.current()
        if attempt is None:
            return None
        task = attempt["tasks"][session["task_position"]]
        today = attempt["metadata"]["study_session_snapshot"]["date"] == datetime.now(ZONE).date().isoformat()
        if not today or attempt["status"] != "active" or not task["first_answer"] or task["final_answer"]:
            if request.endpoint == "autocomplete":
                return jsonify(suggestions=[], source="none", query_model=None)
            if request.endpoint == "iframe_check":
                return jsonify(blocked=None, reason="no-active-search")
            if not today:
                session.clear()
                return redirect(url_for("welcome"))
            return redirect(url_for("task"))
        self.publish(attempt)
        return None

    def next_page(self):
        attempt = self.current()
        self.publish(attempt)
        self.restore(attempt)
        return redirect(url_for("thank_you" if attempt["status"] == "completed" else "task"))

    def prepare_logs(self, logs, fallback):
        """Persist final submissions, then route other events using their question context."""
        attempt = self.current()
        if attempt is None:
            return fallback(logs)
        key = self.key(attempt["metadata"])
        files, receipts, foreign = {}, [], []
        final = None
        groups = {}
        for event in logs:
            if event.get("uid") not in (None, session["user_id"]):
                foreign.append(event)
                continue
            if event.get("sessionID") not in (None, session["session_id"]):
                raise ValueError("Conflicting technical session context")
            number = event.get("task_number", session["task_position"] + 1)
            if (type(number) is not int or not 1 <= number <= 3
                    or event.get("attempt_id", attempt["attempt_id"]) != attempt["attempt_id"]):
                raise ValueError("Invalid progress event context")
            if event["type"] == "TaskEnded":
                if event.get("attempt_id") != attempt["attempt_id"] or "task_number" not in event:
                    raise ValueError("Final answer needs explicit attempt and question context")
                candidate = (number, event.get("answer"))
                if final is not None and final != candidate:
                    raise ValueError("Conflicting final answers in one upload")
                final = candidate
            elif event["type"] not in ("TaskStarted", "OwnKnowledgeAnswerSubmitted"):
                groups.setdefault(number, []).append(event)
        metadata = attempt["metadata"]
        if final is not None:
            if (metadata["study_session_snapshot"]["date"] != datetime.now(ZONE).date().isoformat()
                    and attempt["tasks"][final[0] - 1]["final_answer"] is None):
                raise SessionUnavailable("The session is not available today")
            self.store.submit_final_answer(key, attempt["attempt_id"], final[0], final[1])
        for number, entries in groups.items():
            topic = attempt["tasks"][number - 1]["snapshot"]["topic_id"]
            planned, receipt = self.prepare_upload(entries, session["user_id"], session["session_id"],
                                                  session["log_id"], topic, session["task_order"], number - 1)
            for name, content in planned.items():
                files[name] = files.get(name, "") + content
            receipts.append(receipt)
        if foreign:
            planned, receipt = fallback(foreign)
            files.update(planned)
            receipts.append(receipt)
        primary = final[0] if final else next(iter(groups), session["task_position"] + 1)
        _, response = self.prepare_upload([], metadata["participant_id"], metadata["technical_session_id"],
                                          metadata["log_id"], attempt["tasks"][primary - 1]["snapshot"]["topic_id"],
                                          session["task_order"], primary - 1)
        return files, {**response, "saved_events": sum(r["saved_events"] for r in receipts) + int(final is not None),
                       "recovered_incomplete": {k: v for r in receipts for k, v in r["recovered_incomplete"].items()}}
