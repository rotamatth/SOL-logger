"""The recap PDF opens with the recap picture as the tablet showed it; the text pages follow unchanged."""
import re
from pathlib import Path

import pytest

import recap_picture
from recap_picture import RecapPicture, fit, printable, wrap
from student_recap import RECAP_ARROWS, render_recap_pdf
from .test_connected_first_answer import begin
from .test_editable_recap import complete_today, draft_revisions
from .test_study_enrollment import question_set, schedule, student_modules  # noqa: F401

APP_ROOT = Path(__file__).resolve().parents[1]
LANDSCAPE = rb"/MediaBox \[ 0 0 841.8898 595.2756 \]"
PORTRAIT = rb"/MediaBox \[ 0 0 595.2756 841.8898 \]"


def pages(pdf):
    return len(re.findall(rb"/Type /Page\b(?!s)", pdf))


def task(number, slot, first="Prima", final="Dopo", confidence=2):
    return {"number": number, "slot": slot, "question": f"Domanda {slot}?", "first": first,
            "confidence": confidence, "final": final}


def columns():
    return {1: {"tasks": [{"number": n, "snapshot": {"topic_id": str(n), "question": f"Domanda {n}?"},
                           "first_answer": {"text": "Prima", "outcome": "answered", "confidence": 2},
                           "recap_drafts": {}, "revisions": [], "final_answer": {"text": f"Dopo {n}"}}
                          for n in (1, 2, 3)]}}


@pytest.mark.parametrize(("theme", "image"), [("space", "space-recap.webp"), ("ear", "ear-recap.webp")])
def test_the_picture_is_a_landscape_first_page_before_the_text(theme, image):
    picture = {"background": APP_ROOT / "static/images/review" / image,
               "tasks": [task(2, "1"), task(3, "2"), task(1, "3")], "arrows": RECAP_ARROWS[theme]}
    pdf = render_recap_pdf(columns(), picture)
    assert pdf.startswith(b"%PDF-") and pages(pdf) == 2
    assert len(re.findall(LANDSCAPE, pdf)) == 1 and len(re.findall(PORTRAIT, pdf)) == 1
    assert b"/Subtype /Image" in pdf


def test_without_a_picture_the_pdf_is_the_text_as_before():
    pdf = render_recap_pdf(columns())
    assert pages(pdf) == 1 and not re.search(LANDSCAPE, pdf) and b"/Subtype /Image" not in pdf


def test_a_card_keeps_what_fits_and_says_when_it_left_some_out():
    lines = wrap("una parola " * 80, "Helvetica", 9, 150)
    kept, cut = fit(lines, 4, "Helvetica", 9, 150)
    assert len(kept) == 4 and cut and kept[-1].endswith("…")
    assert fit(["breve"], 4, "Helvetica", 9, 150) == (["breve"], False)


def test_a_word_longer_than_the_card_is_broken_not_lost():
    lines = wrap("supercalifragilistichespiralidoso" * 3, "Helvetica", 9, 60)
    assert "".join(lines) == "supercalifragilistichespiralidoso" * 3 and len(lines) > 1


def test_what_the_pdf_fonts_cannot_show_is_left_out_of_the_card():
    assert printable("Laika 🚀 città") == "Laika  città"


def test_a_long_answer_is_cut_on_the_picture_and_noted():
    picture = RecapPicture(APP_ROOT / "static/images/review/space-recap.webp",
                           [task(1, "1", final="lunga " * 200), task(2, "2"), task(3, "3")], RECAP_ARROWS["space"], 700)
    from io import BytesIO
    from reportlab.pdfgen.canvas import Canvas
    picture.canv = Canvas(BytesIO())
    picture.draw()
    assert picture.truncated == [(1, "after")]


def test_the_pdf_places_cards_and_labels_where_the_tablet_does():
    """recap.css and recap_picture.py must agree: a change to one needs the same change to the other."""
    css = (APP_ROOT / "static/recap.css").read_text()

    def left(kind, slot):
        found = re.search(rf"\.recap-piece--space-{slot} \.{kind}[^{{]*\{{ left: ([\d.]+)%; \}}", css)
        return float(found[1]) / 100

    for slot in ("1", "2", "3"):
        assert left("review-number", slot) == pytest.approx(recap_picture.LABEL_LEFT[slot])
        assert left("review-before", slot) == pytest.approx(recap_picture.BEFORE_LEFT[slot])
        assert left("review-after", slot) == pytest.approx(recap_picture.AFTER_LEFT[slot])
    assert "width: 24.8%;" in css and recap_picture.CARD_WIDTH == 0.248
    assert "min-height: 19.4%;" in css and recap_picture.CARD_MIN_HEIGHT == 0.194
    assert "bottom: 6.6%;" in css and recap_picture.AFTER_BOTTOM == 0.066
    assert "max(9.4%," in css and recap_picture.BEFORE_TOP == 0.094
    assert "top: 1.8%;" in css and recap_picture.LABEL_TOP == 0.018


def finish(student_modules, theme):
    module = student_modules()
    schedule(module, {**question_set(), "theme": theme})
    client = begin(module)
    auth = complete_today(client)
    assert client.get("/thank_you").status_code == 200
    assert client.post("/recap/finish", json={**auth, "draft_revisions": draft_revisions(client)}).status_code == 200
    return module.PROGRESS.store.recap_pdf(auth["attempt_id"])


@pytest.mark.parametrize("theme", ["spazio", "orecchio"])
def test_salva_keeps_a_pdf_with_the_picture_of_the_session(student_modules, theme):
    pdf = finish(student_modules, theme)
    assert pages(pdf) == 2 and re.search(LANDSCAPE, pdf) and b"/Subtype /Image" in pdf


def test_a_session_without_a_picture_keeps_the_text_pdf(student_modules):
    pdf = finish(student_modules, "Another theme")
    assert pages(pdf) == 1 and not re.search(LANDSCAPE, pdf)


def test_the_server_image_contains_the_picture_module():
    assert re.search(r"^COPY .*\brecap_picture\.py\b", (APP_ROOT / "Dockerfile").read_text(), re.M)
