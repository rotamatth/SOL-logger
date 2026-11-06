"""Server-rendered first-answer states, without importing legacy app services."""
from html.parser import HTMLParser
from pathlib import Path
import re

from flask import Flask, render_template
import pytest


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def find(self, tag, **attrs):
        return [a for t, a in self.elements if t == tag
                and all(a.get(k) == v for k, v in attrs.items())]


def render(**overrides):
    root = Path(__file__).resolve().parents[1]
    app = Flask(__name__, template_folder=str(root / "templates"),
                static_folder=str(root / "static"))
    context = dict(task_number=1, topic="Qual è stato il primo animale nello spazio?",
                   draft_text="", first_answer=None, submit_url="/first-answer",
                   search_url="/search", csrf_token="synthetic-token", error=None)
    context.update(overrides)
    with app.test_request_context():
        return render_template("first_answer.html", **context)


def test_open_field_restores_draft_without_unlocking_search():
    html = render(draft_text="Un cane di nome Laika")
    page = Page(html)
    field, = page.find("textarea", name="text")
    assert "required" in field and "readonly" not in field
    assert "Un cane di nome Laika</textarea>" in html
    assert page.find("label", **{"for": field["id"]})
    assert not page.find("a", href="/search")
    assert "disabled" in page.find("button", id="first-answer-search")[0]


def test_unknown_has_a_separate_explicit_confirmation_post_without_answer_text():
    page = Page(render())
    assert page.find("button", id="first-answer-unknown")[0]["type"] == "button"
    assert page.find("dialog", id="first-answer-unknown-dialog")
    assert len(page.find("form", method="post", action="/first-answer")) == 2
    assert page.find("input", name="outcome", value="unknown")
    assert page.find("button", name="outcome", value="answered")
    assert len(page.find("input", name="csrf_token", value="synthetic-token")) == 2
    assert not page.find("input", name="text")


@pytest.mark.parametrize("answer", [
    {"outcome": "answered", "text": "Laika", "submitted_at": "synthetic"},
    {"outcome": "unknown", "text": None, "submitted_at": "synthetic"},
])
def test_only_persisted_submission_reveals_search_and_preserves_original(answer):
    html = render(first_answer=answer, draft_text="Old draft")
    page = Page(html)
    assert page.find("a", href="/search")
    assert not page.find("form")
    assert not page.find("dialog")
    assert "Old draft" not in html
    if answer["outcome"] == "answered":
        assert "readonly" in page.find("textarea")[0]
        assert "Laika</textarea>" in html
    else:
        assert "Non lo so" in html
        assert not page.find("textarea")


def test_error_keeps_recoverable_text_and_does_not_report_success():
    html = render(error="Salvataggio non riuscito. Riprova.", draft_text="Laika")
    page = Page(html)
    assert page.find("p", role="alert")
    assert "Salvataggio non riuscito. Riprova." in html
    assert "Laika</textarea>" in html
    assert not page.find("a", href="/search")


def test_question_answer_and_error_are_escaped_without_legacy_reward_scripts():
    attack = '</textarea><script>alert("x")</script>'
    html = render(topic=attack, draft_text=attack, error=attack)
    page = Page(html)
    assert "&lt;/textarea&gt;&lt;script&gt;" in html
    assert attack not in html
    assert all(a.get("src", "").endswith("first-answer.js")
               for a in page.find("script"))
    assert "reward" not in html.lower()


@pytest.mark.parametrize("submitted", [False, True])
def test_leading_newline_survives_html_textarea_parsing(submitted):
    # HTML consumes the first LF immediately after a textarea's opening tag.
    text = "\nLaika"
    answer = {"outcome": "answered", "text": text} if submitted else None
    html = render(draft_text=text, first_answer=answer)
    assert re.search(r"<textarea\b[^>]*>\n\nLaika</textarea>", html)
