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
`data`, `infra`, `docs`, `tests`, `dashboard`

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

## 2026-11-07 — Back from an introduction no longer starts the question

**Commit:** pending · **Type:** fix · **Area:** study flow

**Files**
- `logger/search-app/search_app.py` — pages a child should not be on send a question not begun to its introduction
- `logger/search-app/tests/test_child_pages.py` — one more case

**What changed for the participant**
The introductions have no logger, so the browser's Back works there. It reached the start page, which sent the child on to `/task`: that skipped the
introductions and logged `TaskStarted`. Back now returns to the introduction, and the question starts only when the child taps "Inizia".

**How it works**
`phase_redirect_url` uses `PROGRESS.entry_url` for a question without a first answer. A question already begun still resumes at its form.

**If something looks wrong after this, check**
- A child who cannot leave an introduction → `entry_url`, and whether `TaskStarted` was stored for that attempt.

**Left alone**
Old runs without a progress record go to `/task` as they did.

**Verified**
Reload, Back and Forward at each step in WebKit and Chromium on the production image: one `TaskStarted` and one `TaskEnded` per question.

## 2026-11-07 — Keep a test ID's unsent choice out of the real log folder

**Commit:** pending · **Type:** fix · **Area:** logging

**Files**
- `logger/search-app/search_app.py` — a batch with no server run goes by whose events it holds
- `logger/search-app/tests/test_permanent_test_experiment.py` — one more case

**What changed for the participant**
No visible change.

**How it works**
The choice of ID is logged before a run has its server ID, and is sent by the next page that has the logger. The new introduction pages do not, so a tester who leaves a test run there
keeps that event in the browser. It was then sent during the next child's run, and with no attempt to look up it went to the real folder. The dashboard ignored the file, so results were not affected. A batch with
no attempt now goes to the test folder when every event in it belongs to a test ID.

**If something looks wrong after this, check**
- `TEST-` files in the top of `logs-v2` → a batch mixing a test ID and a child; the dashboard ignores them.

**Left alone**
Batches of a known attempt, and every batch of a child, which go where they did.

**Verified**
Found by the shared-tablet rehearsal on the production image; the new test covers both directions.

## 2026-11-07 — List May's experiment in Sessions

**Commit:** pending · **Type:** feature · **Area:** dashboard

**Files**
- `logger/search-app/research_dashboard/session_views.py` — `historical_rows`
- `logger/search-app/research_dashboard/templates/research/sessions.html`, `workflow_i18n.py` — the row and its wording
- `logger/search-app/tests/test_session_history_rows.py` — new

**What changed for the participant**
No visible change. Researchers see "Esperimento 19 maggio" per class under Past sessions, linking to its data, instead of "No sessions yet" for 2025/2026.

**How it works**
The rows are read from the historical rules saved by the setup tool. They are not sessions: a May session would take a number and make Tuesday's class 4 Session 2.

**If something looks wrong after this, check**
- No row → `historical_grades` in settings, or the year filter.

**Left alone**
Session numbers, the settings, Data and history. A May run still says "Other saved runs" on a child's page.

**Verified**
Tests for the year, the class filter and the number of IDs, and a look at the page in the rehearsal.

## 2026-11-07 — Match the child pages to Diletta's Figma

**Commit:** pending · **Type:** feature · **Area:** task-flow, styling, session

**Files**
- `logger/search-app/templates/first_answer.html`, `static/first-answer.css`, `static/first-answer.js` — equal buttons, no search button until the answer is confirmed, saved answer as text, sizes that follow the screen height
- `logger/search-app/templates/task_intro.html` — new; "Cominciamo!" and the question introduction
- `logger/search-app/student_progress.py`, `study_progress.py` — `/task/intro`, `entry_url`, `task_started`, theme texts
- `logger/search-app/templates/search_first_answer.html`, `static/main.css` — the first answer pop-up in the layout of the `?` pop-up; Nunito and Poppins
- `logger/search-app/static/fonts/` — new; the Figma's fonts, served from here
- `logger/search-app/templates/study_handoff.html`, `static/study-review.css`, `search_app.py` — the review page as the Figma's "Pieces Unlock"; `static/review-animation-key.svg` removed
- `logger/search-app/templates/recap.html`, `static/recap.css` — the Figma's look over the same functions
- `logger/search-app/static/test-run.css` — the test banner sits in the blue band
- `logger/search-app/tests/test_child_pages.py`, `test_child_pages_browser.py` — new; other tests follow the new labels and steps
- `logger/docs/desktop_interface.md`, `editable_recap.md`, `follow_up_checks.md`

**What changed for the participant**
See `logger/docs/child_pages_2026-11.md`. New steps: "Cominciamo!" at the start of a run and an introduction before each question. Pages fit shorter tablets.

**How it works**
`/start` and the next question lead to `/task/intro` while the question has no `TaskStarted`. `/task` is unchanged and logs `TaskStarted` when it shows the form, so the
introductions log nothing and a question already begun resumes directly. Everything else is templates and styles. Pages load their styles with `?v=child-pages-1` so tablets do not keep old ones.

**If something looks wrong after this, check**
- A button below the screen on a tablet → the `vh` sizes in `first-answer.css` and `--stage` in `study-review.css`; `test_child_pages_browser.py` sets the sizes it guards.
- A child repeating an introduction → `task_started` and `entry_url`.
- Cards in the wrong place on an animation → the `.unlock--` rules and `REVIEW_ARROWS`.

**Left alone**
What is saved and logged, `/first-answer`, the confirmation step of issue #6, recap saving and the PDF, the search page's layout.
Session 3's finish button no longer says "termina lo studio", but it still ends the study.

**Verified**
Full suite with browser tests. Every step measured at 1180 x 699, 1280 x 680, 1024 x 520 and 800 x 1100 in WebKit, and at 1280 x 680 in Chromium. Class, crash, fault and shared-tablet
rehearsals on the production image. Not yet on a real classroom tablet.

## 2026-11-07 — Re-encode the review animations on white

**Commit:** pending · **Type:** content · **Area:** task-flow, styling

**Files**
- `logger/search-app/static/videos/review/*.mp4` — the six clips cropped to their picture, on white, without their silent sound track
- `logger/search-app/static/images/review/{ear,space}-{1,2,3}.webp` — stills, now the last frame of each clip
- `logger/search-app/tools/prepare_review_media.py` — new; makes them from the supplied files

**What changed for the participant**
No black rectangle around the animation on tablets, and the picture is larger. Orecchio 02 and 03 follow the Figma: inside of the ear, then animals.

**How it works**
The supplied 4K clips have a black background, with each picture small and off-centre because it is a piece of the recap picture. A CSS filter hid
the black on a computer and not on the iPad. The tool removes black joined to the frame or filling a large enclosed area, keeping outlines and pupils, and writes the
clip on white, which is the colour of the page behind it. The `SOFT` setting handles the sound waves, which fade out over the black.

**If something looks wrong after this, check**
- A faint box around a clip → the white of the clip against the page: `lutyuv` in the tool.
- The wrong picture for a question → `CLIPS` in the tool, then the question's box in the dashboard.
- An old clip on a tablet → its browser cache: the pages load clips with `?v=child-pages-1`.

**Left alone**
The recap pictures, and which clip goes with which question slot in the code.

**Verified**
Frames of every clip at the start, during and at the end, by eye; browser tests play all six in Chromium. Not yet seen on a classroom tablet.

## 2026-11-06 — Keep the deploy script running after its backup

**Commit:** pending · **Type:** fix · **Area:** infra

**Files**
- `scripts/deploy.sh` — the backup container no longer reads the script's standard input
- `logger/search-app/tests/test_deploy_script.py` — new; runs the remote part from standard input with a fake `docker`
- `logger/docs/follow_up_checks.md` — the fake May logs are gone from the server

**What changed for the participant**
No visible change.

**How it works**
`deploy.sh` sends its remote part to `ssh ... bash -s`, so that part is on standard input while it runs. `docker compose run`
attaches standard input to the container and drained the rest of the script. The remote shell then found nothing more to do and
exited with success, leaving the app stopped, with "Deploy complete" printed and no rollback. The backup itself was fine.
`</dev/null` keeps that one command away from the script.

**If something looks wrong after this, check**
- A deploy that prints "Deploy complete" without "Verified backup" → a step read standard input; the app is stopped, so start it with `docker compose up -d --no-build --wait search_app`.

