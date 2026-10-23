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

## 2026-10-23 — Upload during tasks, keep reused-set conditions, ignore recovered fragments in status

**Commit:** pending · **Type:** fix · **Area:** logging, task-flow, data, docs, tests

**Files**
- `search-app/static/logger.js` — `syncLogsInBackground()` uploads unsent events on
  page load, every 60 s and when the page is hidden or closed (registered on `load`,
  after the viewer's own `pagehide` handler); small batches use `keepalive`. A
  successful upload no longer clears the navigation history used by `logSERP`.
- `search-app/research_dashboard/question_views.py`, `question_versions.py`,
  `state.py` — the `recovered_draft_token` field re-applies a recovered copy's question
  IDs and condition metadata if this session's questions are unchanged since the copy
  (`question_fields()`, `State.settings_body()`); otherwise
  `question_set_changed_since_copy` is shown once and the typed text stays on screen.
- `search-app/research_dashboard/static/editor.js`,
  `templates/research/session_questions.html` — "Use this text with the current
  version" also sets `recovered_draft_token`; structural fields are never shown as text.
- `search-app/research_dashboard/index.py`, `history_data.py`,
  `templates/research/overview_table.html`, `participant.html`, `i18n.py` — runs made
  only of `*_INCOMPLETE.log` files are marked `recovery_only`, shown as "Recovered
  fragments" and excluded from status; the overview footer explains when logs are saved.
- Docs: `research_dashboard.md`, `manual_logging_walkthrough.md`.
- Tests: `test_background_upload_browser.py`, `test_question_recovery_structure.py`,
  `test_question_recovery_browser.py` (new); `test_reporting_scope_regressions.py`.

**What changed for the participant**
No visible change. Events now reach the server while the child works, so an
interrupted run (lesson over, iPad switched off) keeps everything up to the last
page instead of losing the unfinished task when the next child starts on that iPad.

**What changed for researchers**
Saved logs grow during a task. After a conflict, recovered editor text of a reused
set keeps its question IDs and conditions (e.g. the high-interest question), unless
the session's questions were changed meanwhile. A recovered fragment no longer
marks a child who completed as incomplete.

**How it works**
Uploads reuse the pending-batch protocol: a batch is stored with its identifier
before sending and resent until acknowledged, and the server deduplicates by
`(session, batch_id)`. Events on a task's pages are uploaded while the server is on
that task, so `task_number` attribution is unchanged; the end-of-task flow still
waits for every queued upload before `/end`.

**If something looks wrong after this, check**
- A results page revisit appears as new `searchResultGenerated` events → the
  navigation history must survive uploads; see `sendLogs()` and `logSERP()`.
- More `/log_session` requests in the server log → expected: one per page load
  with new events, at most one per minute while idle, plus page exit.
- An editor save refused with "after your copy was made" → another tab changed
  this session's questions; saving again keeps only the text.

**Left alone**
Uploads still require the server session of the run: events typed after the last
page load on an iPad that is reset at once (no screen-off, no minute elapsed) can
still be lost. No change to the start page, the provider error page or deployment.

**Verified**
Full suite with required Chromium browser tests (594 passed). The new upload test
fails on `c0e685a`; re-adding the history reset makes the revisit test report 4
instead of 2 `searchResultGenerated` events; the four recovery tests fail on `c0e685a`.

## 2026-10-23 — Enforce the 60-minute idle limit on every student page

**Commit:** pending · **Type:** fix · **Area:** session, task-flow, tests

**Files**
- `search-app/search_app.py` — `idle_session_expired()` replaces `note_student_activity()`
  and the search page's own check: each page navigation (task, search, result, viewer,
  end task, reward, next task) first enforces the limit, then records activity.
- `search-app/tests/test_student_start_and_recovery.py` — the idle test now checks
  both halves of the rule on the viewer, result and search pages.

**What changed for the participant**
A run left open for over an hour ends on whichever page is opened first, and the
child returns to the welcome page. A child who keeps opening pages is not stopped.

**How it works**
The previous commit refreshed `last_active` on every page but checked it only on
the search page, so a run left open on an iPad could continue days later through
the results or viewer pages. Checking and refreshing now happen together.

