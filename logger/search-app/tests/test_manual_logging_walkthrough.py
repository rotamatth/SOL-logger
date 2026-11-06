"""
Contract tests for the manual logging walkthrough.

The walkthrough is intentionally human-run, but the event inventory should not
drift away from the event names emitted by the app.
"""

import re
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
REPO_LOGGER_ROOT = APP_ROOT.parent
WALKTHROUGH = REPO_LOGGER_ROOT / "docs" / "manual_logging_walkthrough.md"

SOURCE_FILES = [
    APP_ROOT / "static" / "logger.js",
    APP_ROOT / "templates" / "layout.html",
    APP_ROOT / "templates" / "webpage.html",
    APP_ROOT / "templates" / "error.html",
    APP_ROOT / "templates" / "end.html",
]

DYNAMIC_LOG_EVENTS = {
    # webpage.html computes this event name before calling logEvent(evt, ...).
    "webpageLoadSucceeded",
    "webpageLoadFailed",
    "webpageLoadCheckUnknown",
}

SERVER_LOG_EVENTS = {
    "OwnKnowledgeAnswerSubmitted", "TaskStarted", "TaskEnded", "sessionCompleted", "experimentFinished",
    "RecapAnswerEdited", "studySessionFinished",
}

# Frozen pre-migration non-reward inventory: editing the walkthrough cannot
# accidentally authorize dropping an existing event family.
NON_REWARD_EVENTS = set("""
autocompleteSuggestionsShown AnswerBoxClosed ClickedEndTaskConfirmation
ClickedOnSendAndTerminateTask EndTaskConfirmationClosed EndTaskDialogClosed
OpenedAnswerBox TaskContinued TaskEnded TaskStarted browserBackBlocked
choseAutoCompleteSuggestion clickedDidYouMeanSuggestion clickedResult
cursorEnteredSnippet cursorLeftSnippet customBackButtonClicked experimentFinished
firstAnswerClosed firstAnswerOpened generatedDidYouMean hoverOverDidYouMean
hoverOverQuerySuggestions idSubmitted iframeBackNavigation iframeNavigation
iframeNavigationTrackingLimited logoOnSerpClicked pageNavigationClicked
queryBoxFocused queryCleared querySubmitted resourceViewEnded resourceViewStarted
resultExposureEnded resultExposureStarted searchError searchNoResults
searchResultGenerated sessionCompleted taskQuestionHelpClicked taskQuestionHelpClosed
webpageClosed webpageLoadCheckUnknown webpageLoadFailed webpageLoadSucceeded webpageOpened
""".split())

LOG_EVENT_RE = re.compile(r"studyLogger\.logEvent\(\s*[\"']([^\"']+)[\"']")
INVENTORY_RE = re.compile(
    r"<!-- event-inventory:start -->(.*?)<!-- event-inventory:end -->",
    re.DOTALL,
)
MARKDOWN_EVENT_RE = re.compile(r"^- `([^`]+)`$", re.MULTILINE)


def app_event_types():
    events = set()
    for path in SOURCE_FILES:
        events.update(LOG_EVENT_RE.findall(path.read_text(encoding="utf-8")))
    events.update(DYNAMIC_LOG_EVENTS)
    events.update(SERVER_LOG_EVENTS)
    return events


def walkthrough_event_types():
    source = WALKTHROUGH.read_text(encoding="utf-8")
    match = INVENTORY_RE.search(source)
    assert match, "manual walkthrough is missing event inventory markers"
    return set(MARKDOWN_EVENT_RE.findall(match.group(1)))


def test_manual_walkthrough_lists_every_app_log_event_type():
    assert walkthrough_event_types() == app_event_types()


def test_all_existing_non_reward_event_families_survive_the_new_flow():
    emitted = app_event_types()
    assert NON_REWARD_EVENTS <= emitted
    assert not emitted & {"rewardShown", "finalRewardRevealClicked", "finalRewardRevealCompleted"}


def test_manual_walkthrough_has_operational_steps():
    source = WALKTHROUGH.read_text(encoding="utf-8")

    required_sections = [
        "## Setup",
        "### 1. Start a session",
        "### 2. Exercise search input logging",
        "### 3. Exercise normal SERP logging",
        "### 4. Exercise pagination and SERP return logging",
        "### 5. Exercise did-you-mean and no-result logging",
        "### 6. Exercise resource page logging",
        "### 7. Exercise iframe navigation logging",
        "### 8. Exercise answer modal and task-end logging",
        "### 9. Exercise completion logging",
        "### 10. Exercise search error logging",
        "## Final checks",
    ]

    for section in required_sections:
        assert section in source
