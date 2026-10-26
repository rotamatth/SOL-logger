"""In a real browser: recovered text of a reused set keeps its conditions after a conflict."""
from itsdangerous import URLSafeSerializer

from .test_editor_browser import EDITOR, live, until  # noqa: F401 - pytest fixture
from .test_research_dashboard import app  # noqa: F401 - pytest fixture


def test_using_recovered_text_after_a_conflict_keeps_the_reused_sets_conditions(live):
    page = live.login()
    page.goto(live.base + EDITOR)
    library_set = page.evaluate("document.querySelector('#library-set option[value]:not([value=\"\"])').value")
    page.evaluate("""value => {
        document.querySelector('#library-set').value = value;
        const form = document.querySelector('form.question-editor');
        form.requestSubmit(form.querySelector('button[value=load_set]'));
    }""", library_set)
    page.wait_for_selector("form.question-editor[data-unsaved]")
    token = page.input_value("[name=draft_token]")
    signer = URLSafeSerializer(live.app.config["RESEARCH_PASSWORD_HASH"], salt="sol-question-draft")
    loaded = signer.loads(token)["question_set"]
    assert until(page, lambda: live.server_copy().get("draft_token") == token)

    # Another tab saves something unrelated, so approving this page is refused.
    state = live.app.extensions["research"]["state"]
    settings = state.settings()
    next(s for s in settings["sessions"] if s["id"] == "grade-5-session-1")["name"] = "Unrelated change"
    state.save_settings(settings, settings["revision"])
    page.click("button[value=approve_questions]")
    page.wait_for_selector("text=changed in another tab or by another researcher")
    page.click("text=Reload saved settings")
    page.wait_for_selector(".recovery-banner")
    page.click(".recovery-banner >> text=Use this text with the current version")
    assert page.input_value("[name=question_0]") == loaded["questions"][0]["question"]
    page.click("button[value=approve_questions]")
    page.wait_for_url("**saved=1**")

    approved = next(s for s in state.settings()["sessions"] if s["id"] == "grade-4-session-1")["question_set"]
    assert approved["metadata"] == loaded["metadata"]
    assert [q["id"] for q in approved["questions"]] == [q["id"] for q in loaded["questions"]]
    assert [q["metadata"] for q in approved["questions"]] == [q["metadata"] for q in loaded["questions"]]