**If something looks wrong after this, check**
- A child is sent to the welcome page mid-task → `last_active` in the student
  session; more than 60 minutes passed without opening any page.

**Left alone**
Background requests (autocomplete, frame checks, uploads) neither count as activity
nor end the run; `/log_session` still accepts uploads from an expiring page.

**Verified**
Full suite with required Chromium browser tests; the new idle test fails on the
previous commit (`bc3f7df`) at the viewer page.

## 2026-10-23 — Fix review findings: hidden absent children, empty runs, lost input on concurrent changes

**Commit:** pending · **Type:** fix · **Area:** session, task-flow, logging, data, styling, docs, tests

**Files**
- `search-app/research_dashboard/history_data.py` — year views also list children
  enrolled in that grade/year without runs; status and completion ratio ignore runs
  without saved log files (`status_runs`, `empty_run_count`); one shared ID sort key.
- `search-app/research_dashboard/history_views.py` — participant page opens for an
  enrolled child without runs in the selected year instead of 404.
- `search-app/research_dashboard/preparation_views.py`, `question_views.py`,
  `enrollment_views.py` — a POST for a session removed or moved elsewhere (or a child
  moved to another class) re-renders with the typed input, an explanation and a
  review link instead of 404. A fresh GET is still 404.
- `search-app/research_dashboard/settings_views.py` — `session_review_url()` shared
  helper; `revision_for()` gives only the rejected form the stale revision.
- `search-app/research_dashboard/participants.py` — `participant_sort_key` uses
  `isdecimal` (legacy ID "²" crashed the links page); `ParticipantError` names the
  IDs behind reserved/unregistered/inactive/promotion-conflict errors.
- `search-app/research_dashboard/state.py` — year change of a session with records
  raises `session_year_has_records` (was the removal message).
- `search-app/research_dashboard/i18n.py` — clearer `settings_changed` wording (other
  tab or researcher), new messages, missing `school_year_unknown`.
- Templates: `prepare.html`, `session_questions.html`, `enrollment.html`,
  `overview_table.html`, `participant.html`, `settings*.html`, `base.html` (CSS version).
- `search-app/research_dashboard/static/research.css`, `workflow.css` — 44 px tap width
  for EN/IT and participant-ID links on touch screens; preview keeps line breaks.
- `search-app/search_app.py` — repeated start of an untouched run continues it;
  admission retried when a researcher save races a start; idle limit counts every
  page; a batch from an earlier session is stored as INCOMPLETE recovery, not 409.
- `search-app/templates/start.html`, `layout.html`, `static/main.css` — start button
  disabled after the first tap; question line breaks shown to children; CSS version.
- `search-app/tools/seed_research_demo.py` — demo school year starts in September.
- Tests: three new modules (`test_concurrent_session_changes.py`,
  `test_reporting_scope_regressions.py`, `test_student_start_and_recovery.py`); assertions
  updated for the reworded conflict message, the new year-change code, the year view,
  the wrong-grade editor POST and the removed 409 path.

**What changed for the participant**
A double tap on **Continua** no longer creates a second, empty run. Multi-line
questions keep their line breaks. A child who reads pages for over an hour without
returning to the search page keeps the session; a real 60-minute pause still ends it.
If a researcher saves settings at the moment a child starts, the start succeeds.

**What changed for researchers**
A school-year or session view lists absent children as **No saved data**. A child
who completed one run is not marked incomplete by an empty run, which is shown as
**Started without saved data**. Removing or moving a session (or child) in another
tab no longer turns an open form into a 404 that loses typed input. After a
conflict, other forms on the settings page work without reloading. Enrollment and
promotion errors list the IDs involved.

**How it works**
`scoped_people()` adds `roster(settings, selected_year)` members when a year is
selected (grades 3–5 and "all"; not unassigned/legacy). `has_logs(run)` decides which
runs count. Concurrency fixes keep the stale revision or point the form at the
changed session, so a repeated click is refused again and never saves elsewhere.

**If something looks wrong after this, check**
- A year view shows children who did not take part → expected: they are enrolled;
  check `scoped_people()` in `history_data.py` if the wrong grade/year appears.