**Left alone**
Every other step of the deploy, and the backup tool.

**Verified**
Reproduced with real Docker: the line after `docker compose run` did not run from `bash -s`, and did with `</dev/null`. The new test
failed before the fix and passes after it. The first real deploy on 2026-11-06 hit this. The earlier Linux rehearsal ran the remote
part from a file, which hid it, so a deploy rehearsal must feed it through standard input. The fixed script has not yet run on the server.

## 2026-11-06 — Set May's classes from the server's logs

**Commit:** pending · **Type:** infra · **Area:** data, dashboard

**Files**
- `logger/search-app/tools/setup_session_2026_11_10.py` — May is 19 May 2026, class 3 with IDs 1-8, 17, 18 and class 4 with IDs 9-16
- `logger/search-app/tests/test_setup_session_2026_11_10.py` — checks the shipped values, and that other days stay out
- `logger/docs/follow_up_checks.md` — May is set, real search answered from a Mac; the server's own check and Diletta's questions remain

**What changed for the participant**
No visible change.

**How it works**
The server's logs show two class starts on 19 May 2026: IDs 9-16 within 8 seconds at 10:41 and IDs 1-8, 17, 18 within 71 seconds at
14:47. All 18 finished three questions, so no later run is a redo. Only that day is classified and linked to the children, so runs
on other days stay out of the classes, also under a real ID. IDs 19 and 20 have no May run, so they are enrolled for this year only.
The rule works by date, so a test on that same day counts with the class: ID 11 has one at 08:00.

**If something looks wrong after this, check**
- A May run without a class → it is not dated 19 May, or its name is not a numeric ID.
- Class 4 of 2025/2026 shows 8 children → expected; 19 and 20 start this year.

**Left alone**
The May log files. Removing the fake runs from the server is a separate manual step.

**Verified**
The tool's tests on a real `State` and index, with runs on other days under real IDs. The dates, times and finished counts come
from the server's real file list, read by Matthias; the log contents were not read here.

## 2026-11-06 — One-step setup of the 10 November session and May's classes

**Commit:** pending · **Type:** infra · **Area:** data, dashboard

**Files**
- `logger/search-app/tools/setup_session_2026_11_10.py` — new; prepares a fresh dashboard in one step, with `--dry-run`
- `logger/search-app/tests/test_setup_session_2026_11_10.py` — new
- `logger/docs/follow_up_checks.md` — what is still open before the class: real engines, May's dates, test IDs on the server

**What changed for the participant**
No visible change: the start page lists the real IDs once this has run.

**How it works**
On a fresh dashboard it creates Session 1 for class 4 (`spazio`, IDs 1-8, 17, 18) and class 5 (`orecchio`, IDs 9-16, 19, 20),
removes the pre-filled IDs 21-40 and the empty sessions, enrolls the same children a class lower in 2025/2026, and adds
historical rules and identity links for May's records. It writes through the dashboard's validated functions, apart from
deleting the unused IDs. May's files are only read. The tool refuses when it finds a school year, a prepared session, a
child's run, a link or a log, and changes nothing.

May does not appear in the Sessions list. Session numbers run per class across years, so a May session for class 4 would make
Tuesday its Session 2, which changes the recap and ends the study one session early.

**If something looks wrong after this, check**
- "Nothing changed" from the tool → it names what it found; look at that before anything else.
- A May run without a class → its date is outside the tool's May periods, or its name is not a numeric ID.

**Left alone**
Default settings for other installs, the May log files, the dashboard's editors. Test names such as `UserTestLog1` and
`Utente1` stay unclassified and remain under historical records.

**Verified**
16 tests on a real `State` and index, including that May's files stay byte-identical. Rehearsed on the production image.

## 2026-11-06 — Add permanent test IDs that stay out of the results

**Commit:** pending · **Type:** feature · **Area:** session, task-flow, logging, dashboard

**Files**
- `logger/search-app/research_dashboard/permanent_test.py` — new; the two test experiments and their assignment
- `logger/search-app/research_dashboard/collection.py` — a test run's sidecar goes to `test-runs`, marked `is_test`
- `logger/search-app/research_dashboard/state.py` — test attempts skip session checks and same-day resume
- `logger/search-app/research_dashboard/index.py` — a test ID's file is never read as a child's
- `logger/search-app/search_app.py` — a second `LogStore` for test runs, `/test-run/restart`, test IDs on the start list
- `logger/search-app/student_progress.py` — progress events of a test run go with its logs
- `logger/search-app/templates/test_run_banner.html`, `logger/search-app/static/test-run.css` — new; PROVA banner, included in the four page shells
- `logger/search-app/tests/test_permanent_test_experiment.py` — new
- `logger/docs/research_dashboard.md`, `logger/docs/production_readiness.md` — what the IDs do and where their logs are

**What changed for the participant**
`TEST-spazio` and `TEST-orecchio` appear at the end of the ID list. A child's own pages do not change: the banner and its
stylesheet exist only in a test run.

**How it works**
Choosing a test ID makes a one-person session on the spot, with a new session ID each time, so every start is a new attempt.
It needs no enrollment or settings. Its uploads, sidecar and progress events go through a separate `LogStore` in
`logs-v2/test-runs`. The dashboard scans only the top of `logs-v2`, so test runs are out of the results by where they are
written, not by a filter. Unsent batches are routed by the attempt they belong to, not by who is using the browser.

**If something looks wrong after this, check**
- A child's logs missing from the dashboard → look in `logs-v2/test-runs`; a test ID may have been chosen, and the PROVA banner would have shown.
- `TEST-` files in the top of `logs-v2` → events of a test run inside a child's batch; the dashboard ignores them.
- A start page without test IDs → an image older than this commit.

**Left alone**
The children's admission, `scheduled_assignment`, `LogStore` itself and the event format. Events of a real run gain no field,
which is why the banner reads the session and not `study_context`, whose content goes into every logged event.

**Verified**
12 new tests: any day with no session, a whole run through the recap with nothing in the real folder, no receipt journal
created there, results and resume lists beside a real child, repeated restarts, a double tap, unsent batches in both
directions, a pending sidecar. Rehearsed on the production image with 20 children at once.

## 2026-11-06 — Choose the search engine from the session's theme

**Commit:** pending · **Type:** feature · **Area:** serp, autocomplete, infra

**Files**
- `logger/search-app/search_backend.py` — `load_theme_configs`, `vertex_config_for`; `search` and `autocomplete` take the run's theme
- `logger/search-app/search_app.py` — `run_theme` reads the theme frozen in the run; `known_theme` shared with the recap pictures
- `logger/docker-compose.yml` — passes `VERTEX_SPAZIO_*` and `VERTEX_ORECCHIO_*`
- `logger/search-app/tools/check_search_engines.py` — asks each engine one real question before a session
- `logger/search-app/tests/test_search_by_theme.py` — new; test doubles of the backend accept the theme
- `logger/docs/production_readiness.md` — how to set the engines on the server

**What changed for the participant**
A class searches the dataset of its own theme: spazio and orecchio can use different engines on one server.

**How it works**
The theme comes from the question set frozen when the run started, the same text that chooses the animations. Once any
per-theme engine is set, a theme without its own engine raises an error, so the child sees the search error page and the
server logs it, rather than results from another dataset. Autocomplete then returns no suggestions.

**If something looks wrong after this, check**
- Search error page for one class only → that theme's `VERTEX_*_ENGINE_ID` in `logger/.env`, or a theme text the app does not recognise.
- `PermissionDenied` in the logs → the service account has no role on the engines' project.
- No Vertex suggestions for one class → that theme's `VERTEX_*_DATA_STORE_ID`.

**Left alone**
What is logged per event, the result handling in `vertex_search`, the PyTerrier backend and the SerpAPI fallback, which has
no dataset. A single engine still works with no new setting.

**Verified**
Tests with fake clients check the engine and data store each theme reaches and that no call happens without one, and
real student routes check the theme passed, including after resuming in a new browser. A real query from a Mac reached Google,
but was refused for this service account's missing permission, so real results per engine are still unverified.

## 2026-11-06 — Fit the tests to the combined release

**Commit:** pending · **Type:** infra · **Area:** tests, task-flow, dashboard

