# Change log

A running record of what changed in the app, why, and what it could break.

This is a debugging tool, not release notes. When a participant reports odd
behaviour, or a log file looks wrong, the point of this file is to turn
"something broke, no idea when" into "three changes touched that area, here
they are, newest first".

## How to use this when something breaks

1. Name the broken area in the vocabulary below, for example `autocomplete`.
2. Search this file for that tag: `grep -n "Area:.*autocomplete" CHANGELOG.md`.
3. Read the matching entries newest first. Each one lists the symptoms it
   could plausibly cause and what it deliberately left alone.
4. If the area tag finds nothing, search for the file path instead. Every
   entry lists the files it touched.

**Area vocabulary.** Keep to these so the search stays reliable. Add a new
one only when nothing fits.

`search-bar`, `autocomplete`, `serp`, `pagination`, `back-navigation`,
`result-viewer`, `logging`, `session`, `task-flow`, `reward`, `styling`,
`data`, `infra`, `docs`, `tests`

## How to add an entry

Add one entry per commit, in the same commit as the change, at the top of
the Entries section. Copy this template.

```markdown
## YYYY-MM-DD — Short scannable subject, ideally the commit subject

**Commit:** `sha` · **Type:** feature | fix | content | infra · **Area:** tag, tag

**Files**
- `path/to/file` — what changed in it

**What changed for the participant**
The observable difference. Skip if there is none, say "no visible change".

**How it works**
The mechanism, only as much as a future reader needs to locate it.

**If something looks wrong after this, check**
- Symptom → where to look first.

**Left alone**
Things in the same area that were deliberately not touched, so they can be
ruled out quickly.

**Verified**
How it was tested, and anything that could not be tested.
```

Two rules that make this worth keeping:

- **Left alone** is as valuable as what changed. Ruling a file out is half
  of debugging.
- Write the entry when you make the change, not later. Reconstructing it
  from a diff weeks on loses the reasoning, which is the part a diff cannot
  show.

---

# Entries

## 2026-09-18 — Search bar: external clear button + instant search on suggestion pick

**Commit:** `cdac79f` · **Type:** feature · **Area:** search-bar, autocomplete, styling, logging, infra

**Files**
- `search-app/templates/home.html` — input wrapped in a `.search-field` row, clear button added
- `search-app/templates/search.html` — same markup change, kept identical to home
- `search-app/templates/layout.html` — clear button behaviour, suggestion submit, CSS cache-busting string
- `search-app/static/main.css` — native clear control suppressed, new button styles, stacked layout rule
- `docs/manual_logging_walkthrough.md` — registered the new `queryCleared` event
- `docker-compose.local.yml`, `docs/local_ui_development.md` — unrelated to the
  search bar. The local preview setup was untracked until now and went in with
  this commit. It mounts templates, static files and the main Python modules
  into the container so edits show up on refresh, started with
  `./scripts/local-ui.sh`. Note `scripts/local-ui.sh` itself is still untracked.

**What changed for the participant**

Two things. The clear control is no longer the browser's own one drawn
inside the input on top of the typed text. It is now an app-owned circular
button sitting outside the field, between the input and "Cerca". It appears
only when there is text to clear.

Choosing an autocomplete suggestion now runs the search immediately.
Previously it only filled the box and the participant still had to press
"Cerca". This applies to both ways of choosing: clicking a suggestion, and
highlighting one with the arrow keys then pressing Enter.

**How it works**

`::-webkit-search-cancel-button` and `::-webkit-search-decoration` are
suppressed on `#search-box`, so the input no longer draws its own control.
`#clear-search-btn` sits beside the input inside `.search-field`. Its hidden
state uses `visibility`, not `display`, so the row never reflows when the
field empties.

`select()` in the layout script now calls `submitSearch()`, which uses
`form.requestSubmit(#submit-box)`. It does not use `form.submit()`, which
would not fire the submit event and would silently skip the study logger and
the loading spinner. Passing the submit button as the submitter keeps the
POST body identical to a manual click on "Cerca".