- A child shows completed although a run is incomplete → only runs without log
  files are ignored; check that run's `log_file_count` in the index.
- A child restarted but stayed in the same run → `untouched_run_for()` in
  `search_app.py`; it applies only before the first task's search page was opened.
- New `*_INCOMPLETE.log` files named after a session ID → batches from an earlier
  session of that browser; see `_accept_other_session_batch()`.

**Left alone**
The shared global settings revision (stale-write protection is unchanged); student
progress/resume, repeat authorization and the one-active-attempt policy; the dead
`templates/no_result.html`; Bootstrap/jQuery CDN loading on student pages; invalid
or session-less uploads still answer 400.

**Verified**
Full suite with required Chromium browser tests; the 20 new regression tests were
also run against an untouched copy of e19bef4: 19 fail there for the reported bug,
1 documents unchanged behavior and passes on both. A real-browser check confirmed
one admitted run after a double click and the visible line break. Not tested on a
physical iPad or in Safari.

## 2026-10-23 — Complete dashboard UX and preserve concurrent session edits

**Type:** feature, fix · **Area:** styling, session, logging, data, infra, docs, tests

**Files**
- `search-app/research_dashboard/` — scoped year controls, searchable question
  library, guarded forms, editor logout/recovery races, history and export fixes;
  required new assets, year helper and template partials are included.
- `search-app/static/logger.js` — prevent duplicate repeated-result listeners
  when restoring a page from the back/forward cache.
- `search-app/tests/`, `.github/workflows/collection.yml` — browser coverage for
  the implemented workflows, replacement of standalone Selenium suites, and
  required execution of every browser regression module.
- `docs/dashboard_review_2026-10-22.md`, `docs/merge_review_2026-10-23.md`,
  `docs/research_dashboard.md`, `docs/codex_handoff.md` — implementation evidence,
  merge gates and current handoff.

**What changed for researchers**
Session/year navigation, question selection and validation preserve context and
entered text. Cross-tab logout and failed saves retain on-screen edits. If another
researcher removes a session or moves it to another year, a rejected session edit
keeps the typed details and opens the saved state for review in a separate tab.

**How it works**
Failed settings POSTs clamp obsolete history pages and render an out-of-scope
submitted session separately through `settings_session_form.html`. The original
revision is retained, preventing a repeated stale save from overwriting changes.
The review link resolves the saved session's current year/page or restore panel.

**If something looks wrong after this, check**
- Missing question/year controls → verify that the new library assets,
  `year_controls.py` and template partials are present in the checkout/image.
- A session conflict hides typed fields → inspect `session_history()` in
  `settings_views.py` and the concurrency server/browser regressions.
- Logout or editor recovery feedback → inspect `static/editor.js` and its
  race/reconciliation tests; researcher recovery is not student progress storage.

**Left alone**
No real collection, credentials or generated demo archive are included. Durable
student resume, repeat authorization and live monitoring remain separate work.

**Verified**
The four new concurrency server cases fail before the fix and pass after it;
three browser cases pass across EN/IT touch layouts and without JavaScript.
See the merge review and PR #20 for full-suite and exact-candidate CI evidence.

## 2026-10-20 — Finalize dashboard review checkpoint and V2 handoff

**Type:** feature, fix · **Area:** styling, session, logging, infra, docs, tests

**Files**
- `search-app/research_dashboard/templates/research/base.html` — decorative gold
  mark and utilities on the top row, centered primary navigation below; selected
  settings navigation and versioned stylesheet URLs.
- `search-app/research_dashboard/static/{research,history,workflow,editor}.css` —
  final very pale logo-gold palette, neutral text and consistent selection states;
  the aligned control/session-row changes described below are included too.
- Student/backend hardening, editor recovery fixes, pinned browser-test dependency
  and required CI are included in this same checkpoint; the entries below describe
  their behavior and validation in detail.
- `docs/merge_v2_readiness.md` (new), `docs/codex_handoff.md`,
  `docs/dashboard_integration.md`, `docs/research_dashboard.md`, `README.md` — current
  merge/deployment gates, known limitations, V2 extension decisions, schema-version
  distinction and the local synthetic demo inventory.