**Files**
- `logger/search-app/tests/test_live_view.py` — the real-run test confirms a first answer and sends a complete final answer
- `logger/search-app/tests/test_first_answer_flow_browser.py` — the expected recap picture now depends on the theme; waits for the search page
- `logger/search-app/tests/test_search_first_answer_browser.py` — waits for the search page before tapping the button
- `logger/search-app/tests/test_final_answer_draft_browser.py` — waits for the search page and the viewer before tapping

**What changed for the participant**
No visible change. Only tests changed.

**How it works**
The live view and recap tests passed on their own branches and failed only once dashboard v2, the question flow and the
recap were merged together. #23 refuses a final answer without its attempt and question, and the server now logs the start of a
task itself, so the live view test takes its times from the real run. It also checks that a finished question shows a
time instead of "—". The recap test expected the space picture for both themes.

The other two were intermittent: they tapped "La mia prima risposta" or "Scrivi la risposta" while the page was still
loading, before the button's handler existed. They now wait for the page, as the other browser tests do.

**If something looks wrong after this, check**
- A live view showing "—" for time on the real flow → `started_at` and `ended_at` in `research_dashboard/task_stats.py`.

**Left alone**
A tap on those buttons while the page is still loading still does nothing, and a second tap works. Nothing is logged or
lost and a saved draft stays, so the app was not changed days before a session.

**Verified**
Two throwaway tests confirmed the cause. With `logger.js` held back, an early tap did nothing and a tap after loading
opened the dialog. In 40 runs of the draft flow, 9 first taps were lost with `openFeedbackModal is not defined`, and
every second tap opened the box with the draft still there. Real iPads were not part of this.

## 2026-11-06 — Run the deploy backup in a container

**Commit:** pending · **Type:** fix · **Area:** infra, docs

**Files**
- `scripts/deploy.sh` — the backup step runs in a one-off container and hands the archive to the checkout's owner
- `logger/docs/production_readiness.md` — the same command for manual backups; check out the new code before the first upgrade

**What changed for the participant**
No visible change.

**How it works**
The container runs as root and writes logs, databases and `password.hash` private to root. `deploy.sh` ran the
backup as the operator's own account, which cannot read them, so on a Linux server the first deployment stopped
collection, failed with `PermissionError`, and rolled back to the old image. Docker Desktop on a Mac maps ownership
to the signed-in user, and CI backs up as root, so neither showed this. Rehearsed on a real Linux filesystem with a
non-root operator (Docker-in-Docker): first upgrade, redeploy during a class, failed release, recovery.

**If something looks wrong after this, check**
- Deploy fails at "Taking a consistent backup" → `docker compose run` output; the new image must contain `tools/backup_study.py`.
- A backup archive owned by root → the `chown` in the same step, and who owns `logger/`.

**Left alone**
`backup_study.py` itself. A rollback during the first upgrade still starts the old image with `logs-v2` mounted (see
`follow_up_checks.md`).

## 2026-11-06 — Keep events a browser could not send when an ID is entered again

**Commit:** pending · **Type:** fix · **Area:** logging, session

**Files**
- `logger/search-app/static/logger.js` — `setAsideUnsent` and `sendUnsentRuns`; `clearClientData` keeps what was set aside
- `logger/search-app/tests/test_unsent_events_browser.py`, `tests/test_upload_client.py` — new tests

**What changed for the participant**
No visible change.

**How it works**
Entering an ID cleared all browser storage, including events and a pending batch that had not reached the server. If
uploads were failing when a run was left, those events were lost once anyone entered an ID on that tablet: 14 events in
each rehearsal. They are now set aside and sent under their own run's ID, reusing the batch ID so a retry cannot write
them twice. The same run's events go to its full log. Another child's go to that child's existing `_INCOMPLETE.log`
recovery file. Sending is separate from `sendLogs`, so a refused old batch never holds up the current run.

**If something looks wrong after this, check**
- `solUnsentRuns` staying in localStorage → the server refused that batch; the browser console and `/log_session` responses.
- An unexpected `_INCOMPLETE.log` → the run was left while uploads were failing; its events carry `recovered: true`.

**Left alone**
Server upload handling and log formats. A batch the server permanently refuses still blocks later uploads from the
*current* run (see "same ID on two tablets" in `follow_up_checks.md`).

## 2026-11-06 — Keep dashboard pages working beside the student flow

**Commit:** pending · **Type:** fix · **Area:** dashboard

**Files**
- `logger/search-app/research_dashboard/dashboard.py` — `page` always passes its own `study_context`
- `logger/search-app/tests/test_guide.py` — new test

**What changed for the participant**
No visible change.

**How it works**
The student flow in PR #23 adds `study_context` to every template, empty outside a run. Dashboard pages that set none
inherited that empty value and crashed in `base.html`. With both in one app, the first sign-in landed on "Server
Error" (the guide), and the trash page and dashboard error pages returned 500. Tests did not catch it because their
test apps do not load both together.

**If something looks wrong after this, check**
- A dashboard page returning 500 only on the deployed app → `study_context` in `base.html`, and the context processors in `student_progress.py`.

**Left alone**
The student flow's own value and templates.

## 2026-11-06 — Re-check dashboard v2 against the researcher feedback of 3 November

**Commit:** pending · **Type:** fix · **Area:** dashboard, styling, docs, tests

Matthias asked for v2 to be checked against the colleague's PDF and screen recording, and spotted that finding an
ID still meant typing it. In the recording the colleague says they do not know which IDs belong to which class and
asks for a list instead.

**Files**
- `search-app/research_dashboard/templates/research/enrollment.html`, `enrollment_views.py` — **Cerca un ID** is a
  menu of every ID in the study with its class this school year, on **Modifica gli ID** and under Participants. The
  school-year filter under Participants is a menu too. An ID that arrives in the URL and is not in the study stays
  selected, so its message still shows.
- `search-app/research_dashboard/templates/research/overview.html`, `static/editor.js`, `static/research.css` —
  **Vai all'ID partecipante** in Data e storico is a menu of the IDs in the view.
- `search-app/research_dashboard/templates/research/prepare.html`, `i18n.py` — brings back the subtitle "Stai
  modificando…" that the colleague asked for and the first v2 commit had dropped.
- `search-app/research_dashboard/templates/research/sessions_new.html`, `session_views.py` — **Crea** asks for name
  and date first, then the class. No class is preselected unless the list was filtered to one.
- `search-app/research_dashboard/session_views.py` — the list opens on the later of the saved current year and the
  year of today's date, and a session dated today stays listed under any selected year.
- `search-app/research_dashboard/static/sessions.css` — a draft in the list has the warning colour and triangle.
- `search-app/research_dashboard/templates/research/base.html` — new version in the style links.
- `search-app/research_dashboard/guide_i18n.py`, `static/guide/` — text and pictures follow the new form.
- `search-app/tests/test_dashboard_feedback.py`, `test_participant_jump_browser.py`, `docs/research_dashboard.md`,
  `docs/follow_up_checks.md`.

**What changed for the participant**
No visible change for children.

**How it works**
All three ID and year controls are native `select` elements using the same request parameters as before, so links
and the messages saying where a hidden ID is work unchanged. Options come from `participant_registry`.

**If something looks wrong after this, check**
- An ID is missing from **Cerca un ID** → `participant_registry` in the settings.
- An ID is missing from **Vai all'ID** → the class, year and session selected in that view.
- Today's session is not listed → the class filter, or `date` on the session.

**Left alone**
The student app. The combined **Aggiungi o iscrivi ID** form, kept on purpose on 3 November: it is what the pop-up
links fall back to without JavaScript. **Domande approvate** and **Approva domande** in the question editor, as
decided for v2. Typing IDs when creating new ones, since those IDs do not exist yet.

**Verified**
A walk through every point of the PDF and recording in a real browser on the demo data, the full suite with browser
tests, and the changed pages at 1280, 768 and 320 px in both languages. Not tested on a real iPad.

A trial merge with PRs #21, #22, #23 and #26 found small clashes in `state.py`, `settings_views.py` and this file.
With them, `test_a_real_student_run_reaches_the_live_view` must change: it uploads `TaskEnded` directly, which the
progress code of #23 refuses outside the real steps. A real child through all three questions in a browser on that
merge did reach the live view at every step.

## 2026-11-05 — Rebuild the sign-in destination from the dashboard prefix

**Commit:** pending · **Type:** fix · **Area:** dashboard, tests

**Files**
- `search-app/research_dashboard/dashboard.py` — `safe_research_next` returns a path built from `PREFIX` and the
  parsed path and query, not the text it received.
