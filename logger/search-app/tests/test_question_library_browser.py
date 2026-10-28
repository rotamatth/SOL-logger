"""Search and explicit reuse work against a synthetic library in real Chromium."""
import pytest

from .test_editor_browser import app, live, until  # noqa: F401 - pytest fixtures
from .test_session_question_editor import URL
from research_dashboard.study_config import question_library


def library(app):
    topics = {f"{number}_{field}": value for number in range(1, 4)
              for field, value in (("short", f"Library topic {number}"),
                                   ("full", f"Readable library question {number}?"))}
    app.config.update(STUDENT_TOPICS={"1": topics, "2": topics},
                      STUDENT_TOPIC_METADATA={
                          "1": {"experimental_condition": "compare sources", "high_interest_topic_column": "first"},
                          "2": {"experimental_condition": "compare sources", "high_interest_topic_column": "second"}})
    return question_library(app)


@pytest.mark.parametrize("language", ["en", "it"])
def test_search_previews_variants_and_requires_an_explicit_apply(live, language):
    choices = library(live.app)
    state = live.app.extensions["research"]["state"]
    revision = state.settings()["revision"]
    page = live.login()
    page.set_viewport_size({"width": 390, "height": 844})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(live.base + URL + "?lang=" + language)
    page.fill("[name=question_0]", "Text already in this editor")
    browser = page.locator('[data-library-kind="sets"]')
    browser.locator("summary").first.click()
    browser.locator("[data-library-search]").fill("second compare sources")
    assert browser.locator(".library-card").count() == 1
    assert "Library topic 3" in browser.locator(".library-results").inner_text()
    expected = next(entry for entry in choices
                    if entry["question_set"]["metadata"]["high_interest_topic_column"] == "second")
    browser.locator("[data-library-choice]").click()
    assert page.input_value("#library-set") == expected["id"]
    assert page.input_value("[name=question_0]") == "Text already in this editor"
    assert state.settings()["revision"] == revision
    assert browser.locator(".library-selected").is_visible()
    assert "Readable library question 3?" in browser.locator(".library-selected").inner_text()
    with page.expect_navigation():
        page.click("button[value=load_set]")
    assert page.input_value("[name=question_0]") == "Readable library question 1?"
    assert state.settings()["revision"] == revision  # Applying is still only a preview.
    with page.expect_navigation():
        page.click("button[value=save_draft]")
    saved = state.settings()["sessions"][0]["question_draft"]
    assert saved["metadata"]["high_interest_topic_column"] == "second"
    assert saved["questions"][1]["metadata"]["high_interest"] is True
    assert saved["approved"] is False
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert errors == []


def test_individual_search_discloses_sources_keeps_other_slots_and_has_empty_feedback(live):
    library(live.app)
    page = live.login()
    page.goto(live.base + URL + "?lang=en")
    page.fill("[name=question_0]", "Unselected first slot")
    page.fill("[name=question_2]", "Unselected third slot")
    browser = page.locator('[data-library-kind="questions"]').nth(1)
    browser.locator("summary").first.click()
    browser.locator("[data-library-search]").fill("no matching synthetic words")
    assert browser.locator(".library-empty").inner_text() == "No matching questions or sets."
    browser.locator("[data-library-search]").fill("Readable library question 2")
    assert browser.locator(".library-card").count() == 1
    assert "Several source conditions" in browser.inner_text()
    browser.locator(".library-card > .library-card-content > details > summary").click()
    assert "high_interest_topic_column=first" in browser.inner_text()
    assert "high_interest_topic_column=second" in browser.inner_text()
    browser.locator("[data-library-choice]").focus()
    page.keyboard.press("Enter")
    assert page.input_value("[name=question_1]") == ""
    assert browser.locator("[data-library-choice]").get_attribute("aria-pressed") == "true"
    with page.expect_navigation():
        page.click("button[value=load_questions]")
    assert page.input_value("[name=question_0]") == "Unselected first slot"
    assert page.input_value("[name=question_1]") == "Readable library question 2?"
    assert page.input_value("[name=question_2]") == "Unselected third slot"


def test_native_select_and_server_apply_remain_available_without_javascript(live):
    choices = library(live.app)
    context = live.context.browser.new_context(java_script_enabled=False)
    try:
        page = context.new_page()
        # Sign in through the standard native form, including its CSRF token.
        from .test_research_dashboard import PASSWORD
        page.goto(live.base + "/dashboard/login?lang=en")
        page.fill("input[type=password]", PASSWORD)
        page.keyboard.press("Enter")
        page.wait_for_url(lambda url: "login" not in url)
        page.goto(live.base + URL + "?lang=en")
        page.locator('[data-library-kind="sets"] > summary').click()
        page.select_option("#library-set", choices[0]["id"])
        with page.expect_navigation():
            page.click("button[value=load_set]")
        assert page.input_value("[name=question_0]") == "Readable library question 1?"
        assert page.locator(".library-browser").count() == 0
    finally:
        context.close()


def test_library_previews_render_source_text_as_text(live):
    library(live.app)
    live.app.config["STUDENT_TOPICS"]["1"]["1_full"] = '<img src=x onerror="window.syntheticInjection=true">'
    page = live.login()
    page.goto(live.base + URL + "?lang=en")
    browser = page.locator('[data-library-kind="sets"]')
    browser.locator("summary").first.click()
    browser.locator("[data-library-search]").fill("syntheticInjection")
    assert browser.locator(".library-card").count() == 2  # Both synthetic entries share the source dict.
    browser.locator("[data-library-choice]").first.click()
    assert '<img src=x onerror="window.syntheticInjection=true">' in browser.inner_text()
    assert browser.locator("img").count() == 0
    assert page.evaluate("window.syntheticInjection === undefined")


def test_large_library_is_rendered_on_demand_and_searches_beyond_the_visible_batch(live):
    live.app.config.update(STUDENT_TOPIC_METADATA={}, STUDENT_TOPICS={
        str(index): {f"{number}_{field}": value for number in range(1, 4)
                     for field, value in (("short", f"Synthetic set {index} topic {number}"),
                                          ("full", f"Needle question {index} slot {number}?"))}
        for index in range(1, 66)})
    page = live.login()
    page.goto(live.base + URL + "?lang=en")
    assert page.locator(".library-card").count() == 0
    browser = page.locator('[data-library-kind="sets"]')
    browser.locator("summary").first.click()
    assert until(page, lambda: browser.locator(".library-card").count() == 20)
    assert "65 / 65" in browser.locator("[role=status]").inner_text()
    browser.locator("[data-library-more]").click()
    assert browser.locator(".library-card").count() == 40
    browser.locator("[data-library-search]").fill("Needle question 65")
    assert browser.locator(".library-card").count() == 1
    assert browser.locator("[data-library-more]").is_hidden()
    browser.locator("[data-library-choice]").click()
    assert "Needle question 65 slot 3?" in browser.locator(".library-selected").inner_text()
    assert page.input_value("[name=question_0]") == ""
