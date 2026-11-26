"""Participant recap routes, plus the PDF snapshot of a finished session that the server keeps."""
from datetime import datetime
from io import BytesIO
from pathlib import Path
import secrets
import sqlite3
from xml.sax.saxutils import escape

from flask import abort, jsonify, render_template, request, session, url_for
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate, Paragraph,
                                SimpleDocTemplate, Spacer)

from recap_picture import PICTURE_RATIO, RecapPicture

from student_progress import ZONE
from study_progress import AttemptNotFound, DraftConflict, SubmissionConflict

CONFIDENCE_LABELS = {1: "Poco giusta", 2: "Abbastanza giusta", 3: "Giustissima"}
RECAP_PLACEHOLDER = "images/review/recap-placeholder.svg"


def _arrow(start, bend_in, magnifier, bend_out, end):
    """The dashed line from a first answer to its final one, through the magnifier, on the 1000 x 667 recap picture."""
    (ex, ey), (cx, cy) = end, bend_out
    length = ((ex - cx) ** 2 + (ey - cy) ** 2) ** 0.5
    ux, uy = (ex - cx) / length, (ey - cy) / length
    left = (round(ex - 13 * ux - 7 * uy), round(ey - 13 * uy + 7 * ux))
    right = (round(ex - 13 * ux + 7 * uy), round(ey - 13 * uy - 7 * ux))
    point = "{0[0]} {0[1]}".format
    return {"line": f"M{point(start)} Q{point(bend_in)} {point(magnifier)} Q{point(bend_out)} {point(end)}",
            "tip": f"M{point(left)} L{point(end)} L{point(right)}", "x": magnifier[0], "y": magnifier[1]}


# Each question's arrow, by theme and by the question's part of the picture: from under its first answer,
# through the magnifier, to its final answer. Every magnifier is where even a card with a long answer never
# reaches: between 266 and 413 for space and ear, whose cards sit in the same places, and in the gap that
# recap.css keeps between the cards for constellations and muscles.
RECAP_ARROWS = {
    "space": {"1": _arrow((45, 200), (22, 265), (40, 340), (55, 420), (95, 486)),
              "2": _arrow((372, 200), (366, 275), (376, 345), (392, 430), (440, 486)),
              "3": _arrow((862, 130), (975, 160), (958, 340), (945, 440), (925, 486))},
    "ear": {"1": _arrow((45, 200), (22, 265), (40, 340), (55, 420), (95, 486)),
            "2": _arrow((470, 200), (468, 270), (480, 340), (500, 420), (520, 486)),
            "3": _arrow((862, 130), (975, 160), (958, 340), (945, 440), (925, 486))},
    # From under the first answer's smallest card, through the magnifier between the two rows, to above the final one.
    "constellations": {"1": _arrow((138, 428), (136, 455), (154, 479), (172, 503), (170, 541)),
                       "2": _arrow((475, 428), (473, 455), (496, 479), (518, 503), (516, 541)),
                       "3": _arrow((812, 428), (810, 455), (839, 479), (868, 503), (866, 541))},
    # Muscles: the rows almost touch, so the arrow goes down the left of the final answer, through the magnifier there.
    "muscles": {"1": _arrow((44, 494), (40, 525), (44, 562), (50, 600), (72, 612)),
                "2": _arrow((381, 494), (377, 525), (381, 562), (387, 600), (409, 612)),
                "3": _arrow((718, 494), (714, 525), (718, 562), (724, 600), (746, 612))},
}
SAVE_ERROR = "Salvataggio non disponibile. Riprova."
CONFLICT_ERROR = "Le risposte sono cambiate in un'altra scheda. Riapri il riepilogo prima di riprovare."


def final_revision(task):
    return next((revision for revision in reversed(task["revisions"])
                 if revision["answer_phase"] == "final-answer"), None)


def latest_final(task):
    revision = final_revision(task)
    return revision["after_text"] if revision else task["final_answer"]["text"]


def render_recap_pdf(columns, picture=None):
    """The recap PDF the server keeps. With `picture` (background, tasks, arrows, theme) its first page is the recap
    picture as the tablet showed it; the text pages follow unchanged, with every answer in full."""
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
        canvas.drawRightString(canvas._pagesize[0] - 48, 26, f"Pagina {doc.page}")

    pdf = BytesIO()
    if picture is None:
        SimpleDocTemplate(pdf, pagesize=A4, leftMargin=48, rightMargin=48, topMargin=40,
                          bottomMargin=48, title="SOL Search - Le tue risposte").build(
                              flow, onFirstPage=footer, onLaterPages=footer)
        return pdf.getvalue()
    wide = landscape(A4)
    picture_frame = Frame(36, 40, wide[0] - 72, wide[1] - 76, id="picture")
    text_frame = Frame(48, 48, A4[0] - 96, A4[1] - 88, id="text")
    document = BaseDocTemplate(pdf, pagesize=A4, title="SOL Search - Le tue risposte")
    document.addPageTemplates([PageTemplate("picture", [picture_frame], pagesize=wide, onPage=footer),
                               PageTemplate("text", [text_frame], pagesize=A4, onPage=footer)])
    width = min(picture_frame._width - 12, (picture_frame._height - 74) * PICTURE_RATIO)
    page_one = [Paragraph("SOL Search · Le risposte di oggi", styles["Title"]),
                RecapPicture(picture["background"], picture["tasks"], picture["arrows"], width, picture["theme"]),
                Spacer(1, 6),
                Paragraph("Le risposte complete sono nelle pagine seguenti.", styles["BodyText"]),
                NextPageTemplate("text"), PageBreak()]
    document.build(page_one + flow)
    return pdf.getvalue()


