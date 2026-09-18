# Manual Logging Walkthrough

This file documents the current SOL logging event types and gives a short
manual walkthrough for checking that each event family is still emitted in the
expected user flow.

## Event catalogue

### Session and task flow

- `idSubmitted`: emitted when the participant ID form is submitted.
- `TaskStarted`: emitted when the task start button is clicked.
- `ClickedOnSendAndTerminateTask`: emitted when the answer box is opened from the task button.
- `OpenedAnswerBox`: emitted whenever the answer modal is shown.
- `AnswerBoxClosed`: emitted when the answer modal is closed with the x button or by continuing search.
- `EndTaskDialogClosed`: emitted when the end-task confirmation dialog is closed with the x button.
- `EndTaskConfirmationClosed`: emitted with the x-button close path for the end-task confirmation dialog.
- `TaskContinued`: emitted when the user backs out of ending the task.
- `ClickedEndTaskConfirmation`: emitted when the user confirms final task submission.
- `TaskEnded`: emitted when the task is submitted with an answer.

### Search input and autocomplete

- `queryBoxFocused`: emitted when the search input receives focus.
- `queryCleared`: emitted when the user empties the search input with the clear
  button next to it.
- `hoverOverQuerySuggestions`: emitted when the user hovers over an autocomplete suggestion.
- `choseAutoCompleteSuggestion`: emitted when the user selects an autocomplete suggestion.
- `querySubmitted`: emitted when a search query is submitted.

### SERP and result interaction

- `searchResultGenerated`: emitted once for each result rendered on a normal SERP.
- `searchNoResults`: emitted when the no-results state is rendered.
- `generatedDidYouMean`: emitted when a corrected-query suggestion appears.
- `hoverOverDidYouMean`: emitted when the user hovers over the corrected-query suggestion.
- `clickedDidYouMeanSuggestion`: emitted when the user clicks the corrected-query suggestion.
- `cursorEnteredSnippet`: emitted when the mouse enters a result card or snippet.
- `cursorLeftSnippet`: emitted when the mouse leaves a result card or snippet.
- `resultExposureStarted`: emitted when a result is at least 50 percent visible for at least 250 ms.
- `resultExposureEnded`: emitted when an active result exposure ends.
- `clickedResult`: emitted when the user clicks a search result link.
- `pageNavigationClicked`: emitted when the user clicks SERP pagination.
- `customBackButtonClicked`: emitted when the app-level back button is clicked, including the current URL and destination URL.
- `logoOnSerpClicked`: emitted when the SERP logo link is clicked.
- `taskQuestionHelpClicked`: emitted when the task help modal is opened.
- `taskQuestionHelpClosed`: emitted when the task help modal is closed.

### Resource viewer and iframe tracking

- `webpageOpened`: emitted when the embedded resource viewer opens.
- `resourceViewStarted`: emitted when the resource dwell session starts.
- `webpageLoadSucceeded`: emitted when the iframe check says the resource should load.
- `webpageLoadFailed`: emitted when the iframe check says the resource is blocked.
- `webpageLoadCheckUnknown`: emitted when iframe load status cannot be determined.
- `iframeNavigation`: emitted when a readable iframe navigates to a different URL.
- `iframeBackNavigation`: emitted when the viewer back button navigates inside readable iframe history.
- `iframeNavigationTrackingLimited`: emitted when iframe navigation cannot be inspected because of cross-origin restrictions.
- `webpageClosed`: emitted when the resource view closes through back, page unload, or task end.
- `resourceViewEnded`: emitted when the resource dwell session ends.

### Browser back blocking

- `browserBackBlocked`: emitted when native browser back navigation is intercepted, blocked, or redirected back to the latest allowed app URL, including the current URL and target URL.

### Reward and completion

- `rewardShown`: emitted server-side when a task reward page is rendered.
- `sessionCompleted`: emitted when the final completion page loads.
- `finalRewardRevealClicked`: emitted when the final reward reveal button is clicked.
- `finalRewardRevealCompleted`: emitted when the final reward reveal animation completes.
- `experimentFinished`: emitted when the final save-and-finish button is clicked.

### Errors

- `searchError`: emitted when the search error page is rendered for a search-engine error.

## Event inventory