- `search-app/tools/capture_guide_screens.py` — the reason moves to its own line, with a bare `NOSONAR` on the
  `Flask(__name__)` line, because SonarCloud did not honour the comment with text after it.
- `search-app/tests/test_dashboard_redirects.py` — covers the rebuilt value.

**What changed for the participant**
No visible change. A destination with a leading space or a fragment now loses them; the dashboard's own links have
neither.

**How it works**
SonarCloud's open redirect finding on PR #25 traces the input through `safe_research_next` as if unchanged. Returning
a value built from the constant prefix makes the guarantee part of the function's result.

**If something looks wrong after this, check**
- A sign-in link loses its `#fragment` → this function. Dashboard pages do not use fragments in `next`.

**Left alone**
What the function refuses, which the previous entry describes.

**Verified**
See the pull request: the full server suite, Ruff, and a new test for the rebuilt value.

## 2026-11-05 — Keep the sign-in redirect inside the dashboard

**Commit:** pending · **Type:** fix · **Area:** dashboard, tests

**Files**
- `search-app/research_dashboard/dashboard.py` — `safe_research_next` also refuses dot segments, doubled
  slashes and encoded backslashes in the path, encoded forms included.
- `search-app/research_dashboard/security.py` — `login` compares the destination with the Sessions page to
  decide whether the guide opens, instead of keeping a second variable.
- `search-app/tools/capture_guide_screens.py` — the throwaway server gets a random password and secret key on
  each run. Its `Flask(__name__)` line carries a `NOSONAR` comment, with the reason.
- `search-app/tests/test_dashboard_redirects.py` — the new refusals, and a check that the query string is not
  inspected.

**What changed for the participant**
No visible change. For researchers, a crafted sign-in link such as `/dashboard/../welcome` now opens the Sessions
page instead of a page outside the dashboard. Normal links are unaffected.

**How it works**
A browser resolves `..`, including `%2e%2e`, before requesting a page, so a path that starts with `/dashboard/`
could still end up elsewhere on the same site. No tested link reached another site, before or after this change.
Found while checking SonarCloud's open redirect finding on PR #25, which also failed the quality gate on the tool's
fixed password.

**If something looks wrong after this, check**
- A sign-in link lands on Sessions instead of the page asked for → `safe_research_next`; does its path contain `//`
  or a dot segment?
- A brand-new browser signing in with `next` set to exactly the Sessions page opens the guide. That is intended:
  it is the same destination as no link at all.

**Left alone**
The rule that the first sign-in opens the guide, the login throttling and the session handling. The guide's
pictures were not regenerated, because the tool's output does not depend on the password.

**Verified**
See the pull request: the redirect and guide tests, the full server suite, Ruff, and the tool run into a temporary
folder.

## 2026-11-05 — Document dashboard v2

**Commit:** pending · **Type:** content · **Area:** docs

**Files**
- `docs/research_dashboard.md` — new section on Sessions, the live view, statistics and the guide; the
  header, setup steps, session removal and Study settings follow the new layout.
- `docs/dashboard_integration.md` — module table and entry routes.
- `docs/local_ui_development.md` — the collection walkthrough uses the new pages. Also corrects a stale
  line that said unfinished work is not uploaded periodically: it is, at least once a minute.
- `docs/follow_up_checks.md` — new item: check the live view with a real class and the new controls on an iPad.

**What changed for the participant**
No visible change.

**Left alone**
Historical verification notes, which describe what was true when they were written.

**Verified**
Each changed statement was checked against the code. Documentation only: no tests were run for this commit.

## 2026-11-05 — A guide for new researchers

**Commit:** pending · **Type:** feature · **Area:** dashboard, docs, tests

**Files**
- `search-app/research_dashboard/guide_views.py`, `guide_i18n.py`, `static/guide.css`,
  `templates/research/guide.html` (new) — `/dashboard/guide`, in English and Italian.
- `search-app/research_dashboard/static/guide/{en,it}/*.jpg` (new) — screenshots of demo data only.
- `search-app/tools/capture_guide_screens.py` (new) — regenerates those pictures in a throwaway dashboard.
- `search-app/research_dashboard/security.py` — the first sign-in in a browser opens the guide.
- `search-app/research_dashboard/templates/research/base.html` — a Guide button next to Study settings.
- `search-app/research_dashboard/task_stats.py`, `templates/research/task_stats.html` — a chart's last
  value now sits on its column.
- `search-app/research_dashboard/static/sessions.css` — the header utilities take their own row on phones.
- `search-app/tests/test_guide.py`, `test_guide_browser.py` (new); first-login expectations updated.

**What changed for the participant**
No visible change.

**What changed for researchers**
The first sign-in in a browser opens an illustrated guide to the dashboard, with a way straight to
Sessions. Afterwards the Guide button on every page brings it back.

**How it works**
A cookie on the dashboard path remembers that this browser has seen the guide. Sign-ins are shared,
so this is per browser, not per person. A sign-in that was asked to go to a specific page goes there.

**If something looks wrong after this, check**
- A picture shows an old layout → run `python tools/capture_guide_screens.py` and commit the images.
- The guide opens every time → the browser is not keeping the `sol_guide_seen` cookie.

**Left alone**
Sign-in rules and session lifetime. The pictures are public static files, like the other dashboard
assets, because they contain demo data only.

**Verified**
Server and browser test suites pass (counts in the commit message). All pictures load in both
languages at 1365, 768, 390 and 320 px with no sideways scrolling.

## 2026-11-05 — Live view of a running session

**Commit:** pending · **Type:** feature · **Area:** dashboard, logging, tests

**Files**
- `search-app/research_dashboard/live.py` (new) — reads started attempts and each attempt's `_FULL.log`.
- `search-app/research_dashboard/live_views.py` (new) — `/dashboard/sessions/<id>/live` and `live.json`.
- `search-app/research_dashboard/static/live.js` (new) — checks every 5 seconds and updates rows in place.
- `search-app/research_dashboard/templates/research/session_live*.html` (new) — the page, its rows and totals.
- `search-app/research_dashboard/state.py` — read-only `session_attempts`.
- `search-app/research_dashboard/collection.py` — `safe_participant`, shared with `publish_metadata`.
- `search-app/research_dashboard/dashboard.py` — the data route answers failures as JSON.
- `search-app/research_dashboard/templates/research/{sessions,prepare}.html` — links to the live view on the day.
- `search-app/research_dashboard/{stats_i18n,task_stats}.py`, `static/stats.css`, `templates/research/task_stats.html` — wording and layout.
- `search-app/tests/test_live_view.py`, `test_live_view_browser.py` (new).

**What changed for the participant**
No visible change. The children's app, its uploads and its logs are untouched.

**What changed for researchers**
On the day of a session, Sessions and the session page link to a live view: class totals, one row
per child (Not started, In progress, Completed, current question, questions finished, last save)
and the class question by question. Opening a child shows the figures of each finished question;
a question in progress only says since when.

**How it works**
Short polling, because the server has 8 request slots shared with the children and a push stream
would hold one per viewer. The page checks every 5 seconds and stops while its tab is hidden. It
reads files directly and never through the reporting index. Each worker re-reads a log only when
its size or time changes. Nothing is written.

**If something looks wrong after this, check**
- A finished question does not appear → did `/log_session` accept `TaskEnded`? Then `_read_log`.
- A child stays Not started → is there a row in `study_attempts` for that session?
- A researcher stays signed in with the page open → expected while the tab is visible; the 8-hour limit applies.
- Researcher pages slow during class → `session_progress`, and how many live pages are open.

**Left alone**
Issue #17 stays open: it asks for 1-2 second push built on Samuele's progress work (PR #23), which
this does not do. `TaskEnded` is unchanged on that branch, so this keeps working after it merges;
its question phases can then be added in `live.py`.

**Verified**
Server and browser test suites pass (counts in the commit message). One test goes through real
admission and the real upload route. In a browser with a real student page on synthetic data, a
finished question appeared within 5 seconds, and the figures matched the raw log by hand. Not
tried on a real iPad or with a full class.

## 2026-11-05 — Task statistics for each child, each question and across sessions

**Commit:** pending · **Type:** feature · **Area:** dashboard, data, tests

**Files**
- `search-app/research_dashboard/task_stats.py` (new) — counts one task's events; class rows by
  question; a child's totals by session; chart geometry; time formatting.