A guard prevents a second submit while the first is navigating. It releases
on `pageshow`, so a bfcache restore during back-navigation does not leave
the dropdown dead, and after four seconds, so an interrupted load cannot
either.

**If something looks wrong after this, check**

- Clear button missing, or an unstyled x back inside the input → the
  stylesheet is stale. The cache-busting string in `layout.html` is
  `?v=clear-button-20260918`; a running container that bakes files into the
  image rather than mounting them will serve the old CSS.
- Search bar row wraps oddly or overflows on tablets → `.search-field` in
  the `max-width: 900px` block in `main.css`, which makes the row full width
  when the form stacks.
- Suggestion click fills the box but does not search → `submitSearch()` in
  `layout.html`. Most likely the guard stuck, or `#submit-box` / `#search-bar`
  was renamed in one template but not the other.
- Duplicate `querySubmitted` events for one search → the submit guard and
  `querySubmitInProgress` in `logger.js` both exist to prevent this.
- Analysis scripts choking on an unknown event → `queryCleared` is new.

**Left alone**

`logger.js` is unchanged. The log schema and the server are unchanged: the
`/result` route reads only the `query` field and never read the submit
button's name. Event names and payloads for `querySubmitted`,
`choseAutoCompleteSuggestion` and `queryBoxFocused` are unchanged, and
`querySubmitted` still carries `autocompleteSelectedSuggestion`. The
suggestion fetch, its 300ms debounce and the `/autocomplete` endpoint are
unchanged. The `?` task-help button and the submit button keep their ids,
classes and position.

**Verified**

Against the built image with templates mounted live, in an isolated
container, driving the real page scripts. Confirmed: button position and
hidden state, click clears without submitting the form, suggestion click and
Enter each fire exactly one submit carrying the chosen suggestion, event
order stays `choseAutoCompleteSuggestion` then `querySubmitted`, submitter is
`submit-box`. The results template renders the same form and script.

Not tested end to end: a real results page. The Vertex search backend
returns 503 from this machine, so no SERP could be loaded.

---

The entries below were reconstructed from git history after the fact. They
record what the commit and its diff show, without the reasoning that was
never written down. Entries from here on should be written at commit time.

## 2026-05-19 — Added new users for India, 17 and 18

**Commit:** `ddcc0f4` · **Type:** content · **Area:** data

**Files**
- `search-app/data/uids.txt` — two ids added
- `search-app/data/user_topics.csv` — matching topic rows added

**What changed for the participant** Two more participant ids are accepted
at the start screen, each with its own task topics.

**If something looks wrong after this, check** A participant id rejected at
login, or a task showing the wrong question, means these two files disagree.
Every id in `uids.txt` needs matching rows in `user_topics.csv`.

## 2026-05-18 — Custom Indietro button: step back through full query/page history

**Commit:** `eb9e3b9` · **Type:** feature · **Area:** back-navigation, serp, session

**Files**
- `search-app/search_app.py` — navigation history in the session
- `search-app/templates/search.html` — back button href driven by `back_url`

**What changed for the participant** Indietro now steps back through every
view seen, queries as well as pages, instead of jumping straight to the
empty search bar. Earlier results are replayed exactly as they were shown
rather than re-searched, so a logged click always matches what was on screen.

**How it works** `result()` keeps `results_by_query` as a per-query exact
replay cache and `nav_stack` as the chronological list of views. `back=1`
pops, a forward move pushes, deduplicated at the top and capped at 50
entries. `next_task()` clears both so tasks stay isolated.

**If something looks wrong after this, check** Indietro landing in the wrong
place, or results changing between first view and going back → `nav_stack`
and `results_by_query` in the session. Task bleed, where task 2 can step back
into task 1, → the clearing in `next_task()`.

**Left alone** Per the commit message: `logger.js`, the log schema, and the
`#serp-back-btn` id, class and DOM position. `getPageType` ignores the
`&back=1` marker, so `customBackButtonClicked` stays classified serp-to-serp.

## 2026-05-18 — Specified client for SERP API autocomplete calls

