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

## 2026-10-20 — Repair preparation menus, enrollment filters and question tables

**Type:** fix · **Area:** session, styling, data, tests, docs

**Files**
- `search-app/research_dashboard/enrollment_views.py`, `templates/research/enrollment.html` — exact ID search, clear filters, cancel editing, fixed session year and recoverable add/enroll choice.
- `search-app/research_dashboard/preparation_views.py`, `templates/research/base.html` — retain the selected session through global preparation navigation.
- `search-app/research_dashboard/templates/research/prepare.html` — in-page class/session menus open a choice directly, showing saved dates.
- `search-app/research_dashboard/templates/research/participant_question_table.html`, `session_questions.html` — shared aligned table with short Personalize/Edit actions and ID-specific accessible labels.
- `search-app/research_dashboard/i18n.py`, `static/research.css` — labeled filter controls and guidance in English/Italian.
- `search-app/tests/test_enrollment_controls.py` — exact identity, filter reset, session navigation and form recovery regressions.
- `search-app/tests/test_preparation_controls.py` — rendered menu submissions, school-year switching and per-ID question actions.

**What changed for the participant**
Researchers searching for ID `1` see that participant rather than IDs `10`–`19`.
Filters can be cleared without losing the selected class/year/session. Enrollment
forms no longer invite a year change that the selected session rejects, and failed
existing-ID enrollment retains the correct operation and instructions.
Class and session choices open inside the page, including in the local preview;
choosing one opens its details immediately. Question configuration tables use the
same headings and short actions in preparation and the editor.

**How it works**
The enrollment query matches the exact permanent ID. Filter/reset/cancel links keep
the preparation context. Global preparation navigation also carries the session ID.
Session forms submit its fixed school year; signed review and revision checks still
validate writes.
The menus use HTML disclosure elements and submitted GET buttons, without relying
on native select popups or JavaScript. The question table shares its markup and
explicit left alignment across both views.

**If something looks wrong after this, check**
- Empty search → enter the complete ID, including leading zeros and letter case.
- Unexpected enrollment rejection → check active status, selected class/year and revision.

**Left alone**
Permanent identities, schema, student collection and the study's existing records.

**Verified**
330 automated tests passed. The local synthetic preview was restarted with existing
data retained; browser checks covered exact search, edit, review and confirmation
returning to the selected session, class/session menu selection and question-table
layout. The final local container image built successfully.

## 2026-10-20 — Prepare sessions, participant IDs and questions in one workflow

**Type:** feature · **Area:** session, styling, data, tests, docs

**Files**
- `search-app/research_dashboard/preparation_views.py`, `templates/research/prepare.html`, `preparation_context.html` — session preparation entry and retained context.
- `search-app/research_dashboard/__init__.py`, `enrollment_views.py`, `templates/research/` — navigation, contextual enrollment review and draft/approval returns.
- `search-app/research_dashboard/participants.py`, `state.py` — enroll existing IDs with permanent keys and share session construction with administration.
- `search-app/research_dashboard/i18n.py`, `static/research.css` — English/Italian labels and preparation layout.
- `search-app/tests/test_session_preparation.py`, `test_research_dashboard.py` — workflow, identity, concurrency and admission coverage.

**What changed for the participant**
No student-page change. Researchers land on **Prepare a session**, with session
details, class IDs, saved drafts and question readiness together. Every active
class ID is included automatically in every session. Rare administration tools
remain under settings.

**How it works**
Preparation composes authoritative settings, enrollment and question services.
Initial enrollment and session details save under one revision. Known children
can be enrolled in another year without new identities; signed review shows any
changed grade. Question and enrollment editors return to the selected session.
No schema migration is introduced.

**If something looks wrong after this, check**
- Wrong session after navigation → `preparation_views.py` context selection and `prepare_session` links.
- An ID is missing → active status and enrollment for the session's own year/class.
- A draft appears unavailable → approval/readiness state, not the reporting cache.

**Left alone**
Student collection, immutable admitted snapshots, upload acknowledgement, durable
progress/resume work and live monitoring.

**Verified**
313 automated tests passed. Italian browser walkthrough covered session creation,
ID review/confirmation, draft save/reopen, approval and student entry with synthetic data.
The final image built and passed isolated container replacement and backup/restore checks.
Institutional deployment, physical tablets and external search need release checks.

## 2026-10-19 — Recover collection safely after retries and server replacement (#18)

**Type:** fix · **Area:** logging, session, task-flow, infra, data, tests, docs

**Files**
- `search-app/research_dashboard/log_store.py` — durable upload receipts and recoverable appends.
- `search-app/research_dashboard/state.py`, `collection.py`, `index.py`, `runtime.py` — atomic admission, immutable snapshots, isolated reporting cache and private persistent session configuration.
- `search-app/search_app.py`, `static/logger.js`, `templates/layout.html`, `templates/end.html` — acknowledged uploads, stable retries and a visible retry dialog that survives reload.
- `docker-compose.yml`, `search-app/Dockerfile`, `search-app/requirements.lock`, `../scripts/deploy.sh`, `../.github/workflows/collection.yml` — persistent sessions, pinned dependencies, readiness, backup and image rollback.
- `search-app/tools/backup_study.py`, `check_collection_restart.py`, `setup_runtime_secret.py` — verified recovery and isolated restart checks.