- `search-app/research_dashboard/index.py` — stores the figures per file and per run; index version 3,
  so already indexed files are read again once.
- `search-app/research_dashboard/history_views.py`, `template_context.py` — pass them to the pages.
- `search-app/research_dashboard/templates/research/task_stats.html` (new) — tables and charts, used by
  `participant.html`, `overview.html` (when a session is selected) and `run.html`.
- `search-app/research_dashboard/static/stats.css`, `stats_i18n.py` (new), `i18n.py`, `base.html`.
- `search-app/tests/test_task_stats.py`, `test_task_stats_pages.py` (new).

**What changed for the participant**
No visible change. Nothing the children do is logged differently.

**What changed for researchers**
A child's page shows, for each question: time, logged events, searches, results opened, time on
pages and difficulty signals, plus totals and small charts across sessions. A session in Data and
history shows the class by question: how many finished, typical time with range, events, searches
and results. A run's page shows the same figures for that run.

**How it works**
Time runs from the first `TaskStarted` to the first `TaskEnded`. Questions are grouped by what was
asked, because order is shuffled per child. In class figures each child counts once per question,
using their latest run that finished it. A count of 0 means none were logged; a dash means there
was nothing to measure. Runs made only of recovered fragments are left out.

**If something looks wrong after this, check**
- A figure looks off → compare with the run's events, then `add_event` and `COUNTED_EVENTS`.
- Time is a dash → the task has no `TaskStarted` or `TaskEnded`, or their timestamps can't be compared.
- A question appears twice in the class table → its text differs between children (edited after approval).
- The first page load after upgrading is slow → the index is reading every log again, once.

**Left alone**
Original logs and everything in exports: the figures are not added to manifests or metadata.

**Verified**
Server and browser test suites pass (counts in the commit message). Figures checked against
synthetic logs by hand, including text ranks as the student app logs them. English and Italian
at desktop and phone width.

## 2026-11-05 — Deactivate several children at once

**Commit:** pending · **Type:** feature · **Area:** dashboard, tests

**Files**
- `search-app/research_dashboard/participants.py` — `deactivate_participants`, one audit line per ID.
- `search-app/research_dashboard/state.py`, `enrollment_views.py` — the `deactivate` operation,
  using the same signed review step as the other participant changes.
- `search-app/research_dashboard/templates/research/enrollment.html` — checkboxes on the list,
  "Select all on this page", "Deactivate selected".
- `search-app/research_dashboard/static/editor.js`, `workflow.css`, `workflow_i18n.py` — selection count, layout, wording.
- `search-app/tests/test_bulk_deactivate.py`, `test_bulk_deactivate_browser.py` (new).

**What changed for the participant**
No visible change. A deactivated child cannot start new sessions, exactly as with one-at-a-time.

**What changed for researchers**
On the participant list (from Study settings, or Edit participant IDs on a session) they can tick
children and deactivate them after one review. Reactivating is still one child at a time.

**How it works**
All selected IDs change in one transaction. If any ID is unknown or already inactive, or the
settings changed since the review, nothing changes. Selection covers the visible page of up to 50.

**If something looks wrong after this, check**
- A child is missing from a session's IDs → status filter on the list, then "Recent participant changes".
- The select-all box is missing → it needs JavaScript; single checkboxes work without it.

**Left alone**
Enrollments, participant keys, logs and started attempts. The single Edit enrollment form.

**Verified**
Server and browser test suites pass (counts in the commit message). Browser tests use synthetic
data, with a mouse on desktop and at phone width without JavaScript. Not tried on a real iPad.

## 2026-11-05 — Dashboard v2: session list, Create, and the Published status

**Commit:** pending · **Type:** feature · **Area:** dashboard, session, styling, tests

**Files**
- `search-app/research_dashboard/session_views.py` (new) — `/dashboard/sessions` (the list, now
  the start page, with remove and restore) and `/dashboard/sessions/new` (Create).
- `search-app/research_dashboard/preparation_views.py` — `session_group`, `session_needs`,
  `is_placeholder`, `save_session_details`; `preparation_status` no longer calls a partly
  ready future session scheduled; `/prepare` without a session redirects to the list.
- `search-app/research_dashboard/settings_views.py` — session administration removed; Study
  settings keeps School year and Participants. `/settings?section=sessions` redirects.
- `search-app/research_dashboard/templates/research/` — new `sessions.html`, `sessions_new.html`,
  `sessions_tabs.html`, `session_needs.html`; `prepare.html` loses the year/class/session menus
  and gains "Back to Sessions" and "Remove session"; `settings_sessions.html` and
  `settings_session_form.html` deleted; links elsewhere point to the list.
- `search-app/research_dashboard/{i18n,workflow_i18n}.py` — Published/Draft wording, unused keys removed.
- `search-app/research_dashboard/static/` — new `sessions.css`; rules of the old menus and
  session tab removed from `research.css`.
- `search-app/tests/` — new `test_session_list.py`; tests of the old tab moved to the new routes.

**What changed for the participant**
No visible change. Who can start, and when, is decided exactly as before.

**What changed for researchers**
They land on a list grouped into Today, Published, Drafts, and collapsed Past and Removed. A
session is Published when it has a future date, IDs and approved questions for every child;
it is never set by hand. Drafts say what they still need, each linking to its step. Opening a
session shows the same three steps as before, with a back link instead of menus.

**How it works**
The status is computed on each request from `session_readiness`; nothing new is stored. The
list reads settings only, not the reporting index, so a cache failure cannot block it. Numbered
slots nobody has filled in are hidden, and Create fills the lowest free one for that class, so
a new study starts empty and its first session is Session 1.

**If something looks wrong after this, check**
- A session sits in the wrong group → `session_group`, then `session_readiness` for that session.
- "Needs" names the wrong step → `session_needs`.
- A session seems to be missing → the year filter, or `is_placeholder` (no date, name or questions).
- An old bookmark lands in the wrong place → the redirects in `settings_page` and `prepare_page`.

**Left alone**
Student routes, admission (`scheduled_assignment`, `admit_attempt`), question approval and its
"Approve" wording, enrollment, exports and stored settings. The old range editor keeps its URL.

**Verified**
Server and browser test suites pass (counts in the commit message). Checked in a browser on
synthetic data in English and Italian at 1440, 390 and 320 px, with no sideways scrolling.

## 2026-11-05 — Dashboard v2: two main sections, Study settings beside EN/IT

**Commit:** pending · **Type:** feature · **Area:** dashboard, styling

**Files**
- `search-app/research_dashboard/templates/research/base.html` — the main navigation is
  Sessions and Data and history; Study settings moved to the header utilities, before EN/IT.
- `search-app/research_dashboard/static/research.css` — current-page style for the header
  link; the rule for the old third navigation item is gone.
- `search-app/research_dashboard/{preparation,question,enrollment}_views.py` — the area
  behind the navigation highlight is now called `sessions`.
- `search-app/tests/` — navigation tests follow the new labels.

**What changed for the participant**
No visible change. Researchers see two main sections instead of three.

**How it works**
Only navigation moved. "Sessions" still opens the preparation page; the session list
follows in the next commit.

**If something looks wrong after this, check**
- No section highlighted in the header → the view's `research_area` value.

**Left alone**
All routes and pages, including `/dashboard/settings`, which still has its Sessions tab.

**Verified**
The server test suite passes. The narrow-width layout is reviewed with the session list.
## 2026-11-05 — Update desktop interface verification for background uploads

**Commit:** pending · **Type:** fix · **Area:** tests, logging

The isolated `tests/ui_fixture.py` echoes the batch identifier expected by the
logger. The desktop keyboard and touch scripts now inspect submitted events
through that acknowledgement. All seven keyboard scenarios, both touch
orientations and 42 layout checks passed in Chromium.

## 2026-11-05 — Refine answer dialogs and animate question review

**Commit:** pending · **Type:** feature · **Area:** task-flow, styling, tests

**Files**
- `search-app/static/first-answer.js`, `final-answer-draft.js`, `main.css` and `templates/layout.html` keep routine saves quiet, surface errors and fit the answer actions on one row.
- `search-app/search_app.py`, `templates/study_handoff.html`, `static/study-review.css` and `study-review.js` select and play each question's animation beside the existing answer comparison.
- `search-app/static/videos/review/` contains the six supplied MP4s.
- Student browser tests and `desktop_interface.md` cover the connected flow and record before and after captures.