**What changed for researchers**
The three main areas stand out on their own centered row. Light gold matches the
search mark while status badges keep their text and semantic colors. The handoff
now distinguishes what is implemented, what still needs acceptance before merge
or release, and what remains for progress/resume, repeats and monitoring in V2.

**If something looks wrong after this, check**
- Old colors or header arrangement → refresh the page and inspect the versioned
  research stylesheets and `base.html`.
- A large local roster or DEMO sessions in two years → these are local Docker
  fixtures described in `merge_v2_readiness.md`, not production participant data.
- Assumed student resume or live activity → those are still separate V2 changes;
  editor recovery and indexed sample logs do not implement them.

**Left alone**
This checkpoint adds no authoritative database migration, new student-progress
policy or classroom deployment. Local demo logs, state, passwords and one-off
seed scripts are excluded from Git.

**Verified**
449 tests passed in 64.72 seconds on Python 3.13.2, including all 10 required
Chromium regressions; the two legacy standalone Selenium suites were excluded.
Existing Flask-Session deprecation warnings remain. Dependency, JavaScript syntax,
Compose and diff checks passed. A Python 3.14.4 runtime image built successfully;
fresh-container restart plus verified backup/restore checks passed with synthetic
storage. Hosted CI and final-layout PC/iPad acceptance remain open; see the detailed
verification and limitations in `merge_v2_readiness.md`.

## 2026-10-20 — Align dashboard selectors, inputs and buttons

**Type:** fix · **Area:** styling

**Files**
- `search-app/research_dashboard/static/research.css` — new `--control-height`
  token (42px; 44px under `pointer: coarse`) used by buttons, inputs, native selects
  and the in-page menus. Native selects drop the platform look (`appearance:none`)
  and draw the same arrow as the menus with CSS gradients. The closed session menu
  shows its date on the name's line. Inputs nested in a `<label>` use regular text.
  Participant session rows use fixed name/date/badge columns. At ≤700px the grade
  and session pickers take full rows (the earlier `flex-basis:100%` rule lost on
  specificity), and a closed menu wraps the whole date instead of cutting it off.
- `search-app/research_dashboard/static/history.css` — picker labels use the same
  weight as other labels; "Show full history" is centred on the filter controls.

**What changed for researchers**
No behaviour change. In Prepare a session, the year field, Open year, Grade,
Session and New session now have one height and their labels sit on one line.
Previously the session menu was 64px tall because of its two-line date. Session
details text no longer appears in small bold type. All dropdowns, native or
in-page, look the same. On participant pages, dates and completion badges line up
from one session row to the next.

**How it works**
Controls that share a row size from `var(--control-height)`. The arrow is two
`linear-gradient` triangles (CSP `img-src 'self'` rules out an inline SVG image).

**If something looks wrong after this, check**
- A select without an arrow or with a double arrow → the `select` rule in
  `research.css` (background gradients, `appearance:none`).
- A long session name truncated with "…" in the closed menu at desktop width →
  `.preparation-menu summary>span` (`text-overflow:ellipsis`); the full name stays
  in the open list and its `aria-label`.
- Participant session rows overlapping on narrow screens → the `.session-meta` grid
  and its `display:flex` override at ≤600px.

**Left alone**
Templates, editor.js, the menu option lists, table layouts and the iPad 44px rule's
selectors. Student app styles (`static/main.css`) are untouched.

**Verified**
Screenshots before and after in Chrome at 1440, 768 and 390px of Prepare a session,
Data and history (grade and session view), a participant page and Study settings →
Participants, using simulated data. Test suite in the app image: 432 passed. 5 failures
need Node.js, which the image lacks (logging contract and upload client). The 2
walkthrough tests failed only because `logger/docs` was not mounted, and pass with it.
Not checked on a real iPad.

## 2026-10-20 — Finish discard safety, private error logs and required browser checks

**Type:** fix, infra · **Area:** session, autocomplete, result-viewer, logging, infra, tests, docs

**Files**
- `search-app/research_dashboard/static/editor.js` — discard pauses new autosaves,
  waits for the full pending save/reconciliation, and reloads only after a successful
  clear. A rejected clear leaves the page and text available with error feedback.