**What changed for the participant**
A failed answer save displays **Riprova** and retains the pending answer after a
reload. Retrying a lost response does not record the answer twice. Replacing the
container preserves active session state when persistent storage and the key remain.

**How it works**
Admission commits the immutable question/session snapshot before sidecar publication.
An upload journal records exact log offsets/bytes before appending and acknowledges
only after all destinations are flushed. The reporting index is lazy and rebuildable.
See [production recovery](production_readiness.md) for the storage and upgrade contract.

**If something looks wrong after this, check**
- Save remains pending → collection write access, `.uploads.sqlite3` and original-file consistency; retain the browser buffer.
- Student cookies stop working → signing key and `student-sessions` mount. The first upgrade requires finished classroom runs because the old shared fallback key is replaced.
- Dashboard unavailable but collection works → reporting cache and server storage diagnostics.

**Left alone**
Permanent identities/yearly enrollment (#19), full progress/resume (#6), authorized
repeat/reset (#15), live monitoring (#17), and the selected HTTP/VPN deployment.
Existing original logs and task event fields are preserved.

**Verified**
Automated failure, concurrency, migration, backup and client-upload tests; production
image build; replacement-container check; browser failure → reload → retry → reward
with one original answer. Server deployment, actual tablet and external search checks
remain release acceptance steps; the older Selenium suites need separate setup.

## 2026-10-16 — Remove and restore unused study sessions

**Type:** feature · **Area:** session, data, tests, styling, docs

Session settings offer confirmed removal for unused sessions, with a separate
Removed sessions section for restoration. Saved questions, original numbers and
IDs are retained; removed sessions are excluded from new student eligibility.
Fresh index checks protect sessions with participant records, including started
metadata-only attempts, archived history and trashed logs. Unavailable or uncertain
source data blocks removal. An in-flight run arriving after removal retains its
history; #6 must atomically coordinate future attempt creation with availability.
Original source logs are never erased. Regression tests cover identity reservation,
draft restoration, date conflicts, access, storage failures and historical records.

## 2026-10-15 — Show saved question drafts and remove repeated reuse choices

**Type:** fix · **Area:** session, task-flow, data, styling, tests, docs

Saved session questions now appear in session settings and the session overview,
with draft/approved status and a link to continue editing. Explicit draft-save,
save-and-return and approval actions clarify when work is persisted. Unsaved
library previews say that they still need saving.

The individual question picker lists each normalized topic/question once.
Full-set experiment variants and original metadata remain available; copying a
question does not choose a conflicting condition arbitrarily. New regression
tests cover saved drafts, reopening, approval, scope, duplicate choices and metadata.

## 2026-10-15 — Configure dated V2 session questions and participant exceptions

**Type:** feature · **Area:** session, task-flow, reward, logging, data, docs, tests

**Files**
- `search-app/research_dashboard/study_config.py`, `state.py`, `student_config.py` — question sets, approval, readiness and legacy metadata library.
- `search-app/research_dashboard/__init__.py`, templates and styles — shared/individual editors and session readiness.
- `search-app/search_app.py`, reward/end templates — dated access and completion without puzzle media.
- `search-app/research_dashboard/collection.py`, `index.py` — immutable question/session metadata and historical grouping.
- Configuration, editor, student, history and metadata tests; setup instructions.

**What changed for the participant**
Only today's configured Zurich session can start, using approved shared questions
or an individual exception. Missing an earlier session does not block today. Puzzle
files are optional. Unavailable sessions show “Session not available”.

**How it works**
Fresh assignments live inside append-only SQLite settings revisions. The editor
keeps imported IDs and experiment metadata in signed drafts. New runs snapshot
questions, session identity and randomized order; edits apply to new runs.

**If something looks wrong after this, check**
- Student cannot start → session date, exact roster ID, approval and three complete questions.
- Interest condition differs → selected library variant and saved metadata.
- Old session label differs → recorded sidecar snapshot and index refresh.

**Left alone**
Search retrieval, interaction event formats, authentication, archived source logs
and school-year rules. Durable progress and authorized repeat/reset remain #6/#15.

**Verified**
Automated tests use isolated synthetic settings/logs and stub search. Browser checks
cover the editor and readiness. Existing Selenium back/BFCache suites require their
separate live-app/browser environment.

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

## Permanent enrollment foundation — issue #19

- Added a permanent participant register, annual enrollments, individual status/grade
  edits, and reviewed year-to-year promotion. IDs are never recycled.
- Sessions own their September–August school year; admission checks exact enrollment
  and captures stable participant/enrollment keys with the immutable question snapshot.
- Added explicit, date-scoped legacy identity links and revocation with an audit trail.
  Unified participant history/exports retain source IDs, original files and link provenance.
- Added transactional schema 2 migration, concurrent-edit protection, and restart/restore
  checks for registry keys and annual enrollment.
- Documented the source integration contract for #6 in `dashboard_integration.md`.