The animation uses the theme and original question position saved for the
attempt. Inline playback is muted and honors the browser's reduced-motion
setting. The recap uses its static theme image. If a clip looks wrong, compare
the attempt's assigned theme and topic ID with the matching file in
`static/videos/review/`. For draft recovery, use the inline error and retry
control. [Desktop and tablet verification](desktop_interface.md)
## 2026-11-06 — Validate recap autosave acknowledgements

- Advance the locally tracked draft revision only when the server confirms
  the expected revision. Keep the draft available to retry after a malformed
  acknowledgement.

## 2026-11-06 — Preserve recap access across the browser handoff

- Require the browser's completed third-question review before showing,
  editing or downloading the recap. A fresh browser that selects the same
  completed ID sees the completion message.
- Align the connected-flow and enrollment tests with the new recap and
  verify that the same browser can download the durable PDF from another worker.

## 2026-11-05 — Add editable session recap and saved PDF

**Type:** feature · **Area:** participant recap, persistence, logging

- Show completed sessions in three independently navigable columns with the
  original question order, saved initial confidence and final-answer revisions.
- Commit edits from every card together and save the final PDF in the progress
  database before exposing download and return to welcome.
- Record recap edits and per-session finish in the durable outbox. See
  [recap behavior and storage](editable_recap.md).

## 2026-11-05 — Complete progress history contracts and retire puzzle rewards

**Commit:** pending · **Type:** feature · **Area:** task-flow, reward, data, logging, tests

**Files**
- `search-app/study_progress.py`, `student_progress.py` — schema 6 recap drafts/revisions, repeat receipts, session lifecycle events and stale-page/start-failure recovery.
- `search-app/search_app.py`, templates, `static/main.css` — remove the reward route, reveal controls and styles; retain task review and neutral completion/close events.
- `search-app/static/puzzle_pieces/*`, `templates/reward.html` — remove obsolete reward media and page.
- `search-app/research_dashboard/student_config.py`, `settings_views.py`, `study_config.py`, `i18n.py` — question sets no longer require reward assets; historical metadata remains readable.
- Progress/history/retirement/logging tests, restart smoke and `issue6_handover.md` — acceptance coverage and API handover.

**What changed for the participant**
The three-question flow contains no reward page or puzzle. An old browser's completed questions still continue safely. Concurrent advancement and a transient TaskStarted save failure remain recoverable.

**How it works**
Recap edits are append-only records with original before/after text, timestamp and verified editing context. Revision counters remain monotonic after draft confirmation, rejecting delayed autosaves. The internal repeat API atomically retires the old attempt and copies its exact snapshot/order into a fresh run with an idempotent authorization receipt. These are storage contracts for the separate #9/#15 interfaces. Identical pre-upgrade first-answer retries keep their historical null confidence. Completion and explicit closure publish through the durable outbox before success/clear.

**If something looks wrong after this, check**
`recap_draft_revisions` when restoring inactive drafts, new technical/log IDs when integrating #15, and the once-only TaskStarted/session events in FULL/per-task logs. A missing asset must not block enrollment.

**Left alone**
Recap/PDF/save-session UI, researcher reset authorization UI, autocomplete, MP4 and layout/autosave-label changes. The existing illustrated read-only handoff is retained.

**Verified**
Full server suite: 722 tests passed; current focused history/confidence checks: 40 passed. The complete required Chromium suite passed 116 tests. Ruff and JavaScript syntax passed. New-process restart, offline backup/restore and restored-process verification passed with confidence preserved. Desktop/tablet screenshots were inspected. Independent review findings were reproduced and fixed; real iPad Safari and local Docker replacement were not tested locally.

## 2026-11-05 — Collect the child's initial self-assessment from Figma

**Commit:** pending · **Type:** feature · **Area:** task-flow, styling, tests

**Files**
- `search-app/templates/first_answer.html`, `static/first-answer.js`, `static/first-answer.css`, `static/confidence/*.svg` — accessible assessment options and original Figma stars.
- `search-app/tests/test_initial_confidence_browser.py` and browser setup helpers — visibility, reset, restore, unknown and responsive checks.

**What changed for the participant**
“Secondo te, quanto è giusta la tua risposta?” appears immediately when an answer contains text. The child selects “Poco giusta”, “Abbastanza giusta” or “Giustissima” before confirming. Clearing the text resets the selection. “Non lo so” retains its separate confirmation.

**How it works**
Native radios share the existing revisioned draft save and recovery buffer. Acknowledgements compare both text and assessment so a change made during a save cannot disappear.

**If something looks wrong after this, check**
The first-answer draft's confidence and browser recovery buffer, and loading of the two local star SVGs.

**Left alone**
Autosave labels, search/final-answer button layouts, recap/PDF, MP4 and researcher restart interfaces.

**Verified**
19 required Chromium first-answer/search/upload regressions passed. Assessment controls fit desktop, portrait/landscape tablet and 320px widths. Real iPad Safari is not available in this environment.

## 2026-11-05 — Persist initial confidence with the first answer

**Commit:** pending · **Type:** feature · **Area:** task-flow, data, logging, tests

**Files**
- `search-app/study_progress.py`, `search-app/student_progress.py` — schema 5 migration, validated confidence, revisioned drafts and canonical events.
- `search-app/tests/test_initial_confidence.py` and first-answer/progress setup helpers — atomicity, retries, concurrency, upgrade and route contracts.

**What changed for the participant**
Typed first answers require a confidence assessment. Confirmed “Non lo so” records no confidence.

**How it works**
The integer confidence (1/2/3) is stored with the original answer, search phase and outbox event in one transaction. Drafts store text and confidence under the same revision. Old measurements remain null and existing outbox events are preserved.

**If something looks wrong after this, check**
The configured progress database's schema version and the `confidence` field in `OwnKnowledgeAnswerSubmitted`. Conflicting confidence on a retry must return 409.

**Left alone**
Final answers, recap/restart interfaces, autocomplete and deployment dependencies.

**Verified**
104 focused persistence/route/event tests passed before the UI increment; additional migration and browser checks passed with that increment.

## 2026-11-05 — Add the illustrated participant review on tablets

**Commit:** pending · **Type:** feature · **Area:** styling, task-flow, tests

**Files**
- `search-app/templates/study_handoff.html`, `search-app/static/study-review.css` —
  clarify the comparison, stack answers on narrow screens, and align the three
  questions side by side in the landscape recap.
- `search-app/static/study-review.js` — remove the print action from the recap.
- `search-app/static/images/review/` — the six task images and two recap images
  from the Diagrammi page of Attività Lambertenghi 2026-2027, optimized for tablets.
- `search-app/search_app.py` — select artwork from the saved theme and original
  topic position so it follows the question when the display order changes.
- `search-app/tests/test_first_answer_flow_browser.py` — cover the narrow comparison
  and the landscape recap in the complete three-question flow.
- `search-app/tests/test_connected_first_answer.py` — verify the artwork for both themes.

## 2026-11-05 — Mark draft retries as intentional background saves

**Commit:** pending · **Type:** fix · **Area:** task-flow

**Files**
- `search-app/static/first-answer.js`, `search-app/static/final-answer-draft.js` —
  explicitly discard the promise returned by the retry handler. The save function
  handles failures and updates the retry message.

## 2026-11-04 — Show the participant’s before-and-after answers

**Commit:** pending · **Type:** feature · **Area:** task-flow, styling, tests

**Files**
- `search-app/search_app.py`, `search-app/student_progress.py`, `search-app/study_progress.py` — route confirmed tasks
  to a comparison page scoped to the active participant’s saved attempt.
- `search-app/templates/study_handoff.html`,
  `search-app/static/study-review.css`, `search-app/static/study-review.js` — show
  the two answers after each task and a printable recap after the third task.
- `search-app/tests/` — exercise the comparison, recap, and continuation after a lost
  save acknowledgement in the real student app.

**What changed for the participant**
The first and final answers are shown together after each confirmation. The third
comparison opens a recap with all three pairs and the browser’s print-to-PDF dialog.
The comparison cards use temporary graphics while the original illustrations are exported.

**How it works**
The page reads the stored question snapshot and the answers confirmed in this browser session.
The review grant is recorded in the same transaction as the final answer.
Reopening a completed attempt by ID shows a confirmation without displaying the previous answers.
Original answers and the existing completion events are kept in their existing stores.

## 2026-11-04 — Update study progress to the shared integration branch

