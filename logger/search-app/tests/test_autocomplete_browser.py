"""Exercise real autocomplete UI and event logging with synthetic Italian responses."""

from datetime import datetime, timedelta, timezone

import pytest

from .test_editor_browser import until
from .test_student_navigation_browser import events, student_browser  # noqa: F401 - fixture


SUGGESTIONS = ["fasi della luna", "fasi della luna oggi"]
RESPONSE = {"suggestions": SUGGESTIONS, "source": "SERP_API", "query_model": "search-history"}


def test_suggestions_show_within_half_a_second_with_a_250ms_synthetic_provider(student_browser):
    page = student_browser
    now = datetime.now(timezone.utc)
    page.clock.install(time=now)
    page.clock.pause_at(now + timedelta(seconds=5))
    page.route("**/autocomplete?**", lambda route: route.fulfill(json=RESPONSE))
    page.evaluate("""() => {
        const fetch = window.fetch;
        let providerReady;
        window.syntheticProviderReady = new Promise(resolve => { providerReady = resolve; });
        window.fetch = async (...args) => {
            const response = await fetch(...args);
            if (String(args[0]).startsWith('/autocomplete?')) {
                await new Promise(resolve => {
                    setTimeout(resolve, 250);
                    providerReady();
                });
            }
            return response;
        };
    }""")
    with page.expect_request("**/autocomplete?**", timeout=1500) as request:
        page.fill("#search-box", "fas")
        page.clock.run_for(100)
        page.fill("#search-box", "fasi")
        typed_at = page.evaluate("Date.now()")
        page.clock.run_for(220)

    assert request.value.url.endswith("?query=fasi")
    page.evaluate("window.syntheticProviderReady")
    page.clock.run_for(250)
    page.wait_for_selector("#query-suggestions li")
    assert page.evaluate("window.autocompleteContext.updatedAtMs") - typed_at <= 500


def test_clearing_during_response_parsing_discards_stale_suggestions(student_browser):
    page = student_browser
    page.route("**/autocomplete?**", lambda route: route.fulfill(json=RESPONSE))
    page.evaluate("""() => {
        const fetch = window.fetch;
        window.fetch = async (...args) => {
            const response = await fetch(...args);
            if (!String(args[0]).startsWith('/autocomplete?')) return response;
            const data = await response.json();
            response.json = () => new Promise(resolve => {
                window.releaseStaleAutocomplete = () => resolve(data);
            });
            return response;
        };
    }""")
    page.fill("#search-box", "fasi")
    page.wait_for_function("() => Boolean(window.releaseStaleAutocomplete)", timeout=3000)
    page.click("#clear-search-btn")
    page.evaluate("async () => { window.releaseStaleAutocomplete(); await Promise.resolve(); }")

    assert page.input_value("#search-box") == ""
    assert page.locator("#query-suggestions li").count() == 0
    assert page.locator("#search-box").get_attribute("aria-expanded") == "false"
    assert events(page, "autocompleteSuggestionsShown") == []
    assert events(page, "queryCleared")[-1]["query"] == "fasi"


def test_new_input_cancels_the_previous_fetch(student_browser):
    page = student_browser
    page.evaluate("""() => {
        const fetch = window.fetch;
        window.fetch = (url, options) => {
            if (!String(url).startsWith('/autocomplete?')) return fetch(url, options);
            window.startedAutocomplete = true;
            return new Promise((resolve, reject) => {
                options?.signal?.addEventListener('abort', () => {
                    window.abortedAutocomplete = true;
                    reject(options.signal.reason);
                });
            });
        };
    }""")
    page.fill("#search-box", "fasi")
    page.wait_for_function("() => window.startedAutocomplete === true", timeout=3000)
    page.fill("#search-box", "fa")

    assert page.evaluate("window.abortedAutocomplete === true")
    assert page.evaluate("window.autocompleteContext.prefix") == "fa"
    assert events(page, "autocompleteSuggestionsShown") == []