- `search-app/search_backend.py`, `search-app/search_app.py` — search/autocomplete
  provider failures log the exception type without raw messages, URLs, credentials,
  queries or tracebacks. Malformed iframe redirect destinations return an unavailable
  probe result, including parsing errors raised inside Requests.
- `search-app/tests/test_editor_browser.py` — delayed-save discard, conflicting
  recovery, expired login, storage failure and network failure regressions; required
  browser mode fails on missing dependencies or browser-launch failure.
- `search-app/tests/test_backend_privacy.py` — synthetic provider 401/429 and private
  exception-message regressions.
- `search-app/tests/test_student_security.py` — malformed redirects through both
  `urljoin` and real Requests redirect preparation, plus route-level logging privacy.
- `.github/workflows/collection.yml`, `search-app/requirements-browser-test.txt` —
  separate required Chromium job with pinned Playwright and matching browser.
- `docs/research_dashboard.md`, `docs/dashboard_integration.md`,
  `docs/codex_handoff.md` — required verification command and updated handoff.

**What changed for researchers and participants**
Discard returns to saved questions only when the server confirms the recovery copy
was cleared. On conflict, expired login or storage/network failure, the current
text stays on screen. Invalid external redirect locations no longer produce a
server error. Autocomplete keeps its existing empty fallback on provider failure.

**If something looks wrong after this, check**
- Discard stays on the editor → inspect the existing conflict/sign-in/failure
  notice; another tab's newer recovery is intentionally preserved.
- Browser CI fails before running → verify the pinned dependency and matching
  Chromium installation; required mode deliberately refuses a silent skip.
- Provider diagnostics contain only an exception class → raw provider text is
  omitted because it can include a participant query or credential.

**Left alone**
Page layout and wording, question publication, participant identity, collection
formats and storage schemas.

**Verified**
449 tests passed in 60.49 seconds, including all 10 real Chromium cases with
`SOL_REQUIRE_BROWSER_TESTS=1` (synthetic data only). Required mode was also checked
without Playwright and without Chromium: both fail rather than skip. JavaScript
syntax, workflow YAML, dependency consistency and diff checks passed. The production
image built successfully with Python 3.14.4 and its pinned runtime dependencies.
The two legacy standalone Selenium suites remain excluded; actual PC/iPad acceptance
and the hosted CI run remain release-environment checks.

## 2026-10-20 — Close edit-protection races, keep forms through login expiry, reliable logout

**Type:** fix · **Area:** session, logging, result-viewer, tests, docs

**Files**
- `search-app/research_dashboard/static/editor.js`
  - Leaving the page waits until the text *currently* on screen is stored. Before, a save already in progress for older text was enough.
  - Text typed while the recovery copy loads is saved, never assumed safe, and is never replaced by a recovered copy (a banner offers the earlier text instead).
  - The login check before submit/retry no longer adopts another tab's recovery version, so a stale tab cannot overwrite or clear a newer copy. A version conflict caused by this tab's own lost response is recognised and resolved.
  - Every guarded form (IDs, session details, enrollment edits, links, promotion) checks the login before submitting. When it has expired, nothing is sent, entries stay and a message offers sign-in in another tab.
  - Back/forward cache restores the leave warning.
- `research_dashboard/security.py` — new `GET /dashboard/session` login preflight (JSON 401 when expired). Logout revokes the session before the optional recovery cleanup.
- `research_dashboard/editor_views.py` — recovery cleanup at logout logs and continues on storage errors.
- `research_dashboard/dashboard.py` — `session_check` answers JSON.
- `research_dashboard/templates/research/base.html` — `data-editor-session-url`.
- `research_dashboard/editor_i18n.py` — 3 messages (EN/IT).
- `research_dashboard/static/editor.css` — form notice spacing.
- `search-app/search_app.py` — malformed viewer addresses (e.g. `http://[x`) redirect to the results instead of a 500.
- `search-app/search_backend.py`
  - `print` calls replaced by a module logger.
  - Corrected queries and autocomplete suggestions are no longer written to process logs (only a count).
  - Vertex failure/misconfiguration raises explicitly. Before, it returned a wrong-shaped tuple that failed by accident; the same "could not connect" page is shown.
