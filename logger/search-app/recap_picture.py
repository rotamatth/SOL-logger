"""The recap picture drawn into the recap PDF: the theme's drawing with today's answers on it.

It repeats what the tablet shows (recap.html, recap.css, student_recap.RECAP_ARROWS): the same drawing, the
"Domanda N" labels, the first answers in a row under the labels and the final answers along the bottom, and
the dashed arrows through the magnifiers. Positions are shares of the picture, taken from recap.css, so the
PDF and the tablet stay alike. A card holds what fits; the full answers are on the PDF's text pages.

ReportLab draws it directly: no browser runs on the server, and nothing is taken from the tablet.
"""
import re

from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable

STAGE = (1000, 667)                      # The arrows' coordinates (RECAP_ARROWS).
PICTURE_RATIO = 1600 / 1067              # The drawings' proportions.
# recap.css: where each label and card sits, by the question's part of the picture, as shares of the picture.
LABEL_LEFT = {"1": 0.02, "2": 0.357, "3": 0.694}
LABEL_TOP = 0.018
BEFORE_LEFT = {"1": 0.014, "2": 0.312, "3": 0.609}
AFTER_LEFT = {"1": 0.062, "2": 0.396, "3": 0.73}
BEFORE_TOP = 0.094
AFTER_BOTTOM = 0.066
CARD_WIDTH = 0.248
CARD_MIN_HEIGHT = 0.194
CARD_MAX_HEIGHT = {"before": 0.28, "after": 0.29}

BLUE = colors.HexColor("#4285f4")
BLUE_DARK = colors.HexColor("#1a4fa3")
YELLOW = colors.HexColor("#fbbc05")
BROWN = colors.HexColor("#8a5a12")
STAR = colors.HexColor("#f6a623")
FONT, BOLD = "Helvetica", "Helvetica-Bold"


def printable(text):
    """What the PDF's standard fonts can show: an emoji or another script is left out of the card, not the text page."""
    return "".join(char for char in (text or "") if char in "\n\t" or char.encode("cp1252", "ignore")).strip()


def wrap(text, font, size, width):
    """Lines of at most `width` points, breaking at spaces and inside a word that is too long by itself."""
    lines = []
    for paragraph in printable(text).splitlines() or [""]:
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}".strip()
            if stringWidth(candidate, font, size) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
            while stringWidth(word, font, size) > width:
                cut = max(1, next((n for n in range(len(word), 0, -1) if stringWidth(word[:n], font, size) <= width), 1))
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        lines.append(line)
    return lines


def fit(lines, room, font, size, width):
    """The lines that fit in `room` lines, the last one ending with "…" when some were left out."""
    if len(lines) <= room:
        return lines, False
    kept = lines[:room]
    last = kept[-1]
    while last and stringWidth(last + " …", font, size) > width:
        last = last[:-1]
    kept[-1] = (last.rstrip() + " …").strip()
    return kept, True


def _quadratic_points(path):
    """The points of an arrow's "M x y Q cx cy x y Q ..." line, as (start, [(control, end), ...])."""
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", path)]
    start, rest = (numbers[0], numbers[1]), numbers[2:]
    return start, [((rest[i], rest[i + 1]), (rest[i + 2], rest[i + 3])) for i in range(0, len(rest), 4)]


