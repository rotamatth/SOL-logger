"""Explicit first-answer setup for tests whose subject is the subsequent search."""
from html.parser import HTMLParser


class HiddenFields(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.values = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type") == "hidden":
            self.values[attrs["name"]] = attrs.get("value", "")


def confirm_first(client, text="Synthetic first answer"):
    page = client.get("/task")
    assert page.status_code == 200
    if 'id="first-answer-form"' not in page.text:
        assert "La mia prima risposta" in page.text
        return
    data = HiddenFields(page.text).values
    assert client.post("/first-answer", data={**data, "outcome": "answered", "text": text}).status_code == 303


def final_event(client, text, **extra):
    with client.session_transaction() as state:
        return {"type": "TaskEnded", "answer": text, "attempt_id": state["progress_id"],
                "task_number": state["task_position"] + 1, "uid": state["user_id"],
                "sessionID": state["session_id"], **extra}