- Tests:
  - `test_editor_browser.py` (new, real Chromium; skipped without Playwright). All 5 fail on the previous `editor.js`.
  - `test_question_draft_workflow.py`: logout with a broken store, and the preflight.
  - `test_student_security.py`: malformed URLs, backend logs, explicit Vertex errors.

**What changed for the participant**
No visible change.

**What changed for researchers**
After the 30-minute idle logout, submitting IDs or session details keeps the entries on the page with a sign-in message instead of losing them on the login page.

**If something looks wrong after this, check**
- A guarded form "does nothing" on submit → `/dashboard/session` returned non-200 (message shown above the button).
- Leaving the question editor asks for confirmation → the current text could not be stored after 4 attempts, or another tab changed the copy.

**Left alone**
Recovery store format and server rules, question/settings saving, student logging, page layout (behaviour snapshot identical apart from the new attribute, messages and `editor.js`).

**Verified**
437 automated tests, including 5 real-browser race reproductions (also run 3× for flakiness). The dashboard snapshot (4,000 pages, 56 flows) is unchanged apart from the intended additions. The expired-login message was checked at PC and iPad sizes.

## 2026-10-20 — Security review: escape search results, restrict server probes, drop CORS

**Type:** fix · **Area:** serp, result-viewer, autocomplete, logging, infra, tests, docs

**Files**
- `search-app/templates/search.html` — queries, links and IDs are escaped (`|safe` removed); titles/snippets go through the new `rich_text` filter (text plus `<b>/<strong>/<i>/<em>/<br>` only).
- `search-app/search_app.py` — `rich_text` filter; `/webpage` accepts only http(s) URLs; `/iframe_check` needs an active search and re-validates every redirect hop (max 5); `/autocomplete` needs a participant session; CORS removed; 16 MiB upload limit; `nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: same-origin` on student responses; logging-contract warnings no longer print event contents; prints/tracebacks go to the app logger; dead autocomplete cache and unused imports removed.
- `search-app/search_backend.py` — PyTerrier: query sent as an encoded parameter, 10 s timeout, errors raise (same "could not connect" page as Vertex) instead of returning a 2-tuple that crashed the caller.
- `search-app/templates/layout.html`, `static/main.css` — removed the unused pro/con "saved documents" code from an earlier study.
- `search-app/requirements.txt`, `requirements.lock` — `flask-cors` removed (unused).
- Tests: `test_student_security.py` (new, fails on the previous code); `test_logging_contract.py`, `test_research_dashboard.py` adjusted.

**What changed for the participant**
A query containing `"`, `<` or `&` is now shown and logged exactly as typed. Before, the results event logged it cut off at the first quote (e.g. `la luna "piena"` → `la luna `). None of the 109 queries collected in May contained these characters.

**How it works**
Autoescaping is the default; only `rich_text` returns markup, built from escaped text.

**If something looks wrong after this, check**
- Bold highlights missing in results → engine returned a tag outside the allow-list (`RICH_TEXT_TAGS`).
- Viewer shows "page could not be checked" → `/iframe_check` reasons `no-active-search`, `ssrf-rejected:*`, `too-many-redirects`.
- `413` on upload → batch above 16 MiB (`MAX_CONTENT_LENGTH`).

**Left alone**
Task flow, logger.js, log formats and filenames, dashboard (behaviour snapshot identical), Flask-Session configuration (deprecation warnings only; migrate with the next dependency update).

**Verified**
427 automated tests; new security tests fail on the previous code; browser check on PC and iPad sizes that queries with quotes are logged intact; dashboard snapshot of 4,000 pages and 56 flows unchanged.

## 2026-10-20 — Split the dashboard controller into area modules; fix the always-visible student banner

**Type:** fix, infra · **Area:** styling, session, infra, tests, docs