class RecapPicture(Flowable):
    """The recap picture as one flowable of the given width."""

    def __init__(self, background, tasks, arrows, width):
        super().__init__()
        self.background, self.tasks, self.arrows = background, tasks, arrows
        self.width, self.height = width, width / PICTURE_RATIO
        self.hAlign = "CENTER"
        self.truncated = []

    def wrap(self, available_width, available_height):
        return self.width, self.height

    # Positions: shares of the picture, from its top-left corner like the CSS, to the PDF's bottom-left origin.
    def _x(self, share):
        return share * self.width

    def _y(self, share_from_top):
        return self.height - share_from_top * self.height

    def _stage(self, x, y):
        return x / STAGE[0] * self.width, self.height - y / STAGE[1] * self.height

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        canvas.drawImage(ImageReader(str(self.background)), 0, 0, self.width, self.height)
        canvas.setStrokeColor(colors.black)
        canvas.setLineWidth(1.5)
        canvas.roundRect(0, 0, self.width, self.height, 3, stroke=1, fill=0)
        for task in self.tasks:
            self._arrow(canvas, self.arrows[task["slot"]])
        for task in self.tasks:
            self._label(canvas, task)
            self._card(canvas, task, "before")
            self._card(canvas, task, "after")
        canvas.restoreState()

    def _arrow(self, canvas, arrow):
        scale = self.width / STAGE[0]
        start, curves = _quadratic_points(arrow["line"])
        # A white halo under a dashed black line, so the arrow shows on dark and light parts of the drawing.
        for color, width, dash in ((colors.white, 4.5 * scale, []), (colors.black, 1.6 * scale, [4 * scale, 4 * scale])):
            canvas.setStrokeColor(color)
            canvas.setLineWidth(width)
            canvas.setDash(dash, 0)
            path = canvas.beginPath()
            x0, y0 = self._stage(*start)
            path.moveTo(x0, y0)
            current = start
            for control, end in curves:
                # A quadratic curve as the cubic ReportLab draws.
                c1 = (current[0] + 2 / 3 * (control[0] - current[0]), current[1] + 2 / 3 * (control[1] - current[1]))
                c2 = (end[0] + 2 / 3 * (control[0] - end[0]), end[1] + 2 / 3 * (control[1] - end[1]))
                path.curveTo(*self._stage(*c1), *self._stage(*c2), *self._stage(*end))
                current = end
            canvas.drawPath(path, stroke=1, fill=0)
            canvas.setDash([], 0)
            tip = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", arrow["tip"])]
            path = canvas.beginPath()
            path.moveTo(*self._stage(tip[0], tip[1]))
            path.lineTo(*self._stage(tip[2], tip[3]))
            path.lineTo(*self._stage(tip[4], tip[5]))
            canvas.drawPath(path, stroke=1, fill=0)
        x, y = self._stage(arrow["x"], arrow["y"])
        canvas.setFillColor(BLUE)
        canvas.circle(x, y, 17 * scale, stroke=0, fill=1)
        canvas.setStrokeColor(colors.white)
        canvas.setLineWidth(3 * scale)
        canvas.circle(x - 2.5 * scale, y + 2.5 * scale, 7 * scale, stroke=1, fill=0)
        canvas.line(x + 3 * scale, y - 3 * scale, x + 10 * scale, y - 10 * scale)

    def _label(self, canvas, task):
        size = self.width * 0.0135
        text = f"Domanda {task['number']}"
        width = stringWidth(text, BOLD, size) + size * 1.9
        height = size * 1.55
        x, top = self._x(LABEL_LEFT[task["slot"]]), self._y(LABEL_TOP)
        canvas.setFillColor(YELLOW)
        canvas.setStrokeColor(BROWN)
        canvas.setLineWidth(1.2)
        canvas.roundRect(x, top - height, width, height, height / 2, stroke=1, fill=1)
        canvas.setFillColor(colors.black)
        canvas.setFont(BOLD, size)
        canvas.drawString(x + size * 0.95, top - height + size * 0.42, text)

    def _card(self, canvas, task, kind):
        size = self.width * 0.0118
        leading = size * 1.3
        pad = size * 0.7
        width = self._x(CARD_WIDTH)
        inner = width - 2 * pad
        title = "Cosa sapevi prima" if kind == "before" else "Cosa sai adesso"
        text = task["first"] if kind == "before" else task["final"]
        room = int((CARD_MAX_HEIGHT[kind] * self.height - 2 * pad - leading * 1.2) // leading)
        lines, cut = fit(wrap(text, FONT, size, inner), max(1, room), FONT, size, inner)
        if cut:
            self.truncated.append((task["number"], kind))
        height = max(CARD_MIN_HEIGHT * self.height, 2 * pad + leading * (1.2 + len(lines)))
        if kind == "before":
            x, top = self._x(BEFORE_LEFT[task["slot"]]), self._y(BEFORE_TOP)
        else:
            x, top = self._x(AFTER_LEFT[task["slot"]]), AFTER_BOTTOM * self.height + height
        canvas.setFillColor(colors.white if kind == "before" else BLUE)
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(1.1)
        canvas.roundRect(x, top - height, width, height, 6, stroke=1, fill=1)
        canvas.setFillColor(BLUE_DARK if kind == "before" else colors.white)
        canvas.setFont(BOLD, size)
        canvas.drawString(x + pad, top - pad - size, title)
        canvas.setFillColor(colors.black if kind == "before" else colors.white)
        canvas.setFont(FONT, size)
        for number, line in enumerate(lines):
            canvas.drawString(x + pad, top - pad - size - leading * (1.2 + number), line)
        if kind == "before" and task.get("confidence") in (1, 2, 3):
            self._stars(canvas, x + width - size * 0.7, top, task["confidence"], size)

    def _stars(self, canvas, right, top, count, size):
        """The child's own rating on the card's top edge, as on the tablet."""
        star = size * 0.95
        gap = star * 0.2
        width = count * star + (count - 1) * gap + star * 0.6
        height = star * 1.3
        left = right - width
        canvas.setFillColor(colors.white)
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(1)
        canvas.roundRect(left, top - height / 2, width, height, height / 2, stroke=1, fill=1)
        canvas.setFillColor(STAR)
        for index in range(count):
            cx = left + star * 0.3 + star / 2 + index * (star + gap)
            self._star(canvas, cx, top, star / 2)

    @staticmethod
    def _star(canvas, cx, cy, radius):
        from math import cos, pi, sin
        path = canvas.beginPath()
        for point in range(10):
            r = radius if point % 2 == 0 else radius * 0.45
            angle = pi / 2 + point * pi / 5
            x, y = cx + r * cos(angle), cy + r * sin(angle)
            if point == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.close()
        canvas.drawPath(path, stroke=0, fill=1)