def test_editing_keeps_the_previous_list_visible_until_its_replacement_arrives(student_browser):
    page = student_browser
    held = []
    page.route("**/autocomplete?query=fasi", lambda route: route.fulfill(json=RESPONSE))
    page.route("**/autocomplete?query=sole", lambda route: held.append(route))
    page.fill("#search-box", "fasi")
    page.wait_for_selector("#query-suggestions li")
    options = page.locator("#query-suggestions li")
    page.fill("#search-box", "sole")

    try:
        assert until(page, lambda: held)
        assert options.all_text_contents() == SUGGESTIONS
        assert options.first.is_visible()
        assert page.locator("#query-suggestions").get_attribute("aria-busy") == "true"
        assert options.first.get_attribute("aria-disabled") == "true"
        assert page.locator("#search-box").get_attribute("aria-expanded") == "true"
        context = page.evaluate("window.autocompleteContext")
        assert (context["prefix"], context["suggestions"], context["source"], context["queryModel"]) == (
            "sole", [], "none", None
        )

        page.press("#search-box", "ArrowDown")
        assert options.first.get_attribute("aria-selected") == "false"
        options.first.hover()
        options.first.click(force=True)
        assert page.input_value("#search-box") == "sole"
        assert events(page, "hoverOverQuerySuggestions") == []
        assert events(page, "choseAutoCompleteSuggestion") == []
    finally:
        if held:
            held[0].fulfill(json={"suggestions": ["sole oggi"], "source": "vertex"})

    page.wait_for_selector('#query-suggestions li:text-is("sole oggi")')
    assert options.all_text_contents() == ["sole oggi"]
    assert page.locator("#query-suggestions").get_attribute("aria-busy") is None
    assert events(page, "autocompleteSuggestionsShown")[-1]["source"] == "vertex"

    page.fill("#search-box", "so")
    assert options.count() == 0
    assert page.locator("#search-box").get_attribute("aria-expanded") == "false"


def test_failed_suggestion_render_leaves_no_selection_metadata(student_browser):
    page = student_browser
    page.route("**/autocomplete?**", lambda route: route.fulfill(json=RESPONSE))
    page.evaluate("""() => {
        const logEvent = studyLogger.logEvent.bind(studyLogger);
        studyLogger.logEvent = (type, details) => {
            if (type === 'autocompleteSuggestionsShown') throw new Error('Synthetic storage error');
            logEvent(type, details);
        };
    }""")
    with page.expect_console_message(predicate=lambda message: "Synthetic storage error" in message.text):
        page.fill("#search-box", "fasi")

    assert page.evaluate("window.autocompleteContext.suggestions") == []
    assert page.locator("#search-box").get_attribute("aria-expanded") == "false"


@pytest.mark.parametrize("selection", ["click", "keyboard"])
def test_suggestion_selection_preserves_search_and_event_context(student_browser, selection):
    page = student_browser
    page.route("**/autocomplete?**", lambda route: route.fulfill(json=RESPONSE))
    page.fill("#search-box", "fasi")
    page.wait_for_selector("#query-suggestions li")

    if selection == "keyboard":
        page.press("#search-box", "ArrowDown")
        page.press("#search-box", "Enter")
    else:
        page.locator("#query-suggestions li").first.click()

    page.wait_for_selector('article[data-raw-query="fasi della luna"]')
    shown = events(page, "autocompleteSuggestionsShown")[-1]
    assert (shown["query"], shown["suggestions"], shown["source"], shown["queryModel"]) == (
        "fasi", SUGGESTIONS, "SERP_API", "search-history"
    )
    assert len(events(page, "choseAutoCompleteSuggestion")) == 1
    for event in (events(page, "choseAutoCompleteSuggestion")[-1], events(page, "querySubmitted")[-1]):
        assert event["autocompletePrefix"] == "fasi"
        assert event["autocompleteSource"] == "SERP_API"
        assert event["autocompleteQueryModel"] == "search-history"
        assert event["autocompleteSelectedSuggestion"] == "fasi della luna"