**Files**
- `search-app/templates/layout.html` — the operator banner "Dati di un partecipante precedente…" had an inline `display:block` that overrode `hidden`, so every student page showed it (since `d6d9357`, 16 May). Removed that declaration.
- `search-app/research_dashboard/__init__.py` — now only wires the modules below (was a 1,050-line closure).
- New: `dashboard.py` (shared context), `security.py`, `template_context.py`, `history_data.py`, `history_views.py`, `export_views.py`, `question_views.py`, `settings_views.py` (one handler per action).
- `editor_views.py`, `preparation_views.py`, `enrollment_views.py` — register on the shared context; recovery store failures answer 503 JSON instead of an error page; no warning is logged for forms saved without the script.
- `state.py` — `validate_settings` split into focused validators (same checks, same order, same error codes).
- `index.py` — run summary task merging/status extracted into helpers.
- `collection.py`, `runtime.py`, `log_store.py`, `study_config.py` — imports at module level, unused import removed, exception chaining.
- `static/research.css`, `static/editor.css` — 9 dead overridden declarations removed; 44px touch targets under `@media (pointer: coarse)` (iPad), mouse layouts unchanged.
- Templates: `enrollment.html` (leave warning on edit/link/promotion forms, reflowed table/form), `settings_participants.html` (reflowed).
- Tests: `test_research_dashboard.py` patches `history_views.capture_log`; new change-history test.

**What changed for the participant**
The orange "previous participant" banner no longer shows on every page; it still appears when old data is actually recovered.

**How it works**
Behaviour preserved: a snapshot of 4,000 dashboard pages and 56 write flows (HTML, redirects, ZIP contents) is identical before and after (ignoring whitespace between tags), and 54 screenshots at PC/iPad/phone sizes are pixel-identical apart from the touch sizing.

**If something looks wrong after this, check**
- A dashboard URL 404s → the route's module is registered in `init_dashboard`.
- Error page instead of JSON for the editor script → `dashboard.JSON_ENDPOINTS`.

**Left alone**
Student routes and logging (except the banner), URLs and endpoint names, storage schemas, templates' output.

**Verified**
416 automated tests; behaviour snapshot and screenshot comparison; student start/question pages on PC and iPad sizes.

## 2026-10-20 — Keep approved questions live while editing, and protect unsaved edits

**Type:** fix · **Area:** session, data, styling, tests, docs

**Files**
- `search-app/research_dashboard/__init__.py` — question editor saves drafts to `question_draft`/`participant_question_drafts` and publishes only on approval; new `discard_draft` action; clears the private recovery copy after a successful save; `question_view` template helper.
- `search-app/research_dashboard/static/editor.js`, `static/editor.css` (new) — unsaved-change warning, private autosave/recovery, re-login with CSRF refresh, save-state line, sticky action bar, menu dismissal (Escape/click outside).
- `search-app/research_dashboard/preparation_views.py` — access status reports missing setup before the schedule.
- `search-app/research_dashboard/state.py`, `participants.py`, `templates/research/audit_changes.html` (new), `enrollment.html` — change history lists affected IDs with before/after values; phone card rows for the register.
- `templates/research/session_questions.html`, `prepare.html`, `session_question_preview.html`, `settings_sessions.html`, `overview_downloads.html` — approved vs draft display, Approve as primary action, download labels.
- `search-app/research_dashboard/editor_i18n.py` — English/Italian wording.
- Tests: `test_question_draft_workflow.py` (new); updated draft-contract expectations in `test_session_draft_visibility.py`, `test_session_question_editor.py`, `test_question_library_choices.py`, `test_session_preparation.py`, `test_preparation_preview.py`, `test_research_dashboard.py`.

**What changed for the participant**
No visible change in the student app. Children are no longer blocked when a researcher saves a draft over approved questions.

**How it works**
See "Question lifecycle" in `dashboard_integration.md`. Admission still reads only `question_set`/`participant_questions`.

**If something looks wrong after this, check**
- Child blocked after editing questions → is the approved `question_set` present and complete? Drafts are in `question_draft`.
- Editor shows "recovered" text unexpectedly → `research-state/editor-drafts.sqlite3`; **Discard recovered edits** clears it.
- Script not running → CSP must allow `script-src 'self'`; `/dashboard/static/editor.js` must be served.

**Left alone**
Student routes, logging, admission (`study_config.scheduled_assignment`), exports and the recovery store's schema.

**Verified**
414 automated tests (Selenium back-navigation tests not runnable in the review environment). Browser checks: language switch recovery, expired login while typing, re-login and approve, draft keeps "Available today", discard, leave warning, phone layouts.

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