**Commit:** pending · **Type:** fix · **Area:** task-flow, tests

**Files**
- `search-app/tests/test_student_security.py` — confirm the final answer before ending
  the first task and confirm the first answer before opening the next search.

**Verified**
The iframe test reproduces the missing-answer conflict before the adjustment.
All 19 student security tests pass with the corrected setup.
## 2026-11-06 — Keep autocomplete suggestions visible while typing

The existing list stays visible while a new prefix loads, then the current
response replaces it in one update. Previous suggestions remain inactive
while loading so they cannot be selected or logged for the new prefix.

## 2026-11-05 — Clear suggestion state if rendering fails

**Commit:** pending · **Type:** fix · **Area:** autocomplete, logging, tests

**Files**
- `search-app/templates/layout.html` — clear partially applied suggestions and
  metadata when the current response fails during rendering or logging.
- `search-app/tests/test_autocomplete_browser.py` — synthetic logging failure.

**What changed for the participant**
When the suggestion list fails to open, the search field remains ready for a
typed query without attributing it to a suggestion from that list.

**If something looks wrong after this, check**
- Suggestions disappear despite a successful response → check the browser console
  for errors from rendering or saving the study log.

**Verified**
Chromium exercised a logging failure after the suggestions were prepared.

## 2026-11-05 — Reduce autocomplete wait and recover from Vertex failures

**Commit:** pending · **Type:** fix · **Area:** autocomplete, search-bar, logging, docs, tests

**Files**
- `search-app/templates/layout.html` — 200 ms debounce, browser request cancellation,
  sequence checks around JSON parsing, and current-prefix logging context.
- `search-app/search_app.py`, `search-app/search_backend.py` — normalized response,
  reused Vertex completion client, and bounded attempts with SerpAPI fallback.
- `search-app/tests/test_autocomplete_browser.py`, `test_backend_privacy.py`,
  `test_student_security.py` — synthetic browser and provider contract coverage.
- `docs/issue13_handover.md` — request trace, examples, and live verification steps.

**What changed for the participant**
Autocomplete requests start 100 ms sooner after typing stops. Clearing or editing the
field drops suggestions and metadata for the previous prefix. If Vertex returns no
suggestions or fails, SerpAPI can supply suggestions when configured.

**How it works**
Provider helpers return lists and the Flask route always returns `suggestions`,
`source`, and `query_model`. A successful response preserves its study-log source
label. Empty responses have `source: none` and a null model. The browser aborts
superseded requests and checks the sequence again after parsing JSON.

**If something looks wrong after this, check**
- Late suggestions → the debounce and sequence checks in `layout.html`.
- Missing suggestions → Vertex credentials, the completion deadline, and the
  optional SerpAPI key, using the provider's error class in the app log.
- Frequent SerpAPI fallback → check warm and cold Vertex timings against its
  750 ms RPC deadline.

**Left alone**
Search ranking runs through `/result`. Vertex spell correction is suggestion-only
and appears as `Forse cercavi` on the first result page when applicable.

**Verified**
Synthetic Vertex and SerpAPI responses and real Chromium exercised provider
failures, request timing and cancellation, click and keyboard selection, clear,
and the study log fields. See the handover for the live timing check.

## 2026-11-03 — Weekly Dependabot updates into matthias-dev

**Commit:** pending · **Type:** infra · **Area:** infra, docs

**Files**
- `.github/dependabot.yml` (new) — weekly grouped update pull requests into
  `matthias-dev` for GitHub Actions, the test and quality tools
  (`requirements-*.txt`) and the Docker base image (Python 3.14 patch releases only).
- `docs/follow_up_checks.md` — the GitHub Actions item points to Dependabot; new item
  for the Dependabot `SONAR_TOKEN` secret.

**What changed for the participant**
No visible change.

**How it works**
GitHub reads `dependabot.yml` only from the default branch (`main`), so the update
pull requests start after the next release. They go through the same three checks
and need an approval like any other pull request.

**If something looks wrong after this, check**
- A Dependabot pull request fails `Code quality` at "SonarQube Cloud token required"
  → the Dependabot secret `SONAR_TOKEN` is missing.
- No Dependabot pull requests at all → `dependabot.yml` is not on `main` yet.

**Left alone**
`requirements.lock`: Dependabot reads only `.txt` and `.in` files, so the production
pins are still refreshed by hand; the pip-audit step keeps blocking known
vulnerabilities in them. The workflow and the existing pins are unchanged.

**Verified**
The file parses and every entry targets `matthias-dev` weekly. Dependabot's file
matching was checked in its source (`shared_file_fetcher.rb`). Whether GitHub accepts
the configuration can only be seen once it is on `main` (Insights → Dependency graph
→ Dependabot).

## 2026-11-03 — Record branch protection and Samuele's onboarding status

**Commit:** pending · **Type:** content · **Area:** docs, infra

