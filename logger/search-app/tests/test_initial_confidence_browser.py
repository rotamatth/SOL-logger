"""The child's assessment follows typing, recovery and confirmation in the real app."""
import pytest

from .test_background_upload_browser import student_site, saved, types_of  # noqa: F401
from .test_first_answer_flow_browser import open_first


def test_confidence_appears_immediately_resets_on_blank_and_is_required(student_site):
    page, base, root = student_site
    open_first(page, base)
    assessment = page.get_by_role("group", name="Secondo te, quanto è giusta la tua risposta?")
    assert assessment.is_hidden()
    page.fill("#first-answer-text", "L")
    assert assessment.is_visible()
    page.get_by_role("button", name="Conferma risposta", exact=True).click()
    assert page.locator("button#first-answer-search").is_disabled()
    page.get_by_role("radio", name="Giustissima", exact=True).check()
    page.fill("#first-answer-text", " \n ")
    assert assessment.is_hidden()
    assert page.locator('input[name="confidence"]:checked').count() == 0
    page.fill("#first-answer-text", "Laika")
    assert assessment.is_visible()
    assert page.locator('input[name="confidence"]:checked').count() == 0
    page.get_by_role("radio", name="Poco giusta", exact=True).check()
    page.get_by_role("button", name="Conferma risposta", exact=True).click()
    page.locator("a#first-answer-search").wait_for()
    submissions = types_of(saved(root, "1"), "OwnKnowledgeAnswerSubmitted")
    assert len(submissions) == 1 and submissions[0]["confidence"] == 1


def test_confidence_draft_resumes_in_fresh_browser_and_unknown_needs_no_assessment(student_site):
    page, base, root = student_site
    open_first(page, base)
    page.fill("#first-answer-text", "Laika")
    page.get_by_role("radio", name="Abbastanza giusta", exact=True).check()
    page.get_by_text("Bozza salvata.", exact=True).wait_for()
    other = page.context.browser.new_context()
    try:
        resumed = other.new_page()
        open_first(resumed, base)
        assert resumed.locator("#first-answer-text").input_value() == "Laika"
        assert resumed.get_by_role("radio", name="Abbastanza giusta", exact=True).is_checked()
        assert resumed.locator("button#first-answer-search").is_disabled()
        resumed.get_by_role("button", name="Non lo so", exact=True).click()
        resumed.get_by_role("button", name="Torna alla risposta").click()
        assert resumed.get_by_role("radio", name="Abbastanza giusta", exact=True).is_checked()
        resumed.get_by_role("button", name="Non lo so", exact=True).click()
        resumed.get_by_role("button", name="Confermo: non lo so").click()
        resumed.locator("a#first-answer-search").wait_for()
        submissions = types_of(saved(root, "1"), "OwnKnowledgeAnswerSubmitted")
        assert len(submissions) == 1 and submissions[0]["outcome"] == "unknown"
        assert submissions[0]["confidence"] is None
    finally:
        other.close()


def test_failed_autosave_recovers_confidence_with_text_after_reload(student_site):
    page, base, _ = student_site
    open_first(page, base)
    page.route("**/first-answer/draft", lambda route: route.abort())
    page.fill("#first-answer-text", "Recuperami")
    page.get_by_role("radio", name="Giustissima", exact=True).check()
    page.locator("#first-answer-retry-draft:not([hidden])").wait_for()
    page.reload()
    page.wait_for_function("document.getElementById('first-answer-text').value === 'Recuperami'")
    assert page.get_by_role("radio", name="Giustissima", exact=True).is_checked()
    page.locator("#first-answer-retry-draft:not([hidden])").wait_for()
    page.unroute("**/first-answer/draft")
    page.get_by_role("button", name="Riprova salvataggio").click()
    page.get_by_text("Bozza salvata.", exact=True).wait_for()
    page.reload()
    assert page.get_by_role("radio", name="Giustissima", exact=True).is_checked()


@pytest.mark.parametrize("width,height", [(1440, 960), (768, 1024), (1024, 768), (320, 700)])
def test_confidence_options_fit_and_use_local_design_stars(student_site, width, height):
    page, base, _ = student_site
    page.set_viewport_size({"width": width, "height": height})
    open_first(page, base)
    page.fill("#first-answer-text", "Una risposta")
    page.get_by_role("radio", name="Abbastanza giusta", exact=True).check()
    assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
    for name in ["Poco giusta", "Abbastanza giusta", "Giustissima"]:
        assert page.get_by_role("radio", name=name, exact=True).is_visible()
    page.wait_for_function("Array.from(document.querySelectorAll('.first-answer-confidence img')).every(img => img.complete && img.naturalWidth > 0)")
    assert page.locator(".first-answer-confidence img").count() == 12
    assert page.locator(".first-answer-confidence label:has(input:checked)").evaluate(
        "el => getComputedStyle(el).backgroundColor") == "rgb(255, 179, 71)"
