"""Participant recap routes, plus the downloadable snapshot of a finished session."""
from datetime import datetime
from io import BytesIO
from pathlib import Path
import secrets
import sqlite3
from xml.sax.saxutils import escape

from flask import abort, jsonify, render_template, request, send_file, session, url_for
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from student_progress import ZONE
from study_progress import AttemptNotFound, DraftConflict, SubmissionConflict

CONFIDENCE_LABELS = {1: "Poco giusta", 2: "Abbastanza giusta", 3: "Giustissima"}
RECAP_PLACEHOLDER = "images/review/recap-placeholder.svg"
SAVE_ERROR = "Salvataggio non disponibile. Riprova."
CONFLICT_ERROR = "Le risposte sono cambiate in un'altra scheda. Riapri il riepilogo prima di riprovare."


def final_revision(task):
    return next((revision for revision in reversed(task["revisions"])
                 if revision["answer_phase"] == "final-answer"), None)


def latest_final(task):
    revision = final_revision(task)
    return revision["after_text"] if revision else task["final_answer"]["text"]


def render_recap_pdf(columns):
    styles = getSampleStyleSheet()
    styles["Title"].textColor = colors.HexColor("#173769")
    styles["Heading2"].textColor = colors.HexColor("#235b9e")
    styles["BodyText"].leading = 15
    flow = [Paragraph("SOL Search · Le tue risposte", styles["Title"])]

    def add(text, style="BodyText"):
        # Participant text is plain text. ReportLab paragraphs accept markup.
        flow.append(Paragraph(escape(text).replace("\n", "<br/>"), styles[style]))

    for number in (1, 2, 3):
        add(f"Sessione {number}", "Heading2")
        if number not in columns:
            add("Non ci sono risposte per questa sessione.")
            continue
        for task in columns[number]["tasks"]:
            first = task["first_answer"]
            draft = task["recap_drafts"].get("final-answer")
            final = draft["text"] if draft else latest_final(task)
            add(f"Domanda {task['number']} · {task['snapshot']['question']}", "Heading3")
            add(f"Cosa sapevi prima: {first['text'] or 'Non lo so'}")
            add(f"Autovalutazione iniziale: {CONFIDENCE_LABELS.get(first['confidence'], 'Non disponibile')}")
            add(f"Cosa sai adesso: {final}")
            flow.append(Spacer(1, 9))

    def footer(canvas, doc):
        canvas.setFillColor(colors.HexColor("#52647b"))
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(A4[0] - 48, 26, f"Pagina {doc.page}")

    pdf = BytesIO()
    SimpleDocTemplate(pdf, pagesize=A4, leftMargin=48, rightMargin=48, topMargin=40,
                      bottomMargin=48, title="SOL Search - Le tue risposte").build(
                          flow, onFirstPage=footer, onLaterPages=footer)
    return pdf.getvalue()