class StudentRecap:
    render_pdf = staticmethod(render_recap_pdf)

    def __init__(self, app, progress, artwork=None):
        # attempt -> (illustration, theme): the recap picture of the session, for its page in the PDF.
        self.artwork = artwork
        self.app = app
        self.progress = progress
        self.store = progress.store
        app.add_url_rule("/recap/draft", "recap_draft", self.draft, methods=["POST"])
        app.add_url_rule("/recap/save-changes", "recap_save", self.save, methods=["POST"])
        app.add_url_rule("/recap/finish", "recap_finish", self.finish, methods=["POST"])
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

    @staticmethod
    def _piece(task):
        """One question of today's session as the recap shows it. A draft left by an older recap still wins."""
        first = task["first_answer"]
        draft = task["recap_drafts"].get("final-answer")
        return {"number": task["number"], "slot": str(task["snapshot"].get("topic_id")),
                "question": task["snapshot"].get("question", ""),
                "first": "Non lo so" if first["outcome"] == "unknown" else first["text"],
                "confidence": first.get("confidence"), "final": draft["text"] if draft else latest_final(task)}

    def page(self, attempt, illustration, theme=None):
        if not self.progress.session_event(attempt, "sessionCompleted"):
            return self.progress.unavailable()
        key = self.progress.key(attempt["metadata"])
        columns = self.store.recap_columns(key, attempt["attempt_id"])
        session_number = attempt["metadata"]["study_session_snapshot"]["number"]
        tasks = [self._piece(task) for task in columns[session_number]["tasks"]]
        # The cards sit on the part of the picture that belongs to each question, so every part needs exactly one.
        if theme not in RECAP_ARROWS or sorted(task["slot"] for task in tasks) != ["1", "2", "3"]:
            theme = None
        # Saving confirms the drafts of every session it could change, as when the recap could still edit them.
        draft_revisions = {f"{column['attempt_id']}:{task['number']}": task["recap_draft_revisions"].get("final-answer", 0)
                           for column in columns.values() for task in column["tasks"]}
        return render_template("recap.html", tasks=sorted(tasks, key=lambda task: task["slot"]), theme=theme,
                               arrows=RECAP_ARROWS.get(theme, {}), confidence_labels=CONFIDENCE_LABELS,
                               background=self._background(illustration), draft_revisions=draft_revisions,
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

    def _picture(self, attempt, states):
        """The recap picture as the tablet showed it at Salva, or None when the session has no picture."""
        if self.artwork is None:
            return None
        illustration, theme = self.artwork(attempt)
        number = attempt["metadata"]["study_session_snapshot"]["number"]
        tasks = sorted((self._piece(task) for task in states.get(number, {}).get("tasks", [])),
                       key=lambda task: task["slot"])
        background = self._background(illustration)
        if (theme not in RECAP_ARROWS or [task["slot"] for task in tasks] != ["1", "2", "3"]
                or background == RECAP_PLACEHOLDER):
            return None
        return {"background": Path(self.app.static_folder) / background, "tasks": tasks,
                "arrows": RECAP_ARROWS[theme], "theme": theme}

    def pdf_with_picture(self, attempt, states):
        """The PDF Salva makes now, opening with the recap picture, or None when the session has no picture.
        For drawing again a PDF saved before the picture page existed (tools/redraw_recap_pdfs.py)."""
        picture = self._picture(attempt, states)
        return None if picture is None else self.render_pdf(states, picture)

    def _pdf_for_finish(self, states, attempt=None):
        try:
            picture = self._picture(attempt, states) if attempt is not None else None
            return self.render_pdf(states, picture) if picture is not None else self.render_pdf(states)
        except Exception as error:
            raise OSError("Could not create recap PDF") from error

    def _commit(self, finish):
        attempt, data = self._posted()
        try:
            self.store.commit_recap(self.progress.key(attempt["metadata"]), attempt["attempt_id"],
                                   data.get("draft_revisions"),
                                   (lambda states: self._pdf_for_finish(states, attempt)) if finish else None)
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

    def restart(self):
        attempt, _ = self._posted()
        if not self.store.recap_finished(attempt["attempt_id"]):
            abort(409)
        if not self.progress.publish(attempt):
            return jsonify(error=SAVE_ERROR), 503
        session.clear()
        # The group stays on the end page until a researcher resets the tablet for the next class.
        return jsonify(welcome=url_for("finished_page"))