**Files**
- `docs/follow_up_checks.md` — branch protection on `matthias-dev` and `main` and the
  repository settings ticked as done; Samuele's onboarding stays open with its status
  (PRs #21–#23 retargeted to `matthias-dev`, update steps posted on each).

**What changed for the participant**
No visible change.

**Left alone**
No code changed. PR #20 was merged with a merge commit, not squashed, because Samuele's
branches already contain its earlier commits; a squash would have turned 0/2/0
conflicting files into 64/34/32.

## 2026-11-03 — Dashboard changes from the researcher feedback

**Commit:** pending · **Type:** feature, fix · **Area:** data, styling, docs, tests

From a colleague's walkthrough (PDF and screen recording of 3 November). Decisions by
Matthias: school year from the date, ID pop-ups, Cestino on Dati e storico, warnings
keep the yellow interface but get their own colour and icon.

**Files**
- `research_dashboard/preparation_views.py`, `templates/research/prepare.html` — a
  session's school year follows its date (September–August): no typed year, no date
  limits; a date in another year files the session there and opens it. Year menu like
  the class menu instead of a text field and **Apri anno**. A line says which session
  is being edited. Step 2: **Importa partecipanti da altre classi** (pop-up, IDs
  grouped by their class this year or last class) and **Crea nuovi partecipanti**
  (pop-up, flags IDs already in the study); a later year without enrolled children
  shows a warning linking **Prepara il prossimo anno scolastico**.
- `research_dashboard/settings_views.py`, `settings_sessions.html`,
  `settings_session_form.html`, `settings.html` — the same year rule for creating,
  editing, re-dating and restoring sessions (year shown, not typed); the year filter
  button reads **Mostra le sessioni**; the current-year card lists the years already
  in the study and saving the current year again changes nothing.
- `research_dashboard/enrollment_views.py` — accepts several ticked IDs.
- `research_dashboard/export_views.py`, `templates/research/participant.html` —
  checkbox per run and **Scarica le esecuzioni selezionate** (`POST /exports/runs`,
  only that participant's visible runs).
- `templates/research/base.html`, `overview.html`, `overview_table.html`, `trash.html`,
  `history_views.py` — logo links to Prepara una sessione; header is EN/IT | Esci;
  **Cestino** moved to Dati e storico; "•••" replaced by a **Gestisci log** link. The
  Cestino, participant, run and single-log pages now mark **Dati e storico** as the
  current tab (before, none was marked).
- `static/editor.js`, `templates/research/base.html` — Esci always asks "Sei sicuro di
  voler uscire?" in a Sì/No pop-up (Esc answers No; the other warnings about unsaved
  work use the same pop-up); ID pop-ups.
- `research_dashboard/enrollment_views.py`, `templates/research/enrollment.html` — a
  searched ID hidden by the filters on **Modifica gli ID** says where it is (another
  class, with a link; not enrolled this year, with its last class; hidden by the status
  filter; not in the study) instead of "Nessun partecipante corrisponde ai filtri".
- `templates/research/session_questions.html` — no leading "·" before the date when a
  session has no name.
- `static/research.css`, `workflow.css`, `editor.css`, `icon-warning.svg` — warning
  colour and triangle; quiet "Modifiche recenti ai partecipanti"; pop-up and run
  selection styles; links inside messages are underlined so they read as links
  without hover (iPad).
- `research_dashboard/*i18n.py` — clearer texts: past session ("I bambini non
  possono più iniziare…"), "Domande per tutta la classe", recovery-copy messages
  instead of "Modifiche protette in privato", "Scarica tutti i log di questa vista",
  clearer ID options and errors.
- `year_controls.py` — unused `school_year_bounds` removed.
- Tests: new `test_dashboard_feedback.py`, `test_dashboard_feedback_browser.py`;
  year, concurrency and form-error tests rewritten for the date rule.
- `docs/research_dashboard.md`, `docs/follow_up_checks.md`.

**What changed for the participant**
No visible change for children.

**How it works**
`school_year_for(date)` decides the year wherever a session date is saved;
`State.save_settings` still refuses a year change for a session with records.

**If something looks wrong after this, check**
- A session appears under an unexpected year → its date; the year is September–August.
- "Nessun bambino è ancora iscritto…" → run the yearly step or import the children.
- Pop-ups do not open → JavaScript or `<dialog>` support; the links then open the full
  ID page instead. Without JavaScript, Esci logs out without asking (as before); without
  `<dialog>`, the browser's own OK/Annulla box asks instead of Sì/No.

**Left alone**
Enrollment rules, the yearly promotion, the permanent register page (its combined form
only got clearer labels), the children's app. Two points of the feedback wait for the
colleague's answer: creating a session from name and date before choosing the class,
and whether "più visibilità alla lista di domande condivise" means the class questions
(done) or the question library ("Riutilizza un gruppo di domande", unchanged).

**Verified**
Full suite with browser tests required; screenshots of the changed pages at desktop
and phone width. The feedback was re-checked against the PDF and a second, complete
transcript of the recording. Not yet tested on an iPad (see `follow_up_checks.md`).

## 2026-11-02 — Probe only shown result links and clear the SonarQube findings

**Commit:** pending · **Type:** fix · **Area:** result-viewer, serp, data, infra

**Files**
- `search-app/search_app.py` — `/iframe_check` looks the address up among the result
  links shown in the current task (`results_by_query`) and probes our stored copy;
  any other address answers `not-a-search-result` without a request. Clears the
  SonarQube SSRF findings (S5144).
- `search-app/research_dashboard/index.py` — `file_identity()` parses
  `<stem>_<suffix>.log` right to left instead of with a backtracking regex (S8786).
  Same results as the old pattern on 300,000 generated names, including topics with
  `_`, nested `_task…_topic…` parts and line breaks.
- `search-app/research_dashboard/security.py` — the throttled login builds its response
  with `make_response` to set `Retry-After: 900` (S8495); status and header unchanged.
- `search-app/research_dashboard/templates/research/login.html` — no `autofocus` on the
  password field (S9379).
- `search-app/templates/search.html` — the empty, hidden "read more" links get
  `tabindex="-1"`: the keyboard no longer stops on an invisible link (S6825).
- `search-app/tests/test_student_security.py` — probe tests search first; new tests for
  refused addresses, results cleared on the next task, and links with quotes, `&`, `#`,
  `+`, `%2F`, spaces and accents reaching the probe unchanged.
- `docs/research_dashboard.md`, `docs/manual_logging_walkthrough.md` — the new reason.

**What changed for the participant**
No visible change. Keyboard Tab on the result page skips the invisible link after each
snippet. Researchers click into the password field before typing.

**How it works**
`/webpage` is only reached from a result link, and the viewer probes on page load, while
the task's results are still in the session.

**If something looks wrong after this, check**
- More `webpageLoadCheckUnknown` with reason `not-a-search-result` → the link changed
  between the result page and the viewer; compare `url` with the result's
  `data-original-url` in the log.
- Dashboard missing a task, full or recovery file → `file_identity()` in `index.py`.

**Left alone**
Redirect re-checks, private-address rules and the 3-second timeout; the participants
table keeps `tabindex="0"` so the keyboard can scroll it (S6845 accepted in SonarQube);
`State.connect()` (S8706 is a false positive: the path is the operator's own
`--state-dir`, opened as a file, not a URI).

**Verified**
Full suite with browser tests required; Ruff clean; differential check of
`file_identity()` against the old regex.

## 2026-11-02 — Patch pyasn1 and keep SonarQube running when the audit fails

**Commit:** pending · **Type:** fix, infra · **Area:** infra

**Files**
- `search-app/requirements.lock` — pyasn1 0.6.4 → 0.6.5 (four advisories published
  after the 26 October update; found by the `Code quality` audit on PR #20).
- `.github/workflows/collection.yml` — the audit step no longer stops the job: tests,
  coverage and SonarQube Cloud still run, and a final step fails the job if the audit
  found anything.

**What changed for the participant**
No visible change.

**If something looks wrong after this, check**
- `Code quality` fails on "Known vulnerabilities block the merge" → open the audit
  step's log for the package and fixed version; update that pin.

**Left alone**
No other package changed; `pyasn1_modules` 0.4.2 supports pyasn1 0.6.5.

**Verified**
Fresh environment: `pip check` and `pip-audit` clean; 594 tests pass (browser tests
required); `actionlint` accepts the workflow.

## 2026-11-02 — Record the researcher password policy

**Commit:** pending · **Type:** content · **Area:** docs

**Files**
- `docs/research_dashboard.md` — the shared password never expires and is changed or
  reset only with `tools/set_research_password.py`; sessions still end after 30 minutes
  idle or 8 hours.
- `docs/follow_up_checks.md` — single sign-on (SWITCH edu-ID) or recovery as a later
  option; reminder to set `SONAR_REQUIRED=true` after the first passing analysis.

**What changed for the participant**
No visible change.

**Left alone**
No code changed: login, session limits and the reset command behave as before.

**Verified**
Documentation only.

## 2026-10-26 — Code quality checks, patched dependencies and contribution workflow

**Commit:** pending · **Type:** infra · **Area:** infra, tests, docs

**Files**
- `.github/workflows/collection.yml` — new `Code quality` job: Ruff lint, JavaScript
  syntax, `pip-audit` of `requirements.lock`, tests with coverage, and the SonarQube
  Cloud scan with its quality gate (runs once the `SONAR_TOKEN` secret exists; the
  `SONAR_REQUIRED` variable makes a missing token fail). Pushes now run CI only on
  `main` and `matthias-dev`; every pull request still runs it, and a newer push
  cancels the running check. Manual runs via `workflow_dispatch`.
- `ruff.toml`, `.coveragerc`, `sonar-project.properties` (new, repository root) —
  lint rules, coverage scope, SonarQube Cloud scope (application code only).
  `.gitignore` ignores the local coverage and Ruff cache files.
- `search-app/requirements.lock`, `requirements.txt` — certifi 2026.10.23,
  cryptography 50.0.2, pyasn1 0.6.4, urllib3 2.8.0, Werkzeug 3.1.9 (all with known
  vulnerabilities fixed); unused Pillow removed.
- `search-app/requirements-quality.txt` (new) — pinned Ruff, pip-audit, pytest-cov.
- `CONTRIBUTING.md`, `.github/pull_request_template.md` (new) — branch model,
  draft pull request workflow, checks, local commands and one-time admin setup.
- `docs/follow_up_checks.md` (new), `docs/codex_handoff.md` — dated list of open checks
  (real search after the update, devices, SonarQube Cloud, branch protection) and a
  pointer to it at the top of the Codex handoff.
- `docs/merge_v2_readiness.md` — the hosted CI gate names the new check.
- Tests: three small lint fixes in `test_collection_recovery.py`,
  `test_permanent_participants.py`, `test_research_dashboard.py`.

**What changed for the participant**
No visible change. The patched packages run in the production image.

**How it works**
`pip-audit --no-deps --disable-pip` audits exactly the pinned lock file. Coverage
uses relative paths so SonarQube Cloud can match `coverage.xml`. The SonarQube Cloud
token is given only to its own step, never to tests or package installs.

**If something looks wrong after this, check**
- `Code quality` fails on the audit step → a new advisory was published for a
  pinned package: update that pin in its own pull request.
- Requests to Google or proxy/TLS errors after deployment → the urllib3, certifi or
  cryptography bump; compare with the previous image.
- A feature branch has no checks → it has no pull request yet; open a draft one.

**Left alone**
The PyTerrier search engine (`logger/search-engine`) is not linted or analysed yet.
Branch protection and SonarQube Cloud need repository settings and an account, so
they are documented in `CONTRIBUTING.md`, not applied.

**Verified**
Full suite in a fresh environment with the new pins: 594 passed (Chromium browser
tests required); `pip check` and `pip-audit` clean; `ruff check` clean; `actionlint`
accepts the workflow. The container build and Python 3.14 run happen in CI.

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