<!-- event-inventory:start -->
- `AnswerBoxClosed`
- `ClickedEndTaskConfirmation`
- `ClickedOnSendAndTerminateTask`
- `EndTaskConfirmationClosed`
- `EndTaskDialogClosed`
- `OpenedAnswerBox`
- `TaskContinued`
- `TaskEnded`
- `TaskStarted`
- `browserBackBlocked`
- `choseAutoCompleteSuggestion`
- `clickedDidYouMeanSuggestion`
- `clickedResult`
- `cursorEnteredSnippet`
- `cursorLeftSnippet`
- `customBackButtonClicked`
- `experimentFinished`
- `finalRewardRevealClicked`
- `finalRewardRevealCompleted`
- `generatedDidYouMean`
- `hoverOverDidYouMean`
- `hoverOverQuerySuggestions`
- `idSubmitted`
- `iframeBackNavigation`
- `iframeNavigation`
- `iframeNavigationTrackingLimited`
- `logoOnSerpClicked`
- `pageNavigationClicked`
- `queryBoxFocused`
- `queryCleared`
- `querySubmitted`
- `resourceViewEnded`
- `resourceViewStarted`
- `resultExposureEnded`
- `resultExposureStarted`
- `rewardShown`
- `searchError`
- `searchNoResults`
- `searchResultGenerated`
- `sessionCompleted`
- `taskQuestionHelpClicked`
- `taskQuestionHelpClosed`
- `webpageClosed`
- `webpageLoadCheckUnknown`
- `webpageLoadFailed`
- `webpageLoadSucceeded`
- `webpageOpened`
<!-- event-inventory:end -->

## Setup

Start the app with a clean browser profile or clear local storage before the
run. Use a test participant ID that exists in `data/uids.txt`, then keep the
generated full log and per-task log open while exercising the flow.

### 1. Start a session

Submit a valid participant ID and start the first task. Confirm that
`idSubmitted` appears before `TaskStarted` and that following events carry the
same `sessionID` and `uid`.

### 2. Exercise search input logging

Focus the search box, type at least three characters, hover an autocomplete
option if one appears, select a suggestion, and submit a query. Confirm
`queryBoxFocused`, `hoverOverQuerySuggestions`, `choseAutoCompleteSuggestion`,
and `querySubmitted` where applicable.

### 3. Exercise normal SERP logging

Run a query that returns results. Confirm one `searchResultGenerated` per
visible result, then move the mouse over a result card to check
`cursorEnteredSnippet` and `cursorLeftSnippet`. Scroll so a result remains
visible long enough to trigger `resultExposureStarted`, then move away from it
to trigger `resultExposureEnded`.

### 4. Exercise pagination and SERP return logging

Click a pagination control and confirm `pageNavigationClicked`. Use the
app-level back button from a resource page and confirm
`customBackButtonClicked.fromURL` is the resource view and
`customBackButtonClicked.toURL` is the destination SERP. Click the SERP back
button and confirm `customBackButtonClicked.toURL` points to the search page.
Press the browser Back button and confirm the current app page stays in place
while `browserBackBlocked` is logged with `fromURL` and `toURL`.

### 5. Exercise did-you-mean and no-result logging

Run a query that produces a corrected-query suggestion. Confirm
`generatedDidYouMean`, then hover and click the suggestion to confirm
`hoverOverDidYouMean` and `clickedDidYouMeanSuggestion`. Run a query with no
results and confirm `searchNoResults`.

### 6. Exercise resource page logging

Click a result title and confirm `clickedResult`, `webpageOpened`, and
`resourceViewStarted`. Confirm exactly one of `webpageLoadSucceeded`,
`webpageLoadFailed`, or `webpageLoadCheckUnknown`. Leave the resource view with
the app-level back button or by ending the task, then confirm `webpageClosed`
and `resourceViewEnded`. Pressing the native browser Back button from the
resource view should keep the resource page open and log `browserBackBlocked`,
including `fromURL` and `toURL`.

### 7. Exercise iframe navigation logging

On a resource that allows readable iframe navigation, click an internal link and
confirm `iframeNavigation`. Use the viewer back button while iframe history is
available and confirm `iframeBackNavigation`. On cross-origin pages, confirm
`iframeNavigationTrackingLimited` may appear instead of detailed iframe
navigation.

### 8. Exercise answer modal and task-end logging

Open the answer modal and confirm `ClickedOnSendAndTerminateTask` and
`OpenedAnswerBox`. Close it once to confirm `AnswerBoxClosed`, then reopen it,
enter an answer, and continue through the confirmation dialog. Confirm
`ClickedEndTaskConfirmation` and `TaskEnded`. If the confirmation dialog is
closed instead, confirm `EndTaskDialogClosed`, `EndTaskConfirmationClosed`, and
`TaskContinued`.

### 9. Exercise final reward logging

After each task, confirm the server writes `rewardShown`. After the final task,
open the completion page and confirm `sessionCompleted`, click the reveal
button to confirm `finalRewardRevealClicked` and `finalRewardRevealCompleted`,
then finish the experiment and confirm `experimentFinished`.

### 10. Exercise search error logging

Force or simulate a search-engine error path and confirm `searchError` is
written with the attempted query and error label.

## Final checks

Run the offline log checker against the generated full log and per-task logs.
Confirm required fields are present, result exposure start/end events are
paired, resource view start/end events are paired, and no duplicate consecutive
`querySubmitted` event appears for the same task and query.