class StudentRecap:
    render_pdf = staticmethod(render_recap_pdf)

    def __init__(self, app, progress):
        self.app = app
        self.progress = progress
        self.store = progress.store
        app.add_url_rule("/recap/draft", "recap_draft", self.draft, methods=["POST"])
        app.add_url_rule("/recap/save-changes", "recap_save", self.save, methods=["POST"])
        app.add_url_rule("/recap/finish", "recap_finish", self.finish, methods=["POST"])
        app.add_url_rule("/recap/pdf", "recap_pdf", self.pdf)
        app.add_url_rule("/recap/restart", "recap_restart", self.restart, methods=["POST"])

    def _current(self):
        attempt = self.progress.current()
        if (attempt and attempt["status"] == "completed" and self.progress.reviews(attempt).get(3)
                and attempt["metadata"]["study_session_snapshot"]["date"] == datetime.now(ZONE).date().isoformat()
                and not self.progress.expire_idle(touch=False)):
            return attempt
        abort(404)

    @staticmethod
    def _editing_context(attempt):
        return {"study_session_id": attempt["study_session_id"], "attempt_id": attempt["attempt_id"],
                "technical_session_id": attempt["metadata"]["technical_session_id"]}

    def _posted(self):
        attempt = self._current()
        data = request.get_json(silent=True)
        token = data.get("csrf_token") if isinstance(data, dict) else None
        if (not isinstance(token, str) or not token.isascii()
                or not secrets.compare_digest(token, session["progress_csrf"])):
            abort(403)
        if data.get("attempt_id") != attempt["attempt_id"]:
            abort(409)
        return attempt, data

    def _background(self, illustration):
        path = self.app.config.get("SOL_RECAP_BACKGROUND") or illustration or RECAP_PLACEHOLDER
        root = Path(self.app.static_folder).resolve()
        full = (root / path).resolve()
        return full.relative_to(root).as_posix() if full.is_relative_to(root) and full.is_file() else RECAP_PLACEHOLDER

    def page(self, attempt, illustration):
        if not self.progress.session_event(attempt, "sessionCompleted"):
            return self.progress.unavailable()
        key = self.progress.key(attempt["metadata"])
        columns = self.store.recap_columns(key, attempt["attempt_id"])
        return render_template("recap.html", columns=columns, latest_final=latest_final, final_revision=final_revision,
                               confidence_labels=CONFIDENCE_LABELS, background=self._background(illustration),
                               session_number=attempt["metadata"]["study_session_snapshot"]["number"],
                               finished=self.store.recap_finished(attempt["attempt_id"]),
                               csrf_token=session["progress_csrf"], attempt_id=attempt["attempt_id"])

    def draft(self):
        attempt, data = self._posted()
        try:
            columns = self.store.recap_columns(self.progress.key(attempt["metadata"]), attempt["attempt_id"])
            target = next((row for row in columns.values() if row["attempt_id"] == data.get("target_attempt_id")), None)
            if target is None:
                return jsonify(error=CONFLICT_ERROR), 409
            key = self.progress.key({**attempt["metadata"], "study_session_at_collection": target["study_session_id"]})
            base = data.get("answer_revision")
            if type(base) is not int:
                return jsonify(error="Modifica non valida."), 400
            saved = self.store.save_recap_draft(
                key, target["attempt_id"], data.get("number"), "final-answer",
                data.get("text"), data.get("revision"), editing_context=self._editing_context(attempt),
                base_answer_revision=base)
            return jsonify(revision=saved["revision"])
        except (AttemptNotFound, DraftConflict, SubmissionConflict):
            return jsonify(error=CONFLICT_ERROR), 409
        except ValueError:
            return jsonify(error="Modifica non valida."), 400
        except (OSError, sqlite3.Error):
            return jsonify(error=SAVE_ERROR), 503

    def _pdf_for_finish(self, states):
        try:
            return self.render_pdf(states)
        except Exception as error:
            raise OSError("Could not create recap PDF") from error

    def _commit(self, finish):
        attempt, data = self._posted()
        try:
            self.store.commit_recap(self.progress.key(attempt["metadata"]), attempt["attempt_id"],
                                   data.get("draft_revisions"),
                                   self._pdf_for_finish if finish else None)
            if not self.progress.publish(attempt):
                return jsonify(error=SAVE_ERROR), 503
            return jsonify(saved=True)
        except (AttemptNotFound, DraftConflict, SubmissionConflict):
            return jsonify(error=CONFLICT_ERROR), 409
        except ValueError:
            return jsonify(error="Completa le risposte modificate prima di salvare."), 400
        except (OSError, sqlite3.Error):
            return jsonify(error=SAVE_ERROR), 503

    def save(self):
        return self._commit(finish=False)

    def finish(self):
        return self._commit(finish=True)

    def pdf(self):
        attempt = self._current()
        pdf = self.store.recap_pdf(attempt["attempt_id"])
        if pdf is None:
            abort(404)
        if not self.progress.publish(attempt):
            return self.progress.unavailable()
        response = send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                             download_name="sol-riepilogo.pdf", max_age=0)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    def restart(self):
        attempt, _ = self._posted()
        if not self.store.recap_finished(attempt["attempt_id"]):
            abort(409)
        if not self.progress.publish(attempt):
            return jsonify(error=SAVE_ERROR), 503
        session.clear()
        return jsonify(welcome=url_for("welcome"))
