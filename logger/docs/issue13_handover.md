# Issue 13 autocomplete and query correction

The browser waits 200 ms after the last edit, then requests `/autocomplete?query=…`
for a trimmed prefix of at least three characters. `layout.html` cancels pending
work on a subsequent edit, clear, or selection. The sequence check runs after
both the response and JSON parsing. On receipt, the browser renders up to five
suggestions and records their prefix, source, and model. Click or ArrowDown
followed by Enter submits the selected suggestion through the search form.

`search_app.py` requires a participant session and forwards the trimmed prefix
to `search_backend.autocomplete`. With Vertex configured, the backend uses
the worker's reusable completion client, one 750 ms RPC attempt, and the
configured completion model (default `search-history`). Empty results, missing
Vertex configuration, and provider errors lead to SerpAPI when a key is present.
SerpAPI uses Italian `hl` and `gl` defaults and `gws-wiz` by default. Its connect
and read timeouts are each 2 seconds. With PyTerrier configured, SerpAPI supplies
suggestions directly. Empty, malformed, and failed responses produce a consistent
empty list. Provider error logs record exception classes and omit the query and key.
The old Flask autocomplete cache write had already been removed on the base branch.
The reused client holds the transport in memory, and each request still sends its
prefix to the selected provider.

The route returns `suggestions`, `source`, and `query_model`. The study log source
labels remain `vertex` for Vertex results, `SERP_API` for fallback in Vertex mode,
and `pyterrier` for SerpAPI results in PyTerrier mode. `query_model` records the
configured Vertex completion model on successful Vertex-mode responses, including
fallback. A response with no suggestions carries `source` of `none` and a null model.
The browser preserves `autocompleteSuggestionsShown`, `choseAutoCompleteSuggestion`,
`queryCleared`, and `querySubmitted` and their existing fields.

## Query correction and synthetic Italian examples

`/result` searches the submitted query. Vertex sends `SUGGESTION_ONLY`; when it
offers a correction, the result page links to it as `Forse cercavi`. Following
the link makes a separate search. PyTerrier uses the Italian spellchecker for
the correction link and sends the submitted query to its ranking service.

| Synthetic input | Fixture response | Expected behavior |
| --- | --- | --- |
| `fasi della lu` | Vertex times out, SerpAPI offers `fasi della luna` | The browser shows the suggestion with fallback source metadata. |
| `fasi della lna` | Vertex offers `fasi della luna` as a correction | The original query is searched and the correction is offered as a link. |
| `rocce vulcaniche` | Vertex offers no correction | The original query is searched as entered. |

These are test fixtures. Approved Italian examples and observed live provider
responses are pending.

## Live verification

The Chromium regression uses a controlled 250 ms response delay and checks that
the list is displayed within 500 ms of the final edit. The browser contributes
200 ms of intentional wait, down from 300 ms. Provider and network times depend
on the environment, and fallback may take longer because it follows the Vertex
attempt. The reported roughly 1.5 seconds was an observation from the issue
discussion, separate from the synthetic test.

On a test session against the intended deployment, time the last input to the
first visible suggestion for the agreed Italian prefixes. Record a cold and a
warm request, whether Vertex or SerpAPI supplied the suggestions, and the event
fields. Confirm the correction link with the approved examples once available.
Issue 11 also edits the shared layout for keyboard and dismissal behavior. After
integrating it, rerun the autocomplete browser regressions on the combined layout.