**Commit:** `fd250cb` · **Type:** fix · **Area:** autocomplete

**Files**
- `search-app/search_backend.py` — `client` parameter added to the SERP autocomplete request

**What changed for the participant** Autocomplete suggestions from the SERP
API fallback look closer to what the same query would return on Google.

**If something looks wrong after this, check** Suggestions suddenly generic
or empty → the `client` parameter, defaulting to `gws-wiz`, overridable
through `SERP_AUTOCOMPLETE_CLIENT`. This affects only the fallback path, not
Vertex.

## 2026-05-18 — Fixed second page returning to the search bar instead of SERP results

**Commit:** `8e6bdad` · **Type:** fix · **Area:** pagination, back-navigation

**Files**
- `search-app/templates/search.html` — back button href made page-aware

**What changed for the participant** From page 2 or later, Indietro goes to
the previous page of results instead of dumping the participant back at the
empty search bar.

**How it works** The href became conditional: page above 1 links to the
previous page of the same query, otherwise to the search page. Superseded a
week later by the server-side navigation history in `eb9e3b9`.

## 2026-05-18 — Logo size, user numbering, question mark position

**Commit:** `1215af9` · **Type:** fix · **Area:** styling, search-bar, data

**Files**
- `search-app/data/uids.txt`, `search-app/data/user_topics.csv` — ids renumbered
- `search-app/static/main.css`, `search-app/templates/home.html`,
  `search-app/templates/search.html`, `search-app/templates/start.html` — layout

**What changed for the participant** The `?` task-help button moved next to
the search bar, the logo was resized, and participant ids were renumbered.

**If something looks wrong after this, check** Ids not matching an older log
file → the renumbering happened here, so logs recorded before this commit use
the old numbering.

## 2026-05-17 — Apply spellchecker only when Vertex AI flags the query as wrong

**Commit:** `6cffd0d` · **Type:** fix · **Area:** serp

**Files**
- `search-app/search_backend.py` — spellchecker gated behind the Vertex verdict

**What changed for the participant** Fewer spurious "Forse cercavi"
corrections on queries that were already correct.

**If something looks wrong after this, check** Corrections never appearing →
this gate. If Vertex does not flag a query, the local spellchecker no longer
gets a say.

## 2026-05-16 — Safer log saving: recover abandoned-participant logs

**Commit:** `d6d9357` · **Type:** feature · **Area:** logging, session

**Files**
- `search-app/search_app.py` — recovery path on submission
- `search-app/static/logger.js` — client side of the same
- `search-app/templates/layout.html` — operator notice banner
- `search-app/tests/test_logging_contract.py` — coverage

**What changed for the participant** Nothing visible. For the operator, a
banner appears when the server recovers events from a previous unfinished
participant and saves them as an incomplete experiment, instead of rejecting
the mixed submission and losing the data.

**If something looks wrong after this, check** The orange banner at the top
of the page is this feature, not an error. Events attributed to the wrong
participant, or an unexpected "incomplete" log file, → the recovery path.
The banner is driven by the `sol:incomplete-recovered` event in
`layout.html`.

## 2026-05-15 — Vertex-first autocomplete and query correction, with fallbacks

**Commit:** `1c84960` · **Type:** feature · **Area:** autocomplete, serp, logging

**Files**
- `search-app/search_app.py`, `search-app/search_backend.py` — provider order
- `search-app/static/logger.js` — model recorded in the log events
- `search-app/templates/no_result.html`, `search-app/templates/search.html` — rendering
- `.gitignore`

**What changed for the participant** Autocomplete and "Forse cercavi" now
come from Vertex AI first, falling back to the SERP API and pyspellchecker
respectively when Vertex fails. Correction suggestions are also shown when a
query returns no results.

**How it works** Logging records which model produced each suggestion, so
analysis can separate Vertex suggestions from fallback ones.

**If something looks wrong after this, check** Suggestions appearing with no
obvious source, or analysis unable to tell providers apart → the model fields
on the autocomplete and correction events. A sudden change in suggestion
quality usually means Vertex is failing and the fallback is serving.
