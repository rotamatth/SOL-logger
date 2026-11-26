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

## 2026-11-26 — Keep classroom layouts for the map, and each tablet's health a request away

**Commit:** pending · **Type:** feature · **Area:** dashboard, data, tests

**Files**
- `logger/search-app/research_dashboard/room_maps.py` — new: `rooms.sqlite3` and `room-images/` in the research state folder; named rooms (tables and an optional floor plan, never IDs), each session's own map (a copy of a room plus where each ID sits), revisions, validation on a fixed 1000 × 700 canvas, floor plans checked by their content (PNG, JPEG or WebP, at most 8 MB and 25 megapixels)
- `logger/search-app/research_dashboard/map_views.py` — new: `GET /dashboard/sessions/<id>/map.json`, `POST …/map`, `POST …/map/room` (start from a room's copy), `POST …/map/image`, `POST /dashboard/rooms` and `/dashboard/rooms/<id>` (explicitly save a session's geometry as a room), `GET /dashboard/room-images/<name>`, and `GET …/health.json`, light enough for every two seconds
- `logger/search-app/research_dashboard/__init__.py`, `dashboard.py`, `security.py` — the routes, their JSON errors, and a 9 MB limit for the floor plan's form only
- `logger/search-app/tests/test_room_maps.py` — new

**What changed for the participant**
No change for children. Researchers' map data has a place to live (the next commit shows the map).

**How it works**
Every change is a POST with the CSRF token and the revision it was based on; a stale one gets 409 and the current version back. A session's map starts as a copy of a room with no ID placed, so another class's IDs never come along, and a session changes a room only through the explicit "save as room" or "update room". Placing an ID is a display choice, never an admission rule. The health feed reads the settings' roster and `monitor.sqlite3`, nothing else; when that database cannot be read it says monitoring is unavailable rather than reporting every tablet as lost.

**If something looks wrong after this, check**
- A map that will not save → its revision (409: someone else saved) or `invalid_map` (a table outside the canvas, an ID placed on a missing table).
- A floor plan refused → `invalid_image`: not a real PNG, JPEG or WebP, or too large.

**Left alone**
The live view's existing JSON and page, the logs, the study's settings and enrollment, admission.

**Verified**
The new tests: exact string IDs, a bad map refused whole, revisions, a room copied without IDs and left alone by the session, explicit room updates with their own revision, two named rooms, real and fake pictures, the routes' authentication, CSRF, 409s, the served image's headers, the health feed and its unavailable case, and reads that write nothing. All server tests pass.

## 2026-11-26 — Report every two seconds what the classroom map needs, saves the tablet could not confirm included

**Commit:** pending · **Type:** feature · **Area:** logging, session, tests

**Files**
- `logger/search-app/static/connection-watch.js` — a report every 2 seconds instead of a signal every 15: page, visibility, full screen (capable and on, or unknown), a search not back yet, saves not confirmed, the last confirmed save; changes sent at once; one report at a time, given up after 2 seconds, timed from its start; an order that never goes back across pages; the children's notice after 10 seconds without an answer instead of two missed signals
- `logger/search-app/static/first-answer.js`, `final-answer-draft.js`, `recap.js` — a `sol:save` event when a save is confirmed or not, with the reason (network, conflict, server, unconfirmed)
- `logger/search-app/templates/*.html` — the four scripts at version `monitor-1`, so tablets load them again
- `logger/search-app/tests/test_connection_watch_browser.py` — the notice after ten seconds; the report's content and order; a refused draft reported until a save goes through
- `logger/docs/research_dashboard.md` — the 2-second signal and the 10-second notice

**What changed for the participant**
The "Il collegamento non funziona" notice now appears when the server has been silent for 10 seconds (it was 15 to 30), and goes away as before. Nothing else changes on screen.

**How it works**
Only the inner page reports; the full-screen host does not load the script, so one tablet sends one report at a time. Full screen is read from the host's document when the page lives in its frame. A refused save stays in this tab's storage until the matching success, so it survives a page change. The report carries no answer, query or other app's name.

**If something looks wrong after this, check**
- The notice too eager or too slow → `NOTICE_AFTER_MS`.
- Too many requests on the server → `BEAT_MS` here and `BEAT_SECONDS` in `monitor.py` go together.

**Left alone**
The logs and their uploads, the logged connection and page events, the service worker, the answers' retry buttons and messages.

**Verified**
The connection watch tests in Chromium (seven), the first-answer and child-page browser tests. 1383 of 1386 tests pass; the other three are fullscreen browser tests failing on and off with the CDN "reading 'fn'" error, a different variant each run. Not yet on the classroom tablets in Brave over the VPN.

## 2026-11-26 — Register each tablet for the classroom map, from its ID to its reset

**Commit:** pending · **Type:** feature · **Area:** session, logging, dashboard, tests

**Files**
- `logger/search-app/research_dashboard/monitor.py` — new: `monitor.sqlite3` in the research state folder; registrations per study session and participant ID, each tablet's latest report, search and save incidents, a bounded history, and how a tablet's colour and reasons are worked out from the server's clock
- `logger/search-app/research_dashboard/monitoring.py` — new: the children's side; the `sol_monitor` cookie, registering at the ID, retiring at the reset, and the server-seen save failures (`SAVE_ENDPOINTS`)
- `logger/search-app/research_dashboard/__init__.py` — the monitor next to the presence store
- `logger/search-app/search_app.py` — `MONITORING`; `/presenza` passes the report on; the ID page's `set_number` registers the tablet; `/welcome?reset=1` retires it; the engine's refusal and answer mark and clear a failed search
- `logger/search-app/tests/test_classroom_monitor.py` — new

**What changed for the participant**
No visible change. A tablet whose ID an adult has chosen is now registered for the classroom map (the next commits show it), before the practice and with no run, log or answer created.

**How it works**
The registration lives in its own cookie, so it outlives the run's browser session that Salva clears, and the last page is still heard from. A run under way re-registers its tablet after a reload or a lost cookie. Only `/welcome?reset=1` (the logo's long press, or the address typed by an adult) retires it, or another ID chosen on the same tablet. Reports are ordered by the tablet's own counter, so a late one never overwrites a newer one; ages come from the server's clock. Incidents keep their start time until the matching success: a heartbeat never clears a failed search or a save the server refused. Test IDs are not registered.

**If something looks wrong after this, check**
- A circle that stays grey → the tablet never reported: the cookie was refused, or the ID was chosen before this was deployed.
- An ID the tablet no longer has → `/welcome?reset=1` was not used between classes.
- `monitor.sqlite3` unreadable → the map shows monitoring unavailable; nothing else changes.

**Left alone**
Admission, the practice's no-data rule, the run's session, the logs, the progress database, answers and their retries, exports, the presence store and the list's badges.

**Verified**
The new tests: registration and reassignment, exact string IDs, freshness at 3.9, 4, 5.9 and 6 seconds, a hidden page going silent, reports out of order, full screen only where expected and supported, a failed search and a refused save staying red through heartbeats until the next success, a stalled search, the history of a silence, two tablets with one ID, the expiry, the bounded history, an unreadable database; and through the app, the ID before the practice with nothing recorded, the last page after Salva, the reset, a new ID, test IDs, a refused search and a refused save. All 1179 server tests pass.

## 2026-11-26 — Leave only the title and the picture on the recap PDF's first page

**Commit:** pending · **Type:** content · **Area:** data, tests

**Files**
- `logger/search-app/student_recap.py` — the picture page loses "Le risposte complete sono nelle pagine seguenti." and its "Pagina 1"; the picture is a little larger in the room they leave
- `logger/search-app/tests/test_recap_picture.py` — `drawn_text()` reads what each page draws; the picture page has the title and the cards, no note and no page number, and the text pages keep theirs

**What changed for the participant**
No change for children. The recap PDF's first page shows only "SOL Search · Le risposte di oggi" and the picture with the answers, a little larger. The pages after it, with every answer in full, are unchanged and still numbered (from "Pagina 2"). Matthias found the note and the number useless.

**How it works**
The picture page template has no footer, and the flow of page one is the title, the picture and the break to the text pages. The picture's height reserve for the title is 56 points instead of 74.

**If something looks wrong after this, check**
- The picture alone on a page and the title on another → the reserve in `render_recap_pdf` (`test_the_picture_is_a_landscape_first_page_before_the_text` counts the pages).

**Left alone**
The text pages, their numbers, the cards and their places, Salva, the redraw tool.

**Verified**
The recap PDF tests pass, with the new one; the page looked at by eye.

## 2026-11-26 — Place the constellations and muscles recap cards as on 10 November

**Commit:** pending · **Type:** fix · **Area:** task-flow, styling, data, tests

**Files**
- `logger/search-app/static/recap.css` — constellations and muscles: a column per question under its label, the first answers in one row, the final answers in one row below, moved down under the figures; muscles with taller cards, a slimmer title and the magnifier left of the final answer
- `logger/search-app/recap_picture.py` — `PLACES` of both topics, the same places in the PDF
- `logger/search-app/student_recap.py` — `RECAP_ARROWS` of both topics, from each first answer to its final one
- `logger/search-app/templates/recap.html` — `recap.css` version `pictures-2`, so tablets load the new places
- `logger/search-app/tests/test_child_pages_browser.py` — for both topics: the rows line up as on 10 November, and three lines of every answer show on a tablet (two on the shortest test screen)

**What changed for the participant**
On the recap of `costellazioni` and `muscoli` (tablet and PDF), the cards no longer sit in different places per question: as on 10 November, each question has its column under its "Domanda" label, "Cosa sapevi prima" above, "Cosa sai adesso" below, joined by the arrow through the magnifier. The rows sit below the figures, so the constellation, the sun, the rocket, the child at the telescope, the faces, the first boy's organs and the octopus's hearts stay in sight. Three lines of every answer show on a tablet (picture at least 500 px tall); the full answers stay in the PDF's text pages. Matthias's request, after seeing the muscles PDF: the 24 November places looked random.

**How it works**
The exact 10 November places would cover the faces, the sun and the rocket, so the same arrangement moves into the lower part of each drawing. Under the muscles' hearts there is less room: the two rows almost touch, the magnifier sits left of each final answer (still between the two answers), and the card title is the slimmer one short screens already used, which leaves three lines.

**If something looks wrong after this, check**
- A card over a face or a figure → `FIGURES` in `test_child_pages_browser.py`, and the places in `recap.css`.
- The PDF and the tablet disagree → `recap_picture.PLACES` against `recap.css` (`test_the_pdf_places_cards_and_labels_where_the_tablet_does`).
- The old places on a tablet → its cache: the stylesheet version must be `pictures-2`.

**Left alone**
Space and ear (10 November's places), the labels, the review pages after each question, the pictures, the text pages of the PDF.

**Verified**
1346 of 1349 tests pass; the other three are browser tests that fail on and off with the CDN "reading 'fn'" error, and they passed when run again. The recap browser tests at 1180×699, 1280×680 and 1024×520 with long answers: no card over a figure, a label, a magnifier or another card; rows aligned; three lines at the two tablet sizes, two at 1024×520. Both PDFs checked by eye.

## 2026-11-26 — Keep the recap picture in the PDF as a JPEG, ten times smaller

**Commit:** pending · **Type:** fix · **Area:** data, tests, docs

**Files**
- `logger/search-app/recap_picture.py` — `jpeg()`: the drawing is converted to JPEG (quality 85) before ReportLab draws it
- `logger/search-app/tests/test_recap_picture.py` — every topic's PDF embeds a JPEG and stays under 1 MB
- `logger/docs/research_dashboard.md` — "Recap PDF": the size

**What changed for the participant**
No visible change: the picture page looks the same, and the answers on it are text as before. A recap PDF now weighs 330–640 KB instead of 3–4.5 MB.

**How it works**
ReportLab stored the WebP drawing as raw pixels (about 5 MB, barely compressed); JPEG data it keeps as it is (`/DCTDecode`). Each PDF is saved in `progress_recap_exports` at Salva, so the progress database, on the server's small `/home`, and every deploy backup that zips it grew by 3–5 MB per group. Found while drawing the 10 November PDFs again: 18 groups would have added about 80 MB.

**If something looks wrong after this, check**
- A blurry or blocky picture in the PDF → the JPEG quality in `jpeg()`.
- A PDF without its picture → Pillow missing from the image (it comes with ReportLab in `requirements.lock`).

**Left alone**
The card places, the text pages, the tablet's recap page, the WebP files.

**Verified**
Old and new picture pages compared side by side and close up: no visible difference. 1347 of 1349 tests pass; the other two are the fullscreen browser tests that fail on and off with the CDN "reading 'fn'" error, and they passed when run again.

## 2026-11-26 — Draw the 10 November recap PDFs again, with the picture

**Commit:** pending · **Type:** feature · **Area:** data, dashboard, docs, tests

**Files**
- `logger/search-app/tools/redraw_recap_pdfs.py` — new: draws again the saved recap PDFs of one day with the picture page, keeping the old ones in a zip first
- `logger/search-app/student_recap.py` — `StudentRecap.pdf_with_picture()`: the PDF Salva makes now, or None when the session has no picture; the tool uses it, Salva does not
- `logger/search-app/tests/test_redraw_recap_pdfs.py` — new: dry run changes nothing; `--write` gives the picture page, keeps the time of Salva and the old PDF in a 0600 zip; a second run, another day, test runs and topics without a picture are left alone; a PDF changed meanwhile stops everything
- `logger/docs/research_dashboard.md` — "Recap PDF": how to run it

**What changed for the participant**
No change for children. After the tool runs on the server, the dashboard's "Scarica il riepilogo finale del bambino (PDF)" for a 10 November session gives a PDF that opens with the recap picture, as 2 December's will, instead of the text only.

**How it works**
The PDF is saved at "Salva l'attività"; before #42 (22 November) it had no picture page. The tool imports the app the server runs, finds the day's saved PDFs that have no image (`/Subtype /Image`), and renders each again from `recap_columns` with `pdf_with_picture`, which is Salva's own code. With `--write` it writes the old PDFs to a zip, reads the zip back, then updates `progress_recap_exports.pdf` in one `BEGIN IMMEDIATE` transaction, each row only if its PDF is still the one read (`WHERE pdf = ?`); any mismatch rolls back everything. `finished_at` is not touched.

**If something looks wrong after this, check**
- A 10 November PDF still without the picture → the tool was run without `--write`, or that session's topic is not a topic word.
- A PDF to restore → the zip in `logger/research-state/` holds each old PDF as `<ID>_<attempt>.pdf`.

**Left alone**
Salva and the PDFs it makes, the dashboard's download, the answers, the logs, `finished_at`, test runs.

**Verified**
The new tests pass. On a scratch copy of the 10 November progress database (taken that afternoon, on my Mac only): 18 PDFs drawn again (10 spazio, 8 orecchio), `TEST-spazio` left out, the zip written, and a second run changed nothing.

## 2026-11-26 — Add the tablets, the reset, the test IDs, the topic word and the practice question to the guide

**Commit:** pending · **Type:** content · **Area:** dashboard, docs, tests

**Files**
- `logger/search-app/research_dashboard/guide_i18n.py` — five new steps (session topic, set up each tablet, reset a tablet, test IDs, practice question) and a new part "In class, with the tablets"; the live view step names the tablet's status and the "call an adult" notice; a child's step names the recap PDF
- `logger/search-app/research_dashboard/guide_views.py`, `templates/research/guide.html` — the parts and their steps come from `GUIDE_GROUPS`, numbered in order (13 steps instead of 8)
- `logger/search-app/research_dashboard/static/guide/{en,it}/` — new `topic`, `tablet`, `reset`, `test`, `practice` pictures; `questions`, `ids`, `live`, `child` taken again (the demo topic is now `spazio`, and a child's page has had one card per question since November)
- `logger/search-app/tools/capture_guide_screens.py` — starts `search_app.py` itself, with a stand-in search, instead of the dashboard alone, so it can photograph the tablet pages, the topic line and the practice settings
- `logger/search-app/tests/test_guide.py` — the parts hold every step once and in order; the topic step names every topic word the app knows; the test step names every test ID; the reset step gives the logo and `/welcome?reset=1`
- `logger/docs/research_dashboard.md` — the guide's parts, and what to do when a topic or test ID is added
- `logger/docs/production_readiness.md` — the practice comes after the ID; without its engine the ID page starts the run itself (both lines still described the order before #48)

**What changed for the participant**
No change for children. A researcher opening **Guide** now also learns how to set up a tablet, how to reset it (the logo for three seconds, or `/welcome?reset=1`), how to try the app with a test ID, that the session's topic must be one of the app's words (the 26 November sessions had a longer title, which would have stopped every search), and where the practice question is set.

**How it works**
The page loops over `GUIDE_GROUPS`; each step is still a title, a text, a detail and a picture in each language. The tablet pictures are the children's Italian pages in both languages: a test run of `TEST-costellazioni` through the practice, and `/fine` for the last page.

**If something looks wrong after this, check**
- A step without its picture, or a broken image → run the tool again; `test_every_step_has_wording_and_a_picture_in_each_language`.
- The tool fails at start → `stand_in_search()` lacks something `search_app.py` now asks of `search_backend`.
- The guide names a topic word or a test ID the app no longer has, or misses a new one → `guide_topic_text` / `guide_test_text`.

**Left alone**
The guide's cookie, its first-sign-in rule and the Guide button; the other steps' wording; the pages the guide shows.

**Verified**
All 1338 tests pass apart from the browser tests that fail on and off with the CDN "reading 'fn'" error on the children's pages; those passed when run again. The guide's own tests, browser ones included at 1365, 768, 390 and 320 px, pass. Every new picture was looked at in both languages.

## 2026-11-26 — Swap TEST-costellazioni's first two questions, so each sits in the box of its picture

**Commit:** pending · **Type:** content · **Area:** task-flow, tests

**Files**
- `logger/search-app/research_dashboard/permanent_test.py` — "Le stelle" is now question 1 and "Tra la Terra e il Sole" question 2
- `logger/search-app/tests/test_permanent_test_experiment.py` — the expected order follows

**What changed for the participant**
No change for children. In `TEST-costellazioni`, the nearest-star question now shows next to the constellation with the red star, and the sunlight question next to the Sun shining on the Earth. As published on 26 November, 4a had them the other way round. Matthias chose to swap them in the 4a session too, in the dashboard, so the test ID still asks what the class gets.

**How it works**
A question's box picks its picture (`research_dashboard.md`, "Session topic"). Only the order of two rows changed.

**If something looks wrong after this, check**
- The 4a session and `TEST-costellazioni` in a different order → the swap in the dashboard was not made, or not approved again.

**Left alone**
`TEST-muscoli`, whose order already fit its pictures. The pictures, their boxes, the texts.

**Verified**
The test IDs' tests pass.

## 2026-11-26 — Give TEST-costellazioni and TEST-muscoli the published questions of 4a and 5a

**Commit:** pending · **Type:** content · **Area:** task-flow, docs, tests

**Files**
- `logger/search-app/research_dashboard/permanent_test.py` — the six "Segnaposto" questions replaced by the three of 4a (`grade-4-session-2`) and the three of 5a (`grade-5-session-2`), word for word and in the same boxes, as the server stored them on 26 November (settings revision 46)
- `logger/search-app/tests/test_permanent_test_experiment.py` — a test that the two test IDs ask exactly those questions and that no "Segnaposto" is left
- `logger/docs/research_dashboard.md` — the test IDs' paragraph says where their questions come from

**What changed for the participant**
No change for children. A researcher trying `TEST-costellazioni` or `TEST-muscoli` now meets the questions the classes get on 2 December ("Tra la Terra e il Sole", "Le stelle", "Missioni Spaziali"; "Tipologie di muscoli", "Animale dal sangue blu", "Muscoli del braccio") instead of the placeholders.

**How it works**
Only the question texts. The theme of each test ID stays `costellazioni` / `muscoli`, so it keeps its engine and its pictures. The published sessions' topic texts ("Costellazioni e Missioni Spaziali", "Il sistema muscolare") are not topic words the app knows; a test ID does not use them, so it cannot show whether a real run would search.

**If something looks wrong after this, check**
- A test ID asks other questions than its class → the session was edited in the dashboard after 26 November; the test ID keeps its own copy in `permanent_test.py`.
- A question's picture does not fit it → the question's box in the session; the test ID copies the session's boxes.

**Left alone**
`TEST-spazio` and `TEST-orecchio`, the real sessions and their topic texts, `TOPIC_NAMES`, the pictures and their boxes, the intro lines.

**Verified**
The test IDs' server and browser tests pass, with the new test. Not yet tried on solar, which needs a redeploy for it.

## 2026-11-26 — Call the way back from the change form "Non lo so", not "Annulla"

**Commit:** pending · **Type:** content · **Area:** task-flow, docs, tests

**Files**
- `logger/search-app/templates/first_answer.html` — the change form's way back (`#first-answer-change-cancel`) reads "Non lo so" instead of "Annulla"
- `logger/docs/research_dashboard.md` — the sentence on changing "Non lo so" names the button
- `logger/search-app/tests/test_first_answer_change.py`, `test_practice_question.py` — the link reads "Non lo so", and "Annulla" is gone from the form
- `logger/search-app/tests/test_first_answer_change_browser.py` — the test that keeps "Non lo so" taps the button by its new name (renamed from `test_annulla_keeps_non_lo_so`)

**What changed for the participant**
After "Cambia la mia risposta", the button beside "Conferma" reads "Non lo so", in the same place as the first form's "Non lo so". Tapping it goes back to "La tua prima risposta è: Non lo so", as "Annulla" did. Same in the prova. Matthias's request: "Annulla" was a new word for the children, and "Non lo so" says what they keep.

**How it works**
Only the label of the link. Its id, its look and its address (back to the question, or to `/prova/domanda`) are unchanged, so nothing is sent or logged when it is tapped.

**If something looks wrong after this, check**
- The button opens the "Non sai la risposta?" dialog → the page is the first form, not the change form (`change_mode` in `first_answer.html`).
- A group's "Non lo so" changed after tapping it → it cannot from this link; look for an `OwnKnowledgeAnswerChanged` event, which only "Conferma" sends.

**Left alone**
The first form's "Non lo so" button and its dialog ("Torna alla risposta", "Confermo: non lo so"), "Cambia la mia risposta", the change itself and its logging, the search page's button, the dashboard's own "Annulla" buttons.

**Verified**
All 1308 server and browser tests pass. In Chromium, the change form of a real question and of the prova shows "Non lo so" beside "Conferma", and tapping it leaves "Non lo so" with no `OwnKnowledgeAnswerChanged` event. Not seen on a classroom tablet.

## 2026-11-25 — Set the tablet's number before the prova, and start its run after it

**Commit:** pending · **Type:** feature · **Area:** task-flow, session, logging, dashboard, docs, tests

**Files**
- `logger/search-app/practice_question.py` — the number waits in the browser's session (`SETUP_KEY`) during the prova
- `logger/search-app/search_app.py` — `/start`: `setup=1` only sets the number (`set_number`); the start after the prova and its errors (`run_start_page`, `start_refused`, `start_unavailable`); "Ricomincia" of a test ID skips the prova
- `logger/search-app/student_progress.py` — setting the number takes no admission lock; a start that cannot be saved may show its own page
- `logger/search-app/templates/run_start.html` — new: sends the number's start by itself; "Riprova" after an error
- `logger/search-app/templates/start.html`, `welcome.html`, `layout.html` — Inizia opens the ID page, whose form before the prova only sets the number
- `logger/search-app/research_dashboard/i18n.py` — the prova's texts say the new order
- `logger/docs/research_dashboard.md`, `manual_logging_walkthrough.md`
- `logger/search-app/tests/` — `test_practice_question.py`, `test_practice_question_browser.py`, `test_student_fullscreen_browser.py`, `test_practice_dashboard.py`

**What changed for the participant**
Inizia opens the ID page first. An adult sets the number and hands the tablet over at "Facciamo una prova!". Inizia on "Avete finito la prova!" leads straight to "Cominciamo!": the children no longer choose a number.

**How it works**
Choosing the number and starting the run are two steps. The ID page posts `setup=1` and only keeps `{number, date, over}` in the session, not `user_id`, so the run's routes and `/log_session` refuse the browser as before. Leaving the prova marks it `over`, and `/start` then shows `run_start.html`, which sends the old start request by itself through logger.js's `enter-id-form`. So `idSubmitted` and the clearing of the browser's storage happen when the run starts, as they did, and the ID page's form before the prova (`set-number-form`) records nothing. No database change.

**If something looks wrong after this, check**
- A log that begins long before its first question, or a stray `INCOMPLETE` fragment under an ID nobody used → the form on the ID page must be `set-number-form` while the prova is on.
- A group's run is under another class's number → the tablet was not reset between the classes (`/welcome?reset=1`, or the end page's logo): Inizia must show the list of numbers.
- A group stuck on "Un momento…" or "Riprova" → the server's log for "Could not admit a child" or "Could not publish research run metadata".
- The children see the list of numbers after the prova → `setup` was lost from the session: the browser was closed, or the tablet was reset.

**Left alone**
logger.js, the start request and everything after it, the end page, the recap, the rules for two tablets with one number, the databases. With the prova off or without an engine the ID page starts the run itself, as before.

**Verified**
Server and browser tests: nothing is saved before the prova ends, the log's first event is later than the prova's end, a wrong number followed by a reset leaves nothing under it, a reload returns to the step, a failed start keeps the number and records it once. Not yet on a classroom tablet.

## 2026-11-24 — Add the pictures of the constellations and muscles topics, and the prova's volcano

**Commit:** pending · **Type:** feature · **Area:** task-flow, styling, data, docs, tests

**Files**
- `logger/search-app/static/images/review/constellations-{1,2,3,recap}.webp`, `muscles-{1,2,3,recap}.webp` — new: the single pictures and the recap drawings
- `logger/search-app/static/images/practice/volcano.webp` — new; the placeholder `volcano.svg` is gone
- `logger/search-app/search_app.py` — `REVIEW_PICTURES`: topics with three pictures, with or without clips; the arrows of the new pieces
- `logger/search-app/templates/study_handoff.html`, `static/study-review.js` — a picture where a topic has no clip; only a clip is played
- `logger/search-app/static/study-review.css`, `static/recap.css`, `static/practice.css` — the places of the new pictures, cards and arrows
- `logger/search-app/student_recap.py`, `recap_picture.py` — the recap arrows and, per topic, the card places in the PDF (`PLACES`)
- `logger/docs/research_dashboard.md`, `production_readiness.md` — which question box gets which picture
- `logger/search-app/tests/` — `test_class_topics.py`, `test_child_pages_browser.py`, `test_recap_picture.py`, `test_permanent_test_experiment.py`, `test_practice_question.py`

**What changed for the participant**
With `costellazioni` and `muscoli`, the page after each question shows the question's picture next to the two answers, and the recap is the topic's whole drawing, with the answers on it, as for space and ear. "Avete finito la prova!" shows the real volcano. The recap PDF of these topics opens with the drawing.

**How it works**
A question's box in the session (1, 2, 3) picks its picture, left to right as on the recap drawing: constellation, sun, rocket; boy from the side, octopus, boy flexing. The recap's cards have places of their own per topic, because the faces and the main figures sit where space and ear have their cards: constellations keeps both rows in the lower half, muscles a row along the bottom with the first answers of questions 1 and 3 beside the figures. On screens up to 600 px tall the cards are slimmer, so two lines of each answer show. The single pictures are the supplied crops without their white border. The sun's supplied crop had white eraser marks, so `constellations-2` is the same area cut from the whole drawing.

**If something looks wrong after this, check**
- The picture does not match the question → the question's box in the dashboard (`research_dashboard.md`, "Session topic").
- A card hides a figure, or the PDF differs from the tablet → `recap.css` and `recap_picture.PLACES`, which a test compares.
- An old picture or layout on a tablet → the version in the templates' links (`pictures-1`).

**Left alone**
Space and ear: their clips, places and arrows. The search, the logs, the question order, the intro lines, the placeholder questions of the test IDs.

**Verified**
Browser tests at three tablet sizes with long answers: every card stays inside the drawing, none overlaps, no magnifier is hidden, two lines of every answer show, and no card or label covers a face, the octopus's hearts, the first boy's organs, the red star, the rocket or the child at the telescope. Not yet seen on a real tablet.

## 2026-11-24 — Retry fullscreen on the prova pages and the end page too

**Commit:** pending · **Type:** fix · **Area:** task-flow, tests

**Files**
- `logger/search-app/templates/practice_intro.html`, `practice_done.html`, `finished.html` — load `student-fullscreen.js`, as Samuele's change does on every other child page
- `logger/search-app/tests/test_student_fullscreen_browser.py` — the prova, its last page and the end page bring fullscreen back; a tap inside an open dialog keeps the dialog usable; every child page loads the script

**What changed for the participant**
After leaving fullscreen on "Facciamo una prova!", "Avete finito la prova!" or "Alzate la mano", the next tap brings it back, as on the other pages.

**How it works**
Samuele's change (#38) was written from `matthias-dev`, which has no prova and no end page. These three templates do not extend `layout.html`, so the merge alone left them without the script.

**If something looks wrong after this, check**
- A child page where a tap does not bring fullscreen back → whether it loads `student-fullscreen.js` (`test_every_child_page_loads_the_fullscreen_script`).

**Left alone**
`student-fullscreen.js` itself, the logger, the Back blocker, the connection watch. `offline.html` stays without the script: it must load without the server.

**Verified**
On the plain merge the two new page tests failed. With the script in the three pages they pass. The full run is in the pull request.

## 2026-11-24 — Fix fullscreen quality checks and browser test setup

**Type:** fix · **Area:** task-flow, tests

**Files**
- `logger/search-app/static/student-fullscreen.js` — normalize synchronous errors and rejected promises through an async request and clear pending state in `finally`; use the existing promise catch for entry fallback.
- `logger/search-app/tests/test_student_fullscreen_browser.py` — check that later interactions can retry after both synchronous throws and rejected promises.
- `logger/search-app/tests/test_first_answer_flow_browser.py` — leave fullscreen before resizing the browser for responsive layout assertions.

**What changed for the participant**
No visible change: fullscreen requests still start during the trusted interaction,
and a refused request never blocks the control's normal action or later retries.

**How it works**
Remove the two promise-related `try/catch` patterns reported by Sonar rule
`javascript:S4822`. The async wrapper invokes the browser API before its first
suspension and turns a synchronous throw into a rejection. The chained `finally`
releases the request guard after either outcome.
Fullscreen tests wait for the embedded page's deferred scripts before sending
keyboard input. Responsive layout tests explicitly exit fullscreen before asking
Chromium to resize its window; all layout and saved-answer assertions remain.

**Verified**
All 181 browser tests passed locally, including the GitHub regression; the focused
fullscreen, first-answer flow and UI run passed all 28 tests. Ruff, JavaScript
syntax and whitespace checks passed. SonarQube must reanalyse the next pushed commit.

## 2026-11-24 — Retry student fullscreen from every page

**Type:** fix · **Area:** task-flow, result-viewer

**Files**
- `logger/search-app/static/student-fullscreen.js` — retry on trusted taps, clicks and key presses; reuse the outer fullscreen host.
- `logger/search-app/templates/` — load the shared fullscreen script on every student page and update its cache version.
- `logger/search-app/tests/test_student_fullscreen_browser.py` — cover touch, mouse, keyboard, direct entry, refusal recovery and navigation.
- `logger/search-app/tests/test_first_answer_ui.py` — allow the shared fullscreen script while retaining the legacy-script check.
- `logger/docs/research_dashboard.md` — describe fullscreen recovery and external-frame limits.

**What changed for the participant**
After leaving fullscreen, the next interaction on any student page tries to enter
fullscreen again. Returning to the welcome page is no longer required.

**How it works**
Capture listeners request fullscreen directly during trusted input, targeting the
persistent outer host when present. Active fullscreen and pending requests are
left alone. Failed requests do not cancel the control's action or disable retries.
Escape can exit fullscreen; the following interaction retries. The original
welcome entry and normal-navigation fallback remain available.

**If something looks wrong after this, check**
Check the tablet browser's fullscreen support and permission. Taps inside external
websites' frames do not reach the app; its viewer controls still retry. Research
dashboard pages do not load this script.

## 2026-11-22 — Offer the change of "Non lo so" in the prova too, and in plain sight on the search page

**Commit:** pending · **Type:** fix · **Area:** task-flow, search-bar, tests

**Files**
- `logger/search-app/practice_question.py` — `can_change`, the change form (`/prova/domanda?change=1`) and `/prova/cambia`; the search page's values carry the change link until the first search
- `logger/search-app/templates/search_first_answer.html` — while the change is possible, the button at the top right is "Cambia la mia risposta" and opens the change; the pop-up no longer carries its own change link
- `logger/search-app/static/main.css` — the pop-up link's unused style removed
- `logger/search-app/tests/test_practice_question.py`, `tests/test_first_answer_change.py`, `tests/test_search_first_answer.py`, `tests/test_first_answer_change_browser.py`, `tests/test_search_first_answer_browser.py` — the change in the prova, and the one button on the search page

**What changed for the participant**
In the prova, a confirmed "Non lo so" can now become a written answer before the first search, as in the real questions: "Cambia la mia risposta" beside "Entra nel motore di ricerca". On the search page, prova and real questions alike, the button at the top right reads "Cambia la mia risposta" while a confirmed "Non lo so" can still change, and opens the change directly. Before, it was "La mia prima risposta", and the change was inside its pop-up. After the first search, or once changed, the button is "La mia prima risposta" again, with its pop-up.

**How it works**
The real questions already allowed the change until the first search (`StudentProgress.can_change`, #41). The prova now has the same rule on its session state: a "Non lo so", not yet changed, with no search results in the session. The change stays in the browser session like the rest of the prova and is never recorded. `search_first_answer.html` shows the change link instead of the pop-up whenever `first_answer_change_url` is set, which happens only before a question's first search. The prova's results and web pages never set it, because they always follow a search.

**If something looks wrong after this, check**
- No "Cambia" in the prova → `PracticeQuestion.can_change` and `first_answer_change_url` in `page_values`.
- "Cambia la mia risposta" still at the top right after a search → `results_by_query` in the session.
- Fewer `firstAnswerOpened` events in a log → expected: before the first search, a "Non lo so" group sees the change button, not the pop-up.

**Left alone**
How a real question stores and logs the change (#41), the pop-up itself, the confirmed-answer page of real questions, and the rule "only before the first search".

**Verified**
New tests for the prova (change, once only, needs text, stars and the page's token, gone after a search, records nothing) and for the one button on the search page. All 1101 server tests pass, Ruff is clean, and the browser tests pass. Before/after pictures from the real pages.

## 2026-11-22 — Restore two change log entries that the merges emptied

**Commit:** pending · **Type:** infra · **Area:** docs

**Files**
- `logger/docs/CHANGELOG.md` — the text of "Say under a session's topic…" (#46) and "Enter fullscreen from the existing Inizia button" (#38), copied back from their own branches

**What changed for the participant**
No visible change.

**How it works**
Joining the branches into this one kept those two headings but dropped the text under them. The text is unchanged on `class-topics-2026-12-02` and `keep-children-in-app`; it is copied from there word for word.

**If something looks wrong after this, check**
- A heading with nothing under it → the same entry on the branch it came from.

**Left alone**
Every other entry, and all code.

**Verified**
Every entry under "# Entries" now has text, and each heading appears once.

## 2026-11-22 — Add test IDs for the constellations and muscles topics

**Commit:** pending · **Type:** feature · **Area:** session, tests, docs

**Files**
- `logger/search-app/research_dashboard/permanent_test.py` — `TEST-costellazioni` and `TEST-muscoli`, with placeholder questions
- `logger/search-app/tests/test_permanent_test_experiment.py` — the start list ends with four test IDs; each new one runs on its topic without clips; their topics are words the app knows
- `logger/docs/research_dashboard.md` — "Permanent test IDs"

**What changed for the participant**
No change for the children. The start page's list ends with two more test IDs, after `TEST-orecchio`. They run like the other two (red PROVA banner, any day, kept out of the results) and search the constellations and muscles engines, with three placeholder questions each.

**How it works**
Two more entries in `TEST_EXPERIMENTS`, with the topic words `costellazioni` and `muscoli`, so `known_theme` picks the new engines. Each run gets its own session, as before. The placeholders' topics start with "Segnaposto". When Diletta's questions for 4a costellazioni and 5a muscoli are in the dashboard, they replace the placeholders here, as `TEST-orecchio` got 5a orecchio's.

**If something looks wrong after this, check**
- A new test ID ends on the search error page → that topic's two env lines on the server, and `tools/check_search_engines.py`.
- A new test ID shows a clip → `REVIEW_CLIPS` in `search_app.py` (it should list only spazio and orecchio).

**Left alone**
`TEST-spazio`, `TEST-orecchio`, and where test runs are written. The real sessions and their questions.

**Verified**
New tests for the start list, a whole run on each new test ID, and their topic words. The test ID and topic tests pass.

## 2026-11-22 — Say under a session's topic what the app understood, and warn when the search would fail

**Commit:** pending · **Type:** feature · **Area:** dashboard, docs, tests

**Files**
- `logger/search-app/search_backend.py` — `theme_engine_ready(theme)`: whether a run of that topic can search
- `logger/search-app/search_app.py` — `topic_search_status(text)` and the four topic words, handed to the dashboard through `app.config`
- `logger/search-app/research_dashboard/question_views.py`, `templates/research/session_questions.html`, `i18n.py` — the line under "Tema della sessione" and the suggestions in the field
- `logger/docs/research_dashboard.md` — "Session topic"
- `logger/search-app/tests/test_class_topics.py` — the line in its four states; `tests/backend_stub.py` — new, the stand-in search backend of the tests that load the whole app, now shared by three of them

**What changed for the participant**
No visible change for the children. On the dashboard's questions page, the topic field suggests `spazio`, `orecchio`, `costellazioni` and `muscoli`, and the line under it says "Tema riconosciuto: muscoli." or, in a yellow warning, that the children's search would show an error: the app does not know the word, or the topic has no engine on the server (naming the two env lines). An empty field says "Nessun tema. Scrivi uno di questi: …".

**How it works**
The topic is free text, and a typo used to show up only in class, as the search error page. `topic_search_status` runs the text through `known_theme` and asks `search_backend.theme_engine_ready`, which is true with no per-topic engines (every run uses the single engine) and otherwise only for a topic that has its own. The dashboard reads the function from `app.config["TOPIC_SEARCH_STATUS"]`, so a dashboard without the children's app (its own tests) shows no line. The line reflects the text as last saved, not as it is being typed.

**If something looks wrong after this, check**
- No line under the topic → `TOPIC_SEARCH_STATUS` in `app.config` (set at the end of the topic code in `search_app.py`).
- A warning although the class searched fine → the topic text saved for the session, and `tools/check_search_engines.py` on the server.
- A test that loads the whole app failing on `theme_engine_ready` → it needs `tests/backend_stub.py`.

**Left alone**
Saving and approving: a warning never blocks them. The engines, the topics and the children's pages.

**Verified**
New tests for the recognised topic, a topic without an engine, an unknown word, an empty field, a dashboard without the children's app, and the status function on the real backend with four, two and no engines. All 976 server tests and 165 browser tests pass. Creating both 2 December sessions in the Italian dashboard, on a copy of the 10 November setup, gives Session 2 with the right ten IDs, the recognised topic and "Pubblicata".

## 2026-11-22 — Join the 26 November changes where they meet

**Commit:** pending · **Type:** infra · **Area:** task-flow, infra, tests

**Files**
- `logger/search-app/templates/practice_intro.html`, `practice_done.html`, `finished.html` — load `connection-watch.js`, like every other child page
- `logger/search-app/tests/test_connection_watch.py` — lists the practice and end pages among the child pages
- `logger/search-app/tests/test_practice_question_browser.py` — refuses fullscreen, so the app stays in the top page this test reads
- `logger/docker-compose.local.yml` — mounts `student_progress.py`, `practice_question.py` and `recap_picture.py` for local UI work

**What changed for the participant**
The practice pages and the end page also show "Il collegamento non funziona" when the connection drops.

**How it works**
The merge of #44, #40, #41, #39, #42 and #38 kept every side of each conflict. `/result` notes the first search (#41) before calling the shared results function (#44), so the practice never notes one. The welcome page is Samuele's fullscreen page (#38) with Inizia leading to `/prova` (#44), so the practice runs inside the fullscreen frame. The welcome page itself stays without the connection watch: it hosts the frame, whose pages send the signal.

**If something looks wrong after this, check**
- A page without the notice → whether it loads `connection-watch.js` (`test_every_child_page_watches_the_connection`).

**Left alone**
Everything the six PRs do on their own.

**Verified**
All 1058 server tests passed, and 184 of 185 browser tests in the full run. The other was the practice browser test, which needed the fullscreen refusal above; it passed with Samuele's fullscreen tests afterwards.

## 2026-11-20 — Enter fullscreen from the existing Inizia button

**Commit:** pending · **Type:** feature · **Area:** task-flow, styling, docs, tests

**Files**
- `logger/search-app/templates/welcome.html` — standalone welcome/fullscreen host.
- `logger/search-app/static/student-fullscreen.js` — user-triggered entry and browser fallback.
- `logger/search-app/static/student-fullscreen.css` — full-height student frame and keyboard focus.
- `logger/search-app/tests/test_student_fullscreen_browser.py` — entry, navigation, fallback and exit regressions.
- `logger/docs/research_dashboard.md` — setup and browser/device limits.

**What changed for the participant**
Tapping Inizia enters fullscreen when the browser permits it. The child can move
through the study without each page load leaving fullscreen. A refused request
still opens the usual ID page.

**How it works**
The trusted click requests fullscreen on the welcome document, then opens the
student app in one same-origin iframe. Only the inner student app runs its logger
and Back guard. Returning to welcome inside the frame reuses that host.

**If something looks wrong after this, check**
- No fullscreen → browser support, fullscreen policy and whether Inizia was tapped.
- Frame too short → `student-fullscreen.css` and the tablet's viewport/rotation.
- Route appears unchanged → the address bar retains the welcome host's URL.

**Left alone**
Student routes, saved answers, logging contracts, the shared Back guard and the
research dashboard. No installation, device lock or automatic fullscreen on load.

**Verified**
947 server tests and all 174 Chromium browser regressions passed, including nine
fullscreen cases. Ruff and syntax checks for all 12 production JavaScript files
passed. Welcome and fullscreen results screenshots were visually inspected.
No physical classroom tablet is connected for iPad/Safari or Android acceptance.

## 2026-11-22 — Put the recap picture in the recap PDF

**Commit:** pending · **Type:** feature · **Area:** dashboard, data, docs, tests

**Files**
- `logger/search-app/recap_picture.py` — new: `RecapPicture`, the recap picture drawn with ReportLab at the positions of `recap.css`
- `logger/search-app/student_recap.py` — `render_recap_pdf(columns, picture=None)`: with a picture, a landscape first page before the unchanged text pages; `StudentRecap` takes `artwork` and builds the picture at Salva from the committed answers
- `logger/search-app/search_app.py` — passes the session's drawing and theme to `StudentRecap`
- `logger/search-app/Dockerfile` — copies `recap_picture.py`
- `logger/docs/research_dashboard.md` — "Recap PDF"
- `logger/search-app/tests/test_recap_picture.py` — new

**What changed for the participant**
No visible change on the tablet. The recap PDF that researchers download now opens with the picture the group saw: the theme's drawing with "Domanda N", the first answers and their stars, the final answers and the arrows (Diletta's point 9). On 10 November these pictures had to be rebuilt by hand, because the server kept only the text.

**How it works**
At "Salva l'attività" the commit hands the PDF function the committed answers. `StudentRecap._picture` takes today's session from them, as the recap page does, with the drawing and theme of the session (from `review_illustration` and `review_artwork_theme`). `RecapPicture` draws the drawing, then the arrows (the quadratic curves of `RECAP_ARROWS` as cubic ones, white halo under a dashed black line), the labels, the cards and the stars, at the shares of the picture in `recap.css`. Text the standard PDF fonts cannot show (emoji, other scripts) is left out of the cards only. A card holds the lines that fit and ends with "…"; the text pages keep every answer in full. Without a picture (unknown theme, a missing drawing, a question without its part) the PDF is the text only, as before. No browser runs on the server and nothing comes from the tablet.

**If something looks wrong after this, check**
- A card in the wrong place in the PDF → `recap_picture.py` against `recap.css` (`test_the_pdf_places_cards_and_labels_where_the_tablet_does`).
- Salva failing with "Salvataggio non disponibile" → the PDF's drawing: `_pdf_for_finish` turns any error into the existing 503, so nothing is saved half.
- No picture in the PDF → the session's theme is not spazio or orecchio, or its drawing is missing.

**Left alone**
The tablet's recap, its text pages, what Salva saves and logs, and the dashboard's download.

**Verified**
`tests/test_recap_picture.py`: a landscape picture page before the portrait text page for both themes, the text-only PDF without a picture, cut and broken lines, emoji left out of cards, a long answer noted as cut, the positions matching `recap.css`, and Salva in the app keeping the picture for spazio and orecchio and not for an unknown theme. The full server suite passed. Both themes' first pages were checked as images.
## 2026-11-22 — Mark the connection watch's background signals as such

**Commit:** pending · **Type:** fix · **Area:** infra

**Files**
- `logger/search-app/static/connection-watch.js` — `void beat()` where a signal starts from an event
- `logger/search-app/templates/layout.html`, `first_answer.html`, `task_intro.html`, `study_handoff.html`, `recap.html` — cache version `watch-2`

**What changed for the participant**
No visible change.

**How it works**
SonarCloud's reliability rule S9383 failed the quality gate of PR #39 on two calls of `beat()` whose promise nobody waited for. `beat()` never rejects (it counts every failure itself), so the calls are now marked as deliberately not awaited.

**If something looks wrong after this, check**
- The notice or the signal behaving differently → nothing in the logic changed; compare `connection-watch.js` with the previous entry.

**Left alone**
Everything else in the connection watch.

**Verified**
The connection-watch server and browser tests passed.

## 2026-11-22 — Ask the group to call an adult when the connection drops

**Commit:** pending · **Type:** feature · **Area:** task-flow, logging, infra, docs, tests

**Files**
- `logger/search-app/static/connection-watch.js` — new: the signal every 15 seconds, the "chiama un adulto" notice, the page-left and connection events, and the service worker's registration
- `logger/search-app/static/sw.js`, `static/offline.html` — new: when a children's page cannot be loaded at all, the same message instead of the browser's error
- `logger/search-app/search_app.py` — `GET /sw.js` from the root; the server-error page says "Qualcosa non ha funzionato! Alza la mano e chiama un adulto."
- `logger/search-app/templates/layout.html`, `first_answer.html`, `task_intro.html`, `study_handoff.html`, `recap.html` — load `connection-watch.js`
- `logger/docs/research_dashboard.md`, `logger/docs/manual_logging_walkthrough.md` — the statuses, the notice, the service worker and the four new events
- `logger/search-app/tests/test_connection_watch.py`, `tests/test_connection_watch_browser.py` — new
- `logger/search-app/tests/conftest.py`, `tests/test_background_upload_browser.py` — the `no_service_worker` marker; `tests/test_final_answer_draft_browser.py` uses it for its faked page load
- `logger/search-app/tests/ui_fixture.py`, `tests/test_student_navigation_browser.py` — their small test apps answer `/presenza`
- `logger/search-app/tests/test_first_answer_ui.py`, `tests/test_manual_logging_walkthrough.py` — know the new script and events

**What changed for the participant**
When the tablet loses the network, or the server stops answering for about two signals, the page shows "Il collegamento non funziona. Alza la mano e chiama un adulto." over everything, and it closes by itself when the server answers again. A page that cannot load at all shows the same message. A server error says "Qualcosa non ha funzionato! Alza la mano e chiama un adulto." (Diletta's point 10).

**How it works**
`connection-watch.js` posts `{page, visible}` to `/presenza` every 15 seconds while the page is visible, and every 5 seconds while the notice is shown. Two failed signals in a row, or the browser's `offline` event, show the notice and log `connectionLost` (`reason: no-answer` or `offline`); the next answered signal hides it and logs `connectionBack` with `lostSeconds`. When the page is hidden for more than 1.5 seconds it sends `visible: false` (beacon) and logs `pageHidden`; back on the page it logs `pageVisible` with `hiddenSeconds`. Moving to the next page hides a page only for an instant, so it does not count. Events go through the page's logger as any other, so they wait in its buffer while offline. The service worker handles only GET page loads of the children's app, from the network, and caches one file, `offline.html`, which needs nothing from the server and reloads itself when `/presenza` answers again. Form submissions, the logs, every other request and the dashboard never pass through it. It registers only in a secure context.

**If something looks wrong after this, check**
- The notice appearing while the tablet works → its `/presenza` requests failing (two in a row), or the browser reporting offline.
- A page load misbehaving → `sw.js`; to retire it, serve a version that unregisters itself.
- A test that fakes a page with `page.route()` failing → mark it `no_service_worker`: a service worker's own requests bypass Playwright's routing.

**Left alone**
`logger.js`, the uploads, every existing event, the Back blocker, form submissions and the dashboard's pages.

**Verified**
All 961 server tests and 169 of 170 browser tests passed. The other, `test_original_is_read_only_across_search_results_viewer_and_navigation`, timed out once in the full run, as it also did once on #41; it passed six times in a row alone. New in Chromium: offline shows and online hides the notice, two unanswered signals (on a fake clock) show it and an answer hides it, leaving the app is logged and signalled while a brief hide is not, the offline page while a load fails and the real page once back, and the dashboard left to the browser. Not checked on a classroom tablet yet.

## 2026-11-22 — Show in the live view when a tablet is off the page or silent

**Commit:** pending · **Type:** feature · **Area:** dashboard, infra, tests

**Files**
- `logger/search-app/research_dashboard/presence.py` — new: `Presence`, one row per run in `presence.sqlite3`
- `logger/search-app/research_dashboard/__init__.py` — creates it in the research state folder (`app.extensions["research"]["presence"]`)
- `logger/search-app/search_app.py` — `POST /presenza`: a tablet's page and visibility, stored only for a browser with a run; always answers 204
- `logger/search-app/research_dashboard/live.py`, `live_views.py` — each unfinished child's row gets `presence` (hidden or silent)
- `logger/search-app/research_dashboard/templates/research/session_live_row.html`, `stats_i18n.py`, `static/stats.css` — the badges "Fuori dalla pagina" and "Nessun segnale da N s"
- `logger/search-app/tests/test_presence.py` — new

**What changed for the participant**
No visible change. In the live view, an unfinished child's row says "Fuori dalla pagina" when the tablet's app is hidden, and "Nessun segnale da N s" when nothing has arrived for 30 seconds (Diletta's point 10). The tablets start sending the signal in the next commit.

**How it works**
`/presenza` writes the run's latest signal (`technical_session_id`, participant, page, visible, time) to its own SQLite file with a 0.5-second timeout, apart from the logs, the progress database and the research database. Write errors are swallowed, so the signal can never fail a page or hold a lock that saving a log waits on. The route reads the session but never writes it and never touches `last_active`, so it is not activity for the 60-minute limit. The live view reads the rows of the unfinished children's latest runs; finished and not-started children get no badge, and a visible tablet adds nothing.

**If something looks wrong after this, check**
- No badges although tablets are off → `presence.sqlite3` in the research state folder, and whether the tablets load `connection-watch.js` (next commit).
- "Nessun segnale" for a working tablet → its requests to `/presenza`, and `SILENT_AFTER_SECONDS` (30).

**Left alone**
The logs, the progress and research databases, the live view's other figures and its 5-second refresh.

**Verified**
`tests/test_presence.py`: nothing stored before an ID, a run's page and visibility stored, the session untouched and no log written, malformed signals ignored, a corrupt file never raising, the three states, and the badges in the live view in English and Italian.
## 2026-11-22 — Show a changed "Non lo so" in the dashboard

**Commit:** pending · **Type:** feature · **Area:** dashboard, tests

**Files**
- `logger/search-app/research_dashboard/index.py` — reads `OwnKnowledgeAnswerChanged`; a question's first answer is then the written one, with `changed_from_unknown`
- `logger/search-app/research_dashboard/templates/research/task_stats.html` — the note beside such an answer
- `logger/search-app/research_dashboard/stats_i18n.py` — "first “Non lo so”, changed before searching" / "prima “Non lo so”, cambiata prima della ricerca"
- `logger/search-app/tests/test_first_answer_change_dashboard.py` — new

**What changed for the participant**
No visible change. On a participant's page, "Before searching" shows the written answer and its stars, followed by the note, when the group replaced "Non lo so" before searching.

**How it works**
The index collects `OwnKnowledgeAnswerChanged` per question beside `OwnKnowledgeAnswerSubmitted`. When the submitted answer is "Non lo so" and a change exists, `_task_figures` gives the change as the first answer and adds `changed_from_unknown: True`. Answers that never changed keep exactly the figure they had, so cached and older runs are unaffected.

**If something looks wrong after this, check**
- A changed answer shown as "Don't know" → the run's log lacks `OwnKnowledgeAnswerChanged`, or the event has no text.

**Left alone**
The index version, the final answers, exports (the raw logs carry both events) and every other figure.

**Verified**
`tests/test_first_answer_change_dashboard.py` in English and Italian, with the dashboard answer tests and the full server suite.

## 2026-11-22 — Let a confirmed "Non lo so" become a written answer before the first search

**Commit:** pending · **Type:** feature · **Area:** task-flow, data, logging, docs, tests

**Files**
- `logger/search-app/study_progress.py` — tables `progress_first_answer_changes` and `progress_first_searches`; `change_first_answer()`, `mark_first_search()`; the attempt snapshot shows a changed answer (with `changed_from`) and each question's `searched`
- `logger/search-app/student_progress.py` — `/first-answer/change`; `can_change()`; `mark_searched()`; `/task?change=1` shows the form for a written answer; uploads drop a tablet's own `OwnKnowledgeAnswerChanged`
- `logger/search-app/search_app.py` — `/result` notes the question's first search before searching
- `logger/search-app/templates/first_answer.html` — "Cambia la mia risposta" beside "Entra nel motore di ricerca"; the change form has "Annulla" instead of "Non lo so"
- `logger/search-app/templates/search_first_answer.html` — the same button in the "La mia prima risposta" pop-up, until the first search
- `logger/search-app/static/first-answer.js`, `static/first-answer.css`, `static/main.css` — the form without "Non lo so"; the buttons' spacing; cache versions `change-answer-1`
- `logger/docs/manual_logging_walkthrough.md`, `logger/docs/research_dashboard.md` — the new event and the rule
- `logger/search-app/tests/test_first_answer_change.py`, `tests/test_first_answer_change_browser.py` — new; `tests/test_manual_logging_walkthrough.py` — knows the new server event

**What changed for the participant**
After confirming "Non lo so", a group can tap "Cambia la mia risposta", write an answer and choose its stars, once, as long as it has not searched yet for that question (Diletta's point 11). The button is on the confirmed answer and in the search page's "La mia prima risposta" pop-up; it disappears with the first search. "Annulla" keeps "Non lo so".

**How it works**
Nothing is overwritten. The original "Non lo so" stays in `progress_first_answers` and its `OwnKnowledgeAnswerSubmitted` stays in the log. The written answer goes to `progress_first_answer_changes` and the outbox as `OwnKnowledgeAnswerChanged` (`answer`, `confidence`, `outcome: answered`, `previousOutcome: unknown`, `answerPhase: pre-search`), published like the other server events. `/result` notes the question's first search in `progress_first_searches` before searching, so the change closes even if the browser's session is lost; the session's search keys close it too. `change_first_answer` refuses a written first answer, a second change, a searched question and a question no longer current, and returns the saved change on an identical retry. The attempt snapshot then gives the written answer as the first answer, so the recap shows it. The two tables need no new schema version: the store accepts versions up to 7 and refuses others, so a version change would stop an older image after a rollback.

**If something looks wrong after this, check**
- "Cambia la mia risposta" missing after "Non lo so" → `can_change()`: a search already noted for the question (`progress_first_searches`), or search keys in the session.
- Two different first answers in a log → expected after a change: `OwnKnowledgeAnswerSubmitted` (unknown) then `OwnKnowledgeAnswerChanged`.
- An error in the change form → `first-answer.js` expects no "Non lo so" button there.

**Left alone**
A written first answer, the "Non lo so" confirmation dialog, the final answer, the schema version and the earlier events.

**Verified**
All 963 server tests passed, and 166 of 167 browser tests in the full run. The other, `test_original_is_read_only_across_search_results_viewer_and_navigation`, timed out once right after the full run; it uses a written answer, where none of this shows, and passed in 13 runs in a row afterwards. New: the change and its refusals (searched, written, second change, token, missing text or stars), the search note surviving a lost session, both events, a forged upload dropped, the recap's answer, schema version 7, and in Chromium the whole change and "Annulla".
## 2026-11-22 — End the experiment on an "Alzate la mano" page

**Commit:** pending · **Type:** feature · **Area:** task-flow, styling, docs, tests

**Files**
- `logger/search-app/templates/welcome.html` — standalone welcome/fullscreen host.
- `logger/search-app/static/student-fullscreen.js` — user-triggered entry and browser fallback.
- `logger/search-app/static/student-fullscreen.css` — full-height student frame and keyboard focus.
- `logger/search-app/tests/test_student_fullscreen_browser.py` — entry, navigation, fallback and exit regressions.
- `logger/docs/research_dashboard.md` — setup and browser/device limits.

**What changed for the participant**
Tapping Inizia enters fullscreen when the browser permits it. The child can move
through the study without each page load leaving fullscreen. A refused request
still opens the usual ID page.

**How it works**
The trusted click requests fullscreen on the welcome document, then opens the
student app in one same-origin iframe. Only the inner student app runs its logger
and Back guard. Returning to welcome inside the frame reuses that host.

**If something looks wrong after this, check**
- No fullscreen → browser support, fullscreen policy and whether Inizia was tapped.
- Frame too short → `student-fullscreen.css` and the tablet's viewport/rotation.
- Route appears unchanged → the address bar retains the welcome host's URL.

**Left alone**
Student routes, saved answers, logging contracts, the shared Back guard and the
research dashboard. No installation, device lock or automatic fullscreen on load.

**Verified**
947 server tests and all 174 Chromium browser regressions passed, including nine
fullscreen cases. Ruff and syntax checks for all 12 production JavaScript files
passed. Welcome and fullscreen results screenshots were visually inspected.
No physical classroom tablet is connected for iPad/Safari or Android acceptance.
- `logger/search-app/search_app.py` — new route `/fine` (`finished_page`); `reset=1` clears the session there
- `logger/search-app/templates/finished.html`, `static/finished.css`, `static/finished.js` — new: the end page and the researchers' three-second hold on the logo
- `logger/search-app/student_recap.py` — the recap's Chiudi now sends the tablet to `/fine` instead of the welcome page
- `logger/search-app/templates/study_handoff.html` — "Chiudi l'attività" goes to `/fine?reset=1`
- `logger/docs/research_dashboard.md` — "End of the experiment"
- `logger/search-app/tests/test_finished_page.py`, `tests/test_finished_page_browser.py` — new
- `logger/search-app/tests/test_editable_recap.py`, `tests/test_first_answer_flow_browser.py` — expect `/fine` after Chiudi

**What changed for the participant**
After "Salva l'attività" and "Chiudi", the tablet no longer returns to the welcome page: it shows "Complimenti! Siete arrivati alla fine!", the SOL logo and "Alzate la mano per dire che avete finito!", on the blue screen of Diletta's Figma (point 8). It stays there. A researcher holds the logo for three seconds to bring the welcome page back for the next group.

**How it works**
The recap's restart saves and clears the session exactly as before, then returns `/fine` as the address to open. The end page has the Back blocker and no logger, since the run is closed. `finished.js` starts a three-second timer on `pointerdown` over the logo and cancels it on `pointerup`, `pointerleave` or `pointercancel`; when it runs out it opens `/welcome?reset=1`. The logo fades while held, and the CSS turns off the tablet's long-press menu and selection on it.

**If something looks wrong after this, check**
- The tablet back on the welcome page after Chiudi → the `welcome` value returned by `/recap/restart` in `student_recap.py`.
- The hold not working on a tablet → `finished.js` and the `touch-action`/`-webkit-touch-callout` rules in `finished.css`.

**Left alone**
What Salva and Chiudi save and log, the legacy `end.html` page of runs without progress saving, and the welcome page.

**Verified**
All 951 server tests and all 168 browser tests passed, including the new ones: the page's texts and links, the reset only with `reset=1`, a tap or a 1.2-second press keeping the page, a 3-second hold opening the welcome page, and Back staying on the end page. Not checked on a classroom tablet yet.

## 2026-11-22 — Drop "Prova a rispondere alla domanda:" from the question introduction

**Commit:** pending · **Type:** content · **Area:** task-flow, tests

**Files**
- `logger/search-app/templates/task_intro.html` — the line is gone
- `logger/search-app/tests/test_child_pages.py` — checks the page without it

**What changed for the participant**
The page before each question shows "#1", the question, "Pensi di sapere la risposta?" and Inizia, as in Diletta's Figma. The word "prova" now belongs to the practice question before the ID (PR #44), so the real questions no longer use it (Diletta's point 12).

**How it works**
One paragraph removed from the template.

**If something looks wrong after this, check**
- The question's introduction missing a line → `task_intro.html`.

**Left alone**
"Cominciamo!" and its texts per theme, the answer form and every logged event.

**Verified**
`test_child_pages.py` passed, with the full suites (see the next entry).
## 2026-11-22 — Pass the practice engine's IDs to the app on the server

**Commit:** pending · **Type:** fix · **Area:** infra, docs, tests

**Files**
- `logger/docker-compose.yml` — passes `VERTEX_PROVA_ENGINE_ID` and `VERTEX_PROVA_DATA_STORE_ID`
- `logger/docs/production_readiness.md` — the two lines for `logger/.env`
- `logger/search-app/tests/test_practice_engine.py` — the compose file passes both

**What changed for the participant**
No visible change until the IDs are set on the server; then the practice question appears after Inizia.

**How it works**
`docker-compose.yml` hands the app only the variables it names. Without these two lines the IDs written in the server's `logger/.env` would never reach the app, and the practice would stay off.

**If something looks wrong after this, check**
- The dashboard saying "No search engine is set" although `.env` has both IDs → the container was not recreated after the change (`docker compose up -d`), or one value is empty.

**Left alone**
The other engines' variables.

**Verified**
`test_practice_engine.py` passed.

## 2026-11-21 — Set the practice question in the dashboard

**Commit:** pending · **Type:** feature · **Area:** dashboard, docs, tests

**Files**
- `logger/search-app/search_backend.py` — `theme_engine_ready(theme)`: whether a run of that topic can search
- `logger/search-app/search_app.py` — `topic_search_status(text)` and the four topic words, handed to the dashboard through `app.config`
- `logger/search-app/research_dashboard/question_views.py`, `templates/research/session_questions.html`, `i18n.py` — the line under "Tema della sessione" and the suggestions in the field
- `logger/docs/research_dashboard.md` — "Session topic"
- `logger/search-app/tests/test_class_topics.py` — the line in its four states; `tests/backend_stub.py` — new, the stand-in search backend of the tests that load the whole app, now shared by three of them

**What changed for the participant**
No visible change for the children. On the dashboard's questions page, the topic field suggests `spazio`, `orecchio`, `costellazioni` and `muscoli`, and the line under it says "Tema riconosciuto: muscoli." or, in a yellow warning, that the children's search would show an error: the app does not know the word, or the topic has no engine on the server (naming the two env lines). An empty field says "Nessun tema. Scrivi uno di questi: …".

**How it works**
The topic is free text, and a typo used to show up only in class, as the search error page. `topic_search_status` runs the text through `known_theme` and asks `search_backend.theme_engine_ready`, which is true with no per-topic engines (every run uses the single engine) and otherwise only for a topic that has its own. The dashboard reads the function from `app.config["TOPIC_SEARCH_STATUS"]`, so a dashboard without the children's app (its own tests) shows no line. The line reflects the text as last saved, not as it is being typed.

**If something looks wrong after this, check**
- No line under the topic → `TOPIC_SEARCH_STATUS` in `app.config` (set at the end of the topic code in `search_app.py`).
- A warning although the class searched fine → the topic text saved for the session, and `tools/check_search_engines.py` on the server.
- A test that loads the whole app failing on `theme_engine_ready` → it needs `tests/backend_stub.py`.

**Left alone**
Saving and approving: a warning never blocks them. The engines, the topics and the children's pages.

**Verified**
New tests for the recognised topic, a topic without an engine, an unknown word, an empty field, a dashboard without the children's app, and the status function on the real backend with four, two and no engines. All 976 server tests and 165 browser tests pass. Creating both 2 December sessions in the Italian dashboard, on a copy of the 10 November setup, gives Session 2 with the right ten IDs, the recognised topic and "Pubblicata".

## 2026-11-22 — Add the constellations and muscles topics, each with its own search engine

**Commit:** pending · **Type:** feature · **Area:** task-flow, serp, autocomplete, infra, docs, tests

**Files**
- `logger/search-app/search_app.py` — `TOPIC_NAMES`: the words a session's topic may be typed with, now also `costellazioni` and `muscoli`; `REVIEW_ARTWORK_THEMES` is built from it
- `logger/search-app/search_backend.py` — `VERTEX_THEME_SETTINGS` gains `COSTELLAZIONI` and `MUSCOLI`
- `logger/search-app/student_progress.py` — intro lines for both topics
- `logger/search-app/tools/check_search_engines.py` — asks the two new engines too, and names a topic without an engine instead of failing on it
- `logger/docker-compose.yml` — passes `VERTEX_COSTELLAZIONI_*` and `VERTEX_MUSCOLI_*` to the app
- `logger/docs/production_readiness.md` — "Search engines per theme": the four topics and the words to type
- `logger/search-app/tests/test_class_topics.py` — new; `test_child_pages.py`, `test_search_by_theme.py` — the new topics in the existing cases

**What changed for the participant**
On 2 December class 4 searches constellations and class 5 muscles, each in its own dataset (Google apps `SOL-app-constellations` and `SOL-app-muscles`). The "Cominciamo!" page says "In classe state studiando le curiosità dell'universo." (constellations) or "… del corpo umano." (muscles), then "Ma ci sono ancora tante cose da imparare!": Diletta will write the line about the topic itself. There are no clips or recap drawing for these topics yet, so the page after each question shows the two answers alone and the recap has its plain layout; the recap PDF is text only.

**How it works**
A session's topic is the free text "Tema della sessione" in the dashboard. `known_theme` matches it, ignoring case and extra spaces, against `TOPIC_NAMES` and gives `constellations` or `muscles`. `search_backend` then reads `VERTEX_COSTELLAZIONI_ENGINE_ID` / `_DATA_STORE_ID` or `VERTEX_MUSCOLI_*`. As for spazio and orecchio, once any topic has its own engine, a run whose topic has none gets the search error page and never searches another topic's dataset. `corpo umano` alone still means orecchio, as before, so the muscles topic is typed `muscoli` or `corpo umano (muscoli)`.

**If something looks wrong after this, check**
- Search error page for a constellations or muscles class → the two lines of that topic in the server's `logger/.env`, then `docker compose up -d --wait search_app` and `tools/check_search_engines.py`.
- A class searching the wrong dataset → the topic typed for its session in the dashboard (`corpo umano` is orecchio).
- An orecchio clip on a new topic → `REVIEW_CLIPS` (previous entry).

**Left alone**
Spazio and orecchio: their engines, words, clips, drawings and test IDs. The prova's engine. No test IDs for the new topics yet: they need the real questions.

**Verified**
New tests: each new topic searches and completes on its own engine and never on an old one; the dashboard words pick the topic; the intro lines; a full run on each topic ends on the plain recap with no clip; the engine check with four and with two engines; compose passes the four variables. The topic, search, child page and test-ID tests pass.

## 2026-11-22 — Show a question's clip only for a topic that has clips

**Commit:** pending · **Type:** fix · **Area:** task-flow, tests

**Files**
- `logger/search-app/search_app.py` — `REVIEW_CLIPS`, the topics with clips by clip name; `task_review` shows a clip only for those
- `logger/search-app/tests/test_child_pages.py` — a topic without clips

**What changed for the participant**
No visible change for spazio and orecchio. A topic without clips now shows its two answers alone on the page after each question, instead of an orecchio clip.

**How it works**
`task_review` chose the clip with `'Spazio' if theme == 'space' else 'Orecchio'`, so every other known topic got the orecchio clips, stills and arrows. It now looks the topic up in `REVIEW_CLIPS` and leaves `animation`, `poster` and `piece` empty when the topic is not there; the template then shows its `unlock--none` layout, the two cards side by side.

**If something looks wrong after this, check**
- A spazio or orecchio review without its clip → `REVIEW_CLIPS` and `test_the_review_page_is_the_figmas_with_the_right_clip_and_still`.

**Left alone**
The clips, stills, arrows and `study-review.css`; the recap picture, which already falls back to the plain layout for a topic without a drawing.

**Verified**
The new test fails before the change (an orecchio clip on a "vulcani" review) and passes after it; all child page tests pass.
- `logger/search-app/research_dashboard/practice_views.py` — new: `/dashboard/settings/practice`, saving the practice and trying a search on its engine
- `logger/search-app/research_dashboard/templates/research/practice.html` — new: the page
- `logger/search-app/research_dashboard/templates/research/settings_navigation.html` — a third tab, "Practice question"
- `logger/search-app/research_dashboard/__init__.py` — registers the page
- `logger/search-app/research_dashboard/i18n.py` — the page's English and Italian texts
- `logger/search-app/research_dashboard/static/research.css` — the switch, text area and test results of the page
- `logger/docs/research_dashboard.md` — new section "Practice question"
- `logger/search-app/tests/test_practice_dashboard.py` — new

**What changed for the participant**
No visible change. Researchers get Settings › Practice question.

**How it works**
The page edits the practice's topic, question and switch through `State.save_practice`, with the revision of the form, so a save from an older page is refused. It shows the engine's state from `practice_engine_status` (set, missing, or also used by a class) and whether children will see the practice. **Try a search** runs the practice engine with the words given and lists the first five titles and sites; it saves nothing and shows no provider message, which could hold credentials. The topic's field says that the last page's volcano is fixed in the app.

**If something looks wrong after this, check**
- The tab missing → `settings_navigation.html` and `register_practice_routes` in `__init__.py`.
- "No search engine is set" although the env file has the IDs → the app was not restarted after the change, or one of the two IDs is empty.

**Left alone**
The study settings page and its forms, the session and ID pages, and the practice's child pages.

**Verified**
`tests/test_practice_dashboard.py` (tab, default, every engine state, save, conflict, refused values, token, sign-in, test search and its failures, both languages), the full server suite (1011 passed) and the dashboard browser tests (51 passed).

## 2026-11-21 — Add the practice question before the ID

**Commit:** pending · **Type:** feature · **Area:** task-flow, serp, search-bar, autocomplete, result-viewer, logging, tests

**Files**
- `logger/search-app/practice_question.py` — new: the practice routes under `/prova`, their guards and the practice state in the session
- `logger/search-app/search_app.py` — registers the practice; `practice_engine_ready()`; `practice=False` in the template context; the dashboard's test search and engine status in `app.config`
- `logger/search-app/static/practice-page.js` — new: loaded instead of `logger.js`; a logger stand-in that keeps, stores and sends nothing, plus the "?" and "La mia prima risposta" pop-ups without events
- `logger/search-app/templates/practice_intro.html`, `practice_done.html` — new: "Facciamo una prova!" and "Avete finito la prova!"
- `logger/search-app/static/practice.css`, `static/images/practice/volcano.svg` — new: the last page's layout and a placeholder volcano until Diletta's picture
- `logger/search-app/templates/welcome.html` — Inizia opens `/prova`
- `logger/search-app/templates/first_answer.html` — practice mode: no question number, the Back blocker without the logger
- `logger/search-app/templates/layout.html` — practice mode: `practice-page.js` instead of `logger.js`, the final answer sent with the end request, and `clearClientData` that clears nothing
- `logger/search-app/Dockerfile` — copies `practice_question.py`
- `logger/search-app/tests/test_practice_question.py`, `tests/test_practice_question_browser.py` — new

**What changed for the participant**
After Inizia, a group first does one practice question on volcanoes: "Facciamo una prova!", the question with a first answer (stars or "Non lo so"), the search, a page, the final answer, then "Avete finito la prova!" with both answers next to a volcano. "Inizia" there leads to the ID page, and the experiment goes on as before. When the practice is off in the dashboard, or its engine is not set, Inizia leads straight to the ID page as before.

**How it works**
The practice comes before the ID, so the browser has no participant, run or log yet. Every practice route refuses once a run exists (it sends the browser back to its run), and the run's own routes keep refusing a browser without a run. The practice pages are the real templates with the practice's own endpoints (`PRACTICE_ROUTES`) and `practice=True`. They load `practice-page.js` instead of `logger.js`, so no event is kept, written to the browser's storage or sent, and the tablet's stored data (an earlier group's unsent run, for instance) is never cleared. The answers stay in the server-side session of this browser only, to draw the last page, and leave it when the group goes on to the ID (choosing an ID clears the session too). The question is the dashboard's at the moment the practice begins; a later edit does not change a practice under way. Searches use the practice engine (`theme="practice"`).

**If something looks wrong after this, check**
- A log, progress row or study record appearing for a practice → nothing should write one: `test_a_whole_practice_records_nothing`.
- Inizia going straight to the ID page → the practice is off in the dashboard, or `VERTEX_PROVA_*` is not set on the server.
- A pop-up not opening on the practice's search page → `practice-page.js`, which copies those two blocks from the end of `logger.js`.
- The volcano missing on the last page → `static/images/practice/volcano.svg`.

**Left alone**
`logger.js`, every logged event, the run's routes and their guards, the start page, the questions, reviews and recap of the run, and the session numbering.

**Verified**
All 993 server tests and all 166 browser tests passed, including the practice tests: the whole flow, every refused step and token, that a whole practice leaves no log file, progress row or study record, that a browser with a run never enters the practice, and in Chromium that the practice sends nothing to `/log_session`, leaves the stored data unchanged and the real question empty. Not checked on a classroom tablet yet.

## 2026-11-21 — Let the practice question share the search pages' code

**Commit:** pending · **Type:** infra · **Area:** serp, search-bar, autocomplete, result-viewer, tests

**Files**
- `logger/search-app/search_app.py` — `CHILD_ROUTES` and `child_routes` in the template context; the body of `/result` moved into `search_results_page()`, the probe of `/iframe_check` into `frame_check_response()` and the call of `/autocomplete` into `autocomplete_response()`
- `logger/search-app/templates/home.html`, `search.html`, `webpage.html`, `layout.html` — links, forms and requests name their endpoint through `child_routes` instead of a fixed address
- `logger/search-app/tests/test_child_routes.py` — new: a run's pages keep `/result`, `/webpage`, `/search`, `/autocomplete`, `/iframe_check` and `/end`
- `logger/search-app/tests/ui_fixture.py`, `tests/test_student_navigation_browser.py` — their small test apps provide `child_routes` (and an `/end` route) like the real app

**What changed for the participant**
No visible change. A run's pages render the same addresses as before.

**How it works**
The practice question (PR #44) shows the same search, results and viewer pages, so it must not get copies that drift apart. The real routes keep their guards (the run's phase, the idle limit) and then call the shared function, which does exactly what the route did before. The templates take the endpoint names from `child_routes`, which the app sets to the run's routes for every page; the practice question will pass its own names.

**If something looks wrong after this, check**
- A run's search, page or answer going to a wrong address → `CHILD_ROUTES` in `search_app.py` and `test_child_routes.py`.
- `'child_routes' is undefined` in a page → a Flask app that renders these templates without `search_app`'s context processor (test fixtures included).

**Left alone**
`logger.js`, every logged event, the guards of the run's routes, the session keys of the search, and the result cache.

**Verified**
All 971 server tests and all 165 browser tests passed. The 13 browser tests that first failed did so because their own test apps lacked `child_routes`, fixed in the fixtures.

## 2026-11-21 — Store the practice question apart from the study settings

**Commit:** pending · **Type:** feature · **Area:** data, dashboard, tests

**Files**
- `logger/search-app/research_dashboard/practice_settings.py` — new: the default (volcano question, on) and validation
- `logger/search-app/research_dashboard/state.py` — table `practice_question`; `State.practice()` and `State.save_practice()`
- `logger/search-app/tests/test_practice_settings.py` — new

**What changed for the participant**
No visible change yet (PR #44).

**How it works**
The practice question's topic, text and on/off switch get a table of their own in `research.sqlite3`, with their own revisions. Saving them never writes the study settings, so it cannot move a session, an ID or the settings revision that admission checks before letting a child in. A save from a form opened before someone else's save is refused (`practice_changed`). Before the first save the default applies: on, topic "Vulcani", question "Le eruzioni vulcaniche possono essere di diversi tipi. Sapete elencarne 3?". The table is created with `CREATE TABLE IF NOT EXISTS` and the schema version stays 2, so an older image opens the same database after a rollback and ignores it. Nothing a child does in the practice is stored here or anywhere else.

**If something looks wrong after this, check**
- The dashboard showing the default question after a save → the `practice_question` table in `research.sqlite3`.
- "Saved by someone else" on the practice form → `practice_changed`, raised by `save_practice`.

**Left alone**
The study settings document, its revisions and `SETTING_FIELDS`, the schema version and the migrations.

**Verified**
`tests/test_practice_settings.py` (default, save and read back, conflict, every refused value, study settings unchanged, schema version 2, reopening), with the settings, backup and start-and-recovery tests: all passed.

## 2026-11-21 — Give the practice question its own search engine

**Commit:** pending · **Type:** feature · **Area:** search-bar, autocomplete, infra, tests

**Files**
- `logger/search-app/search_backend.py` — `PRACTICE_THEME`, `load_practice_config`, `practice_engine_status`, `practice_engine_configured`; `vertex_config_for("practice")` returns that engine
- `logger/search-app/tools/check_search_engines.py` — asks the practice engine too when it is set; `--prova-query` for a topic other than volcanoes
- `logger/search-app/tests/test_practice_engine.py` — new

**What changed for the participant**
No visible change yet. This prepares the practice question that comes before the ID (Diletta's point 7, PR #44).

**How it works**
The practice question is on a topic no class studies (volcanoes for now), so it cannot search the spazio or orecchio engine. It has its own slot in the env file, `VERTEX_PROVA_ENGINE_ID` and `VERTEX_PROVA_DATA_STORE_ID`, in the same Google project and with the same credentials as the others. The slot is kept apart from the theme engines (`_theme_configs`): setting it never turns on "each run searches only its theme's engine", and it never changes which engine a run searches. With only one of the two IDs, or none, the practice engine counts as missing and nothing searches in its place. `practice_engine_status` tells the dashboard whether it is set and whether it is an engine a class also searches, without returning any ID.

**If something looks wrong after this, check**
- A run searching the wrong engine → `vertex_config_for`: only the theme `"practice"` reaches `_practice_config`.
- The engine check printing "the practice question is skipped" → both `VERTEX_PROVA_*` values in the server's env file.

**Left alone**
The theme engines, the single engine, autocomplete's SerpAPI fallback, and every route of the app.

**Verified**
`tests/test_practice_engine.py` (practice searches and completes on its own engine; a half-set or missing engine never falls back; a run's engine is unchanged with and without theme engines; the check tool), with `test_search_by_theme.py` and `test_backend_privacy.py`: all passed.

## 2026-11-10 — Leave `__main__` blocks out of the coverage measure

**Commit:** pending · **Type:** infra · **Area:** tests, infra

**Files**
- `.coveragerc` — `exclude_also` for `if __name__ == "__main__":`

**What changed for the participant**
No visible change.

**How it works**
SonarCloud failed PR #36 on coverage of new code: 0%, because its only new coverable line was the `app.run(...)` line in the `__main__` block of `search_app.py`. That block runs only when the file is started by hand, and tests import the module, so no test can reach it. coverage.py now leaves such blocks out of the report: for `search_app.py` the measured lines go from 793 to 790, the three lines of that block.

**If something looks wrong after this, check**
- Coverage of a file dropping or rising by a few lines → its own `if __name__ == "__main__":` block, now left out.

**Left alone**
What the tests run, the 80% threshold on new code in SonarCloud, and the coverage exclusions in `sonar-project.properties`.

**Verified**
The coverage report of one test file was compared with the old and the new setting: only the three lines of the `__main__` block of `search_app.py` disappear.

## 2026-11-10 — Install production packages by hash and copy only named files into the image

**Commit:** pending · **Type:** infra · **Area:** infra, tests, docs

**Files**
- `logger/search-app/Dockerfile` — `pip install --only-binary :all: --require-hashes`; named files and folders instead of `COPY . .`
- `logger/search-app/.dockerignore` — `**/.DS_Store`
- `logger/search-app/requirements.lock` — sha256 hashes for every pin; the versions are unchanged
- `logger/search-app/tools/hash_requirements_lock.py` — new: rewrites those hashes from PyPI after a version change
- `logger/search-app/tests/test_container_image.py` — new: every file and folder is copied or deliberately left out, every pin has hashes, and the hash tool keeps comments
- `logger/search-app/requirements-test.txt` — its comment shows the two install commands
- `.github/workflows/collection.yml` — each install step installs the lock with `--require-hashes`, then the test file
- `.github/dependabot.yml` — comment updated
- `CONTRIBUTING.md`, `logger/docs/dashboard_integration.md`, `logger/docs/research_dashboard.md`, `logger/docs/production_readiness.md` — the same two install commands, and the hash tool after a version change

**What changed for the participant**
No visible change.

**How it works**
These are SonarCloud's three findings on the Dockerfile.
- **Wheels only.** pip installs only wheels, so no package runs its own setup script while the image is built. All 36 pins have wheels for Python 3.14 on Linux x86_64 and arm64.
- **Hashes.** pip refuses any file whose sha256 is not listed in `requirements.lock`. The hashes cover every file PyPI publishes for each version, so the same lock works on the server, in CI and on a Mac. pip cannot mix a hashed file and an unhashed one in one command, so the lock is installed first and the test tools second.
- **Named files.** The image copies six Python files and `data/`, `research_dashboard/`, `static/`, `templates/` and `tools/` by name. It no longer contains `tests/`, the other requirement files, the Dockerfile or `.dockerignore`, which nothing in the container used. Without `COPY . .`, a new module missing from the Dockerfile would be missing on the server, so `test_container_image.py` fails in CI until it is added there or to the test's `LEFT_OUT` list.

**If something looks wrong after this, check**
- Image build fails with "hashes are required" or "do not match the hashes" → a version in `requirements.lock` changed without `python tools/hash_requirements_lock.py`.
- Image build fails with "no matching distribution" → a pinned version has no wheel for Python 3.14 on Linux; choose one that has.
- `ModuleNotFoundError` or a missing template only on the server → a file the Dockerfile does not copy; `test_container_image.py` should have caught it.
- A local install fails with "hashes are required" → the lock and a test file in one `pip install`; use the two commands.

**Left alone**
- The installed versions: `pip freeze` is identical in the old and new images.
- The app's files: the 167 files both images contain are byte-identical.
- Gunicorn's command, and the user the container runs as (still root, until the data volumes are writable for another user).
- The compose files, `deploy.sh` and the pip-audit step.

**Verified**
- **Images compared.** Both images were built on this Mac (arm64). The new one leaves out `tests/`, five requirement and build files and the unused `no_result.html`, and adds only the hash tool.
- **Container checks.** CI's checks passed on the new image: collection seed and verify, backup create, restore and verify.
- **Running server.** Gunicorn started. `/health/ready`, `/start`, `logger.js` and `main.css` answered 200, and the dashboard login answered 503 without a password, the same as the old image.
- **Installs and tools.** The CI install commands ran verbatim in a fresh environment, and pip-audit reads the hashed lock. Dependabot's view of the folder still parses.
- **Suite.** The full suite passed (1112), browser tests included.
- **Not yet.** The x86_64 build runs in CI on the pull request.

## 2026-11-10 — Fix SonarCloud findings in the child pages and the development server

**Commit:** pending · **Type:** fix · **Area:** logging, pagination, styling, infra

**Files**
- `logger/search-app/static/logger.js` — `Math.trunc` in the fallback ID generator; `Number.parseInt` and `Number.isNaN` in `getTargetPage` and `logPageNavigation`
- `logger/search-app/templates/layout.html` — `<html lang="it">`, as the other child pages already had
- `logger/search-app/templates/start.html` — the text above the number menu is now the menu's `<label for="id-box">` instead of a paragraph
- `logger/search-app/static/main.css` — `.form-label-strong` gets `display: block`, so the label sits exactly where the paragraph did
- `logger/search-app/templates/no_result.html` — deleted: its first line said it was never used, and nothing renders it
- `logger/search-app/search_app.py` — `python search_app.py` listens on 127.0.0.1 unless `SOL_DEV_HOST` says otherwise

**What changed for the participant**
No visible change. Screenshots of the start page at 1180×699, 1280×680 and 1024×520 are byte-identical before and after. A screen reader now reads the text with the menu, and browsers know that the start and search pages are in Italian.

**How it works**
These are SonarCloud's open issues on `main` after the release in #34. `Math.random() * 16 | 0` and `Math.trunc(Math.random() * 16)` give the same 0–15 for every value. `Number.parseInt` is the same function as `parseInt`, and `Number.isNaN` gives the same answer as `isNaN` on the numbers `parseInt` returns, so logged page numbers and generated IDs are unchanged. The `app.run` block runs only when the file is started directly: the container runs Gunicorn and the local UI runs `flask run`, so neither is affected.

**If something looks wrong after this, check**
- Page numbers in `pageNavigationClicked` → `getTargetPage` in `logger.js`.
- The text above the start page's menu a pixel lower or narrower → a tablet still holding the cached `main.css` (`child-pages-3`) without `display: block`; it goes once the file is reloaded.
- `python search_app.py` not reachable from a tablet on the network → set `SOL_DEV_HOST=0.0.0.0`.

**Left alone**
The `logger.js` version string (`strict-back-1`) and the `main.css` one: the code behaves the same, so cached copies stay correct. Gunicorn's `-b 0.0.0.0:7001` in the Dockerfile, which the container needs. The Sonar finding on CSRF protection for the student pages (`python:S4502`): the student session cookie is `SameSite=Lax`, so another site cannot post as a child, and the dashboard checks its own CSRF token. A Flask-WTF token would have to travel with every background upload, including the ones sent after a session has ended, and a rejected upload is a lost event.

**Verified**
The full suite passed before (1108 tests) and after (1112, including the four new tests of the next commit), browser tests included. Start-page screenshots were compared byte by byte, before and after. The image was built and served `/start` with the label and `lang="it"`.

## 2026-11-10 — Let Dependabot read the test requirement files

**Commit:** pending · **Type:** infra · **Area:** infra, tests, docs

**Files**
- `logger/search-app/requirements-test.txt` — no longer includes `requirements.lock`; a comment says why
- `.github/workflows/collection.yml` — the three install steps name `requirements.lock` next to the test, browser-test or quality file
- `.github/dependabot.yml` — comment: no `requirements-*.txt` may include the lock file
- `CONTRIBUTING.md`, `logger/docs/dashboard_integration.md`, `logger/docs/research_dashboard.md`, `logger/docs/production_readiness.md` — the local install commands name the lock file too

**What changed for the participant**
No visible change. The app image installs `requirements.lock` exactly as before.

**How it works**
Dependabot became active when `matthias-dev` was released to `main` (PR #34, `35dd88e`). Its first pip run on `main` failed with "Could not open requirements file: requirements.lock": Dependabot copies only `.txt` and `.in` files, and `requirements-test.txt` began with `-r requirements.lock`. Because `requirements-quality.txt` and `requirements-browser-test.txt` include `requirements-test.txt`, all three failed, and the weekly pip update (Mondays 06:00) would have failed the same way. The test files now list test tools only, and whoever installs them names the lock file as well: `python -m pip install -r requirements.lock -r requirements-test.txt`. Each CI job installs the same packages as before.

**If something looks wrong after this, check**
- `ModuleNotFoundError` for Flask or another app package when running tests locally → the install left out `-r logger/search-app/requirements.lock`; older notes outside this repository may still show the one-file command.
- Dependabot's "Graph Update: pip" run on `main` still failing → its log names the file it could not open; look for another `-r` or `-c` that points at a file that does not end in `.txt` or `.in`.

**Left alone**
`requirements.lock` itself and the Dockerfile, so production versions are unchanged and still updated by hand. The pip-audit step, which still audits `requirements.lock`. The GitHub Actions and Docker parts of `dependabot.yml`. `requirements.txt`, which never included the lock.

**Verified**
A script copied only the `.txt` and `.in` files of `logger/search-app` into an empty folder, as Dependabot does, and parsed every requirements file with pip's own parser. On `main` the three test files failed with Dependabot's error; with this change all four parse. CI on the pull request installs and runs the full suite, the browser tests and the quality job with the new commands. Dependabot's own run happens on `main` after the merge.

## 2026-11-09 — Make the browser's back button do nothing on every child page

**Commit:** pending · **Type:** fix · **Area:** back-navigation, logging

**Files**
- `logger/search-app/static/back-guard.js` — new: the back blocker that was in `logger.js`, now loaded by every child page, with two additions (below)
- `logger/search-app/static/logger.js` — the blocker removed; it still records the blocked attempts and reads `window.__SOLBrowserBackRecoveryInProgress`
- `logger/search-app/templates/task_intro.html`, `study_handoff.html` — load the blocker, which they never had
- `logger/search-app/templates/layout.html`, `first_answer.html`, `recap.html` — load it before the logger; `logger.js` as `strict-back-1`, so tablets drop the old copy that still holds the old blocker
- `logger/search-app/templates/first_answer.html`, `task_intro.html`, `study_handoff.html`, `recap.html` — marked as step pages (`data-sol-step-page`)
- `logger/search-app/static/study-review.js` — its own reload on a cache restore removed; the blocker does it
- `logger/search-app/tests/test_back_navigation_browser.py` — new
- `logger/search-app/tests/test_logging_contract.py`, `test_manual_logging_walkthrough.py` — read `back-guard.js` too, where `browserBackBlocked` is now recorded
- `logger/search-app/tests/test_child_pages_browser.py` — the recap's no-reload check counts page loads, since the guard adds a history entry on a tap without leaving the page
- `logger/docs/manual_logging_walkthrough.md` — where `browserBackBlocked` comes from

**What changed for the participant**
On 9 November Matthias found on the iPad that back left the question introduction and the review page, and could bring back a question's answer form after its answer was confirmed; confirming again only gave "La risposta è già stata confermata". Now back does nothing on every child page: the page stays as it is.

**How it works**
The blocker fills the history with copies of the current page and adds them again after each back, as before, but now on every page: the introductions and review pages never loaded it, and the end of a question cleared the last page reached, so nothing sent the child forward from there. A copy is also added on the child's first tap on each page, because browsers may skip copies added without one. If the browser still reaches an earlier page, it sends the child on to the last page reached, and a step page that comes back from the browser's cache at the same address reloads, since `/task` shows the introduction, the answer form and the confirmed answer at one address; the server then shows the current step.

**If something looks wrong after this, check**
- Back leaves a page → that page's template must load `back-guard.js`; `history.state.__solBrowserBackBlockerGuard` is true on a guarded page.
- A page reloads by itself → it is a step page restored from the browser's cache; `browserBackBlocked` with reason `pageshow` is in the log.
- `browserBackBlocked` missing on an introduction or review page → expected: those pages have no logger.

**Left alone**
What the search page and viewer do when restored from the cache (they keep their page and resynchronize, so results are not logged twice), the server's checks that refuse a step already done, the in-app back buttons, the dashboard.

**Verified**
The new browser tests (back twice on every page of a question: introduction, answer form, confirmed answer, search, results, review, next introduction; an answer form and a review page restored from the cache) pass, and all three fail on the previous code. The full suite: 1108 passed. In an earlier full run one search test (`test_original_is_read_only_across_search_results_viewer_and_navigation`, which does not use back) failed once; it passed six times alone, four times run together and in the last full run. Chromium cannot reproduce Safari's cache, so the iPad remains the acceptance check.

## 2026-11-09 — Give TEST-orecchio the questions of 5a orecchio

**Commit:** pending · **Type:** content · **Area:** task-flow, tests

**Files**
- `logger/search-app/research_dashboard/permanent_test.py` — TEST-orecchio's three placeholder questions replaced by the three Diletta entered for 5a orecchio, in the same order; TEST-spazio unchanged, since it already had 4a spazio's
- `logger/search-app/tests/test_permanent_test_experiment.py` — a test that TEST-spazio matches the 4a setup and TEST-orecchio the 5a questions, in clip order

**What changed for the participant**
No change for children. A researcher trying TEST-orecchio now sees the questions the 5a class gets on 10 November ("Quali sono i 3 ossicini dentro al nostro orecchio?", "Che forma ha la coclea e dove si trova?", "Quali sono 5 animali con l'udito più sviluppato al mondo?") instead of "Domanda di prova: …". TEST-spazio already asked 4a's questions.

**How it works**
The questions are copied from the server's stored settings of 9 November, read without writing. A question's position still chooses its clip, so the order is 5a's.

**If something looks wrong after this, check**
- TEST-orecchio showing other questions than 5a → the session was edited in the dashboard after 9 November; the test ID keeps its own copy in `permanent_test.py`.

**Left alone**
The real sessions and their questions, where test runs are saved (`logs-v2/test-runs`), the PROVA banner, `tools/setup_session_2026_11_10.py`.

**Verified**
The test-ID, setup and child-page tests (54 passed) and Ruff.

## 2026-11-09 — Line up the recap's cards under the labels and along the bottom

**Commit:** pending · **Type:** fix · **Area:** task-flow, styling

**Files**
- `logger/search-app/static/recap.css` — the same card places for both themes: first answers in one row under the labels, final answers in one row along the bottom; cards 24.8% x 19.4%; `recap.css` as `child-pages-6`
- `logger/search-app/student_recap.py` — the arrows and magnifiers redrawn for the new places
- `logger/search-app/templates/recap.html` — the new `recap.css` version, so tablets fetch it
- `logger/search-app/tests/test_child_pages_browser.py` — the recap test runs on both themes and checks the two rows, the magnifiers and the stars
- `logger/docs/recap_card_positions_2026-11-09/` — six before and after pictures for the pull request, with the test IDs only; removed again in the next commit, so the description can link to this one and the server's checkout stays without them

**What changed for the participant**
On the iPad the recap's cards sat at different heights, out of line with the "Domanda" labels, and covered the drawings: the dog astronaut, the inside of the ear, the galaxy. Matthias drew where they go, after Diletta asked for the first answers at the top and the final answers at the bottom. The three first answers now form one row just under the labels and the three final answers one row along the bottom, in the same places on spazio and orecchio. The middle of each drawing stays free. On spazio the middle arrow passes left of the dog instead of over it.

**How it works**
Positions only, as shares of the picture. A first answer starts at 9.4% of the picture's height, or lower on a short screen, so its stars never touch the label above. A final answer is anchored 6.6% from the bottom and grows upwards with a long answer. The magnifiers sit at about half the picture's height (48% to 54%), which no card reaches even with a long answer.

**If something looks wrong after this, check**
- A card over a magnifier or a label → the `.recap-stage--space`/`--ear` rules at the end of the positions block in `recap.css`, and `RECAP_ARROWS` in `student_recap.py`.
- Old positions on a tablet → the browser kept the old `recap.css`; the page asks for `v=child-pages-6`.

**Left alone**
The labels and their numbering, the pictures, what the recap saves and logs, the review page after each question (`study_handoff.html`, `REVIEW_ARROWS`), the narrow-screen layout under 620 px, the plain layout for a theme without a picture.

**Verified**
The child-page tests, 42 passed, including the recap test on both themes at 1180 x 699, 1280 x 680 and 1024 x 520 with long answers. The new checks (rows, magnifiers, stars) fail on the previous layout. Pictures of both themes with the test IDs before and after, with short and long answers. Not yet seen on a real iPad or classroom tablet.

## 2026-11-08 — Keep working notes, screenshots and experiments out of the repository

**Commit:** pending · **Type:** infra · **Area:** docs

**Files**
- Removed, and kept locally in `~/Desktop/IDSIA/SOL-logger-local-docs` with the same paths (107 files):
  - `logger/docs/`: `codex_handoff.md`, `issue6_handover.md`, `issue13_handover.md`, `merge_review_2026-10-23.md`, `merge_v2_readiness.md`, `dashboard_review_2026-10-22.md`, `desktop_interface.md`, `desktop_interface_test_results.md`, `editable_recap.md`, `child_pages_2026-11.md` and its 60 pictures, `follow_up_checks.md`
  - `docs/superpowers/` (one plan), `output/playwright/` (23 screenshots), `experiments/` (March 2026 analysis notebooks, CSVs and developer test logs)
- `logger/README.md`, `logger/docs/dashboard_integration.md`, `logger/docs/research_dashboard.md`, `.github/dependabot.yml`, `logger/search-app/tests/desktop_keyboard.js` — no links to the removed files

**What changed for the participant**
No visible change.

**How it works**
The server's checkout no longer carries working notes, screenshots or old experiments. Nothing in the app, its image or the deploy script read them. The changelog, the READMEs and the operating and developer guides stay. Git's history still holds the removed files, and the PR descriptions keep their pictures, which link to fixed commits.

**If something looks wrong after this, check**
- A broken link in a document → it pointed to one of the files above; the local copy has it.

**Left alone**
The app, the tests, the changelog, `production_readiness.md`, `research_dashboard.md`, `dashboard_integration.md`, `local_ui_development.md`, `manual_logging_walkthrough.md`, `research_diagram_contract.md`.

**Verified**
The 107 local copies are byte-identical to the removed files; no remaining file links to them; no test reads them.

## 2026-11-08 — Document Diletta's feedback and the iPad check of 8 November

**Commit:** pending · **Type:** content · **Area:** docs

**Files**
- `logger/docs/child_pages_2026-11.md` — fixes 23-37, the decisions of this round, what was checked and how, what is left
- `logger/docs/child_pages_2026-11/before-r3-*.jpg`, `after-r3-*.jpg` — before and after pictures of this round

**What changed for the participant**
No visible change.

**How it works**
Documentation only.

**If something looks wrong after this, check**
Nothing in the app.

**Left alone**
Everything else.

**Verified**
Every picture the document names exists. The pictures show test IDs, made-up answers and synthetic dashboard runs only.

## 2026-11-08 — Show "Non lo so" as the first answer in the dashboard

**Commit:** pending · **Type:** fix · **Area:** dashboard

**Files**
- `logger/search-app/research_dashboard/index.py` — a first answer with outcome `unknown` counts even though its `answer` is `null`
- `logger/search-app/tests/test_dashboard_answers.py` — the synthetic "Non lo so" is logged as the app logs it, with `answer: null`

**What changed for the participant**
No visible change for the children. In the rehearsal on the production image, a child who chose "Non lo so" had no "Prima della ricerca" for that question in the dashboard. It now reads "Non lo so".

**How it works**
`OwnKnowledgeAnswerSubmitted` for "Non lo so" carries `answer: null` and `outcome: "unknown"`; the dashboard only accepted text. The answers are picked when the runs are rebuilt from the indexed files, so the logs do not have to be read again.

**If something looks wrong after this, check**
- A missing first answer → the run's `OwnKnowledgeAnswerSubmitted` events and `_task_figures` in `index.py`.

**Left alone**
The logs, the index version, everything else on the page.

**Verified**
The test fails without the fix and passes with it.

## 2026-11-08 — Make the recap PDF on a participant's page a download button

**Commit:** pending · **Type:** fix · **Area:** dashboard, styling

**Files**
- `logger/search-app/research_dashboard/templates/research/participant.html` — the link is a compact button with the download icon, as on the run page
- `logger/search-app/research_dashboard/static/stats.css`, `templates/research/base.html` — its spacing; `stats.css` as `dashboard-v2-20261108c`

**What changed for the participant**
No visible change for the children. Under a child's question cards, "Scarica il riepilogo finale del bambino (PDF)" read as plain grey text; it is now a button.

**How it works**
Template and CSS only; the address and the PDF are the same.

**If something looks wrong after this, check**
Nothing beyond the button's look.

**Left alone**
The download itself, the run page's button.

**Verified**
Dashboard tests and a picture of the page.

## 2026-11-08 — Show a child's statistics as one card per question

**Commit:** pending · **Type:** fix · **Area:** dashboard, styling

**Files**
- `logger/search-app/research_dashboard/templates/research/task_stats.html` — `task_table` draws one card per question instead of a wide table
- `logger/search-app/research_dashboard/static/stats.css` — the cards; `stats.css` as `dashboard-v2-20261108b`
- `logger/search-app/research_dashboard/templates/research/base.html` — the new version of `stats.css`
- `logger/search-app/tests/test_task_stats_pages.py`, `test_dashboard_answers.py`

**What changed for the participant**
No visible change for the children. On a participant's page and a run's page, "Statistiche per domanda" was one wide table with the answers squeezed into the first column and small notes under the numbers; Matthias found it chaotic. Each question is now a card: the question, the answers before and after the search side by side, then one labelled value per figure.

**How it works**
Template and CSS only, with the same figures as before.

**If something looks wrong after this, check**
- A figure missing from a card → `task_table` in `task_stats.html`.

**Left alone**
The class table ("La classe, domanda per domanda"), the sessions table and charts, the live view, the figures themselves.

**Verified**
Dashboard tests; pictures of a child with answers and of a May child.

## 2026-11-08 — Show May's question on its run page

**Commit:** pending · **Type:** content · **Area:** dashboard

**Files**
- `logger/search-app/research_dashboard/legacy_topics.py` — `legacy_question` gives a legacy run's topic name and question
- `logger/search-app/research_dashboard/history_views.py`, `templates/research/run.html` — a task with no recorded question shows the one from `data/user_topics.csv`, with a note saying so
- `logger/search-app/research_dashboard/i18n.py` — the note, in both languages
- `logger/search-app/tests/test_dashboard_answers.py`

**What changed for the participant**
No visible change for the children. On a May run's page, "Recorded question" read "Question text was not recorded". It now shows the question May's app read for that ID and topic, next to the topic's name, and says that it was not recorded in the log.

**How it works**
The same lookup as the topic names: `data/user_topics.csv`, for legacy runs from 19 May 2026 on. Runs whose log recorded the question keep it.

**If something looks wrong after this, check**
- A wrong question → the ID's row in `data/user_topics.csv`.

**Left alone**
The logs, exports, runs of this year.

**Verified**
Tests for a May run and an older one.

## 2026-11-08 — Keep the recap's cards inside the picture and its lines visible

**Commit:** pending · **Type:** fix · **Area:** task-flow, styling

**Files**
- `logger/search-app/static/recap.css` — cards 23% wide, all positions inside the picture; a band of the opposite colour under each dashed line; `recap.css` as `child-pages-5`
- `logger/search-app/student_recap.py` — the arrows and magnifiers moved inside with the cards
- `logger/search-app/templates/recap.html` — each line drawn over its band
- `logger/search-app/tests/test_child_pages.py`, `test_child_pages_browser.py`

**What changed for the participant**
Matthias saw on the iPad that some cards and magnifiers stuck out of the picture, as in the Figma. They are now all inside it. The dashed lines were black and disappeared on dark parts: on orecchio they are dark with a light edge, on spazio white with a dark edge, as the Figma draws them.

**How it works**
Positions only. The cards still sit on their question's part of the picture, numbered by the order the child met the questions, as Diletta asked.

**If something looks wrong after this, check**
- Two cards touching → the `.recap-piece--` rules in `recap.css`; spazio's middle and right cards share little room.

**Left alone**
The numbering, what the recap saves and logs.

**Verified**
The recap's browser test at 1180 x 699, 1280 x 680 and 1024 x 520 with long answers, now also checking that every card stays inside the picture; pictures of both themes.

## 2026-11-08 — Put Cerca right after the search bar

**Commit:** pending · **Type:** fix · **Area:** search-bar, styling

**Files**
- `logger/search-app/static/main.css` — the hidden ✕ takes no space (`display: none` instead of `visibility: hidden`)
- `logger/search-app/templates/layout.html` — the comment of `syncClearButton`
- `logger/search-app/tests/test_search_bar_browser.py` — new

**What changed for the participant**
"Cerca" sits right after the search bar, instead of after an empty space kept for the ✕. Once the child types, the ✕ appears between the bar and "Cerca"; the bar gives it the room, so the row keeps its width and stays centred.

**How it works**
CSS only. The script that shows and hides the ✕ is unchanged.

**If something looks wrong after this, check**
- The row jumping when the child types → `.search-field` and `#search-box` in `main.css`: the bar must be the part that flexes.

**Left alone**
Autocomplete, `queryCleared`, the results page's search row beyond this rule.

**Verified**
A new browser test: "Cerca" next to the bar, the ✕ only with text, between the bar and "Cerca", the row centred and as wide before and after typing.

## 2026-11-08 — Open the first answer's pop-up on its title, not on the close button

**Commit:** pending · **Type:** fix · **Area:** serp, styling

**Files**
- `logger/search-app/templates/search_first_answer.html` — `autofocus` moves from the ✕ to the title, which takes `tabindex="-1"`
- `logger/search-app/static/main.css` — no focus ring on the title
- `logger/search-app/templates/first_answer.html`, `recap.html`, `study_handoff.html`, `task_intro.html`, `layout.html` — load `main.css` as `child-pages-3`
- `logger/search-app/tests/test_search_first_answer_browser.py`

**What changed for the participant**
On Matthias's iPad the ✕ of "La mia prima risposta" opened with a dark ring around it, drawn with a small animation, gone after a tap anywhere. That was the browser's focus ring: the pop-up put the focus on the ✕ as it opened. It now puts it on the title, so the ✕ shows only its own light-blue circle.

**How it works**
A `<dialog>` opened with `showModal()` focuses its `autofocus` element. The title is that element now. Tab still reaches the ✕, and Escape still closes the pop-up.

**If something looks wrong after this, check**
- A ring around the ✕ again → which element has `autofocus` in `search_first_answer.html`.
- A screen reader not announcing the pop-up → the title's `tabindex` and `autofocus`.

**Left alone**
`logger.js`, what is logged on opening and closing, where the focus returns after closing, the "?" pop-up.

**Verified**
The pop-up's browser tests, now also checking that the title has the focus when it opens.

## 2026-11-08 — Show the theme and questions of May's experiment in the dashboard

**Commit:** pending · **Type:** content · **Area:** dashboard

**Files**
- `logger/search-app/research_dashboard/legacy_topics.py` — each ID's three topics and questions from `data/user_topics.csv`; `experiment_questions` gives the theme and questions all of a class's IDs had; the two themes of 19 May 2026, India and Spazio
- `logger/search-app/research_dashboard/session_views.py` — a one-day past experiment's row carries its IDs and, when they all had the same questions, its theme and questions
- `logger/search-app/research_dashboard/history_views.py`, `templates/research/overview.html` — on a class's data page for that year, a panel with the experiment's theme and three questions
- `logger/search-app/research_dashboard/templates/research/sessions.html` — the theme next to "Esperimento 19 maggio"
- `logger/search-app/research_dashboard/workflow_i18n.py` — "Tema" and the panel's note, in both languages
- `logger/search-app/tests/test_session_history_rows.py`

**What changed for the participant**
No visible change for the children. In the dashboard, "Esperimento 19 maggio" shows its theme per class: India for the 3rd class (IDs 1-8, 17, 18), Spazio for the 4th (IDs 9-16), with the questions this year's 4th class has again. The class's data page for 2025/2026 lists the three questions.

**How it works**
May's app read each ID's questions from `data/user_topics.csv`; the dashboard reads the same file when it shows the page. A class gets a theme and questions only when all its IDs had the same three. Nothing is saved in the settings.

**If something looks wrong after this, check**
- No theme or questions → the class's IDs have different rows in `data/user_topics.csv`, the experiment is older than 19 May 2026, or it spans more than one day.

**Left alone**
May's classes in the settings, the logs, exports, the sessions of this year.

**Verified**
Tests for both classes, another year, and a class whose IDs had different questions.

## 2026-11-08 — Show each question's answers and the kept recap PDF in the dashboard

**Commit:** pending · **Type:** feature · **Area:** dashboard

**Files**
- `logger/search-app/research_dashboard/index.py` — reads `OwnKnowledgeAnswerSubmitted` and the attempt ID of answer events; each task's figures carry `first_answer` and `final_answer`, each run its `attempt_ids`; index version 4, so the logs are read again once
- `logger/search-app/research_dashboard/templates/research/task_stats.html` — under each question: "Before searching" with the child's stars, and "After searching"
- `logger/search-app/research_dashboard/recap_pdfs.py` — new: a run's recap PDF, read from the children's progress database, read-only
- `logger/search-app/research_dashboard/history_views.py` — `/dashboard/runs/<key>/recap.pdf`, and which runs have one
- `logger/search-app/research_dashboard/templates/research/run.html`, `participant.html` — the download link where a PDF exists
- `logger/search-app/research_dashboard/stats_i18n.py`, `i18n.py`, `static/stats.css`, `templates/research/base.html` — labels in both languages, styles, `stats.css` as `dashboard-v2-20261108`
- `logger/search-app/tests/test_dashboard_answers.py`

**What changed for the participant**
No visible change for the children. On a participant's page each question shows the child's answer before and after searching, with the child's own rating as stars, or "Non lo so" (Diletta's dashboard point 2). Where the child saved the activity, the run page and the participant page offer "Scarica il riepilogo finale del bambino (PDF)": the PDF the server made at "Salva l'attività", now that the tablet no longer downloads it.

**How it works**
The answers come from the logs, `OwnKnowledgeAnswerSubmitted` and `TaskEnded`. Both carry the attempt ID, which is how a run finds its PDF in `progress_recap_exports`; logs naming two attempts get no PDF. The dashboard opens that database read-only. The first refresh after the deploy reads every log again, once.

**If something looks wrong after this, check**
- No answers under the questions → the run's logs have no `OwnKnowledgeAnswerSubmitted` (May's runs have none), or the reporting index was not read again (its `PRAGMA user_version` should be 4).
- No PDF link → `progress_recap_exports` has no row for the run's attempt, the run's logs name no attempt or two, or `SOL_PROGRESS_DB_PATH` is not set where the dashboard runs.

**Left alone**
The logs, exports and their manifest, the children's app, the live view.

**Verified**
Tests: the answers in both languages and as plain text, a version-3 index read again, the PDF with and without a sign-in, a run without a PDF, logs naming two attempts, no children's database.

## 2026-11-08 — Name May's questions by their topic in the dashboard

**Commit:** pending · **Type:** fix · **Area:** dashboard

**Files**
- `logger/search-app/research_dashboard/legacy_topics.py` — new: the topic names of a legacy run, from `data/user_topics.csv`
- `logger/search-app/research_dashboard/index.py` — `classify` adds `topic_name` to a task that has a topic number but no question
- `logger/search-app/research_dashboard/templates/research/task_stats.html` — a question's label falls back to the topic name before the number
- `logger/search-app/tests/test_dashboard_answers.py`

**What changed for the participant**
No visible change for the children. In the dashboard, May's runs read "1. Bandiera India simbolo" instead of "1. 3" (Diletta's dashboard point 1).

**How it works**
The first app's logs record only the topic number. Its topics came from `data/user_topics.csv`, one row per ID, so the dashboard looks the name up there by ID and number when it shows the page. The file last changed on 19 May 2026, so only legacy runs from that day on get a name.

**If something looks wrong after this, check**
- A wrong name → the ID's row in `data/user_topics.csv`, and whether the run is from 19 May 2026 or later.
- A number instead of a name → the run is not in the legacy collection, is older, or its ID has no row.

**Left alone**
The index and the logs, this year's runs (their logs name the question), exports.

**Verified**
Tests for a May run and an older one.

## 2026-11-08 — Give both pop-ups the same round close button

**Commit:** pending · **Type:** fix · **Area:** styling, serp

**Files**
- `logger/search-app/static/main.css` — one rule for the ✕ of the "?" pop-up and of "La mia prima risposta": a 3 px light-blue ring drawn by the button, and no browser focus ring after a tap or on a touch screen
- `logger/search-app/templates/first_answer.html`, `task_intro.html`, `study_handoff.html`, `layout.html` — load `main.css` as `child-pages-2`
- `logger/search-app/tests/test_child_pages.py`

**What changed for the participant**
The ✕ of "La mia prima risposta" is in a circle, like the "?" pop-up's. On the iPad the circle of the "?" pop-up was the browser's focus ring, there only while the button had focus. Both buttons now draw the same ring themselves.

**How it works**
CSS only. A keyboard user on a computer still sees the dark focus ring.

**If something looks wrong after this, check**
- Two rings around a ✕ → the focus rules for `.search-first-answer-close` and `#task-help-modal .close` in `main.css`.

**Left alone**
What the buttons do, Escape, where focus returns, `firstAnswerOpened` and `firstAnswerClosed`.

**Verified**
Child-page tests, the pop-up browser tests, and pictures in WebKit.

## 2026-11-08 — Clear the answer page of small hints and repeated words

**Commit:** pending · **Type:** content · **Area:** task-flow, styling

**Files**
- `logger/search-app/templates/first_answer.html` — without "Pensi di sapere la risposta a questa domanda?", "Conferma la tua risposta per iniziare la ricerca." and "Prima risposta confermata. Ora puoi cercare informazioni."; "La tua prima risposta è:"
- `logger/search-app/templates/search_first_answer.html` — "La tua prima risposta è:" in the "La mia prima risposta" pop-up
- `logger/search-app/static/first-answer.css` — the two rules nothing uses now
- `logger/search-app/templates/task_intro.html` — loads `first-answer.css` as `child-pages-2`
- `logger/search-app/tests/test_child_pages.py`

**What changed for the participant**
Diletta's low-priority points. The answer page no longer repeats the question the introduction just asked, and shows no small grey hints, which distracted the children. "La tua prima risposta è la seguente:" became "La tua prima risposta è:" on the answer page and in the search page's pop-up. A message about a failed save still appears, only when it happens.

**How it works**
Text only. The answer box points `aria-describedby` at the error when there is one, and at nothing otherwise.

**If something looks wrong after this, check**
- A failed draft save with no message → `#first-answer-draft-status`, which this change left alone.

**Left alone**
The "?" pop-up's "La domanda a cui devi rispondere è la seguente:", the draft status line and its messages, the confidence stars, the logs.

**Verified**
Child-page tests and the first-answer browser tests.

## 2026-11-08 — Show today's questions on the whole picture at the end

**Commit:** pending · **Type:** feature · **Area:** task-flow, styling, session

**Files**
- `logger/search-app/templates/recap.html` — today's picture with an orange "Domanda N" over each question's part of it, the two answer cards, the dashed arrow and magnifier; "Salva l'attività", then only "Chiudi"
- `logger/search-app/static/recap.css` — positions from Diletta's Figma frames for spazio and orecchio, as shares of the picture; a plain layout for a theme without its picture and for narrow screens
- `logger/search-app/static/recap.js` — no editing and no arrows between questions; saving sends the draft revisions the page was given
- `logger/search-app/student_recap.py` — the current session only, with its theme and arrows; the child's `/recap/pdf` route removed
- `logger/search-app/search_app.py` — passes the theme to the recap
- `logger/search-app/tests/test_editable_recap.py`, `test_child_pages.py`, `test_child_pages_browser.py`, `test_first_answer_flow_browser.py`

**What changed for the participant**
The last page shows the whole drawing of today's activity, as in the Figma. Over each part of it an orange "Domanda 1", "2" or "3" gives the order in which the child met that question, with what the child knew before and knows now below it. The three session columns, the arrows between questions and editing are gone, and so are "Salva modifiche" and "Scarica PDF". After "Salva l'attività" the page says "La sessione è salvata.", the drawing stays, and "Chiudi" is the only button. The stars of the child's own rating sit on the top edge of the first card. A long answer scrolls inside its card.

**How it works**
A question's part of the picture is its `topic_id`, the slot that also picks its clip on the page after it. If the theme has no picture, or the three questions do not fill slots 1, 2 and 3, they stand side by side instead. On the server "Salva l'attività" is unchanged: it still checks the recap draft revisions of every session it could change (`_check_recap_draft_revisions`), so the page carries them in `data-draft-revisions` and sends them back. The server still makes and keeps the PDF at that moment. Only the child's download is gone, so nothing is saved on the tablet.

**If something looks wrong after this, check**
- "Le risposte sono cambiate in un'altra scheda" on saving → `data-draft-revisions` on the page against `progress_recap_drafts`.
- Cards on the wrong part of the picture → the question's `topic_id` and the `.recap-piece--` rules in `recap.css`.
- Three questions side by side over the picture → the theme is not spazio or orecchio, or the slots are not 1, 2 and 3.
- No PDF on the server → `commit_recap` in `study_progress.py`, which this change left alone.

**Left alone**
What "Salva l'attività" saves and logs, the PDF on the server, `/recap/draft` and `/recap/save-changes` (no page calls them now), the idle limit, earlier sessions' answers.

**Verified**
New tests for the layout, the plain layout and today's questions only. The recap's browser tests rewritten for the save button: a dropped connection, a connection that stays down, an out-of-date page, buttons waiting for their script. A new browser test that the recap fits at 1180 x 699, 1280 x 680 and 1024 x 520 with long answers and no overlapping cards.

## 2026-11-08 — Give the answer cards the subtitle's size on every page

**Commit:** pending · **Type:** fix · **Area:** styling, task-flow

**Files**
- `logger/search-app/static/study-review.css` — `--review-card-size`, the subtitle's size, for every "Cosa sapevi prima" and "Cosa sai adesso" card; after each question the cards are 34% of the picture's width instead of 31%
- `logger/search-app/templates/study_handoff.html` — loads `study-review.css` as `child-pages-2`

**What changed for the participant**
After each question the two answer cards are a little bigger, with text the size of the line under the title ("Andate avanti per scoprire…"). Diletta found them hard to read on a tablet. The final recap uses the same size (next entry).

**How it works**
One size, defined on `.study-review`, which both the page after each question and the recap read.

**If something looks wrong after this, check**
- A card covering more of the animation → only the width changed; the positions are the `.unlock--` rules in `study-review.css`.
- The old size on a tablet → the page still loads `study-review.css` as `child-pages-1`.

**Left alone**
Card positions, clips, the arrow, the texts, the logs.

**Verified**
Child-page tests, and the browser tests at 1180 x 699, 1280 x 680 and 1024 x 520.

## 2026-11-07 — Fit the lost-draft test to the accepted repeat

**Commit:** pending · **Type:** fix · **Area:** tests

**Files**
- `logger/search-app/tests/test_final_answer_draft_browser.py` — after a lost reply the draft is repeated by itself, with no button and no message

**What changed for the participant**
No visible change: the test catches up with "Accept a repeat of a draft save whose reply was lost".

**How it works**
The test expected the old false conflict: a retry button, then "ricarica". What it protects stays: the saved text is not replaced, the revision stays 1, and a reload shows the same text.

**If something looks wrong after this, check**
Nothing in the app.

**Left alone**
The app.

**Verified**
This test and the full suite.

## 2026-11-07 — Document the independent review and its fixes

**Commit:** pending · **Type:** content · **Area:** docs

**Files**
- `logger/docs/child_pages_2026-11.md` — fixes 19-22, what the review changed, and what is left for Matthias
- `logger/docs/child_pages_2026-11/after-recap-buttons-waiting.jpg` — the buttons while the page opens

**What changed for the participant**
No visible change.

**How it works**
Documentation only.

**If something looks wrong after this, check**
Nothing in the app.

**Left alone**
Everything else.

**Verified**
The picture was looked at, and shows a test ID and test answers only.

## 2026-11-07 — Let the server stop cleanly with a browser connection open

**Commit:** pending · **Type:** infra · **Area:** infra

**Files**
- `logger/search-app/Dockerfile` — Gunicorn `--graceful-timeout 2`

**What changed for the participant**
No visible change.

**How it works**
With `--keep-alive 75`, Gunicorn waits at stop for any open idle connection. On the production image a browser connection open during the stop led to a hard kill (exit 137) after about 3.3 seconds. At 2 seconds the server exits by itself, with exit 0, in 2.4 seconds. The independent review pointed this out.

**If something looks wrong after this, check**
- A request cut off during a deploy → it had 2 seconds to finish. Deploy with no class running, as always.

**Left alone**
The keep-alive of 75 seconds.

**Verified**
Measured on the production image with one idle connection, at the default, 5 and 2 seconds.

## 2026-11-07 — Translate the last English labels on the search pages

**Commit:** pending · **Type:** fix · **Area:** serp, result-viewer

**Files**
- `logger/search-app/search_app.py` — the results page's tab title
- `logger/search-app/templates/search.html`, `logger/search-app/templates/webpage.html` — pagination label, thumbnail text and viewer title
- `logger/search-app/tests/test_child_pages.py` — none of them left on the results page

**What changed for the participant**
The tab says "Cerca - Risultati". The other three are read by screen readers, or shown if a thumbnail fails to load.

**How it works**
Text only. Nothing in the scripts or the logs reads these labels.

**If something looks wrong after this, check**
Nothing expected.

**Left alone**
The browser's own messages, which follow the device's language.

**Verified**
A test on the results page, and a search for each string in the scripts.

## 2026-11-07 — Accept a repeat of a draft save whose reply was lost

**Commit:** pending · **Type:** fix · **Area:** task-flow, data

**Files**
- `logger/search-app/study_progress.py` — `save_draft` answers an exact repeat of the save that made the current revision
- `logger/search-app/tests/test_study_progress.py`, `logger/search-app/tests/test_child_pages_browser.py` — the repeat, other text, other stars, an older revision, and a lost reply in a browser

**What changed for the participant**
After a lost reply on a first or final answer draft, the child no longer reads a false "La bozza è cambiata", and saving of the draft carries on.

**How it works**
The saved draft had reached the server, so the repeat looked like an old revision and got a 409, which stopped further draft saves. The automatic repeat in `try-again.js` made this easier to reach. The same rule already applied to recap drafts: same text at the next revision is the same save. For a first answer the stars must match too.

**If something looks wrong after this, check**
- A draft that overwrites newer text → this condition in `save_draft`. Different text, other stars and older revisions are still refused.

**Left alone**
Confirmed answers, which were never affected, and what is logged.

**Verified**
Store tests for each case and a browser test that lets the server save the draft and then drops the reply.

## 2026-11-07 — Keep the recap's buttons disabled until they work

**Commit:** pending · **Type:** fix · **Area:** task-flow, styling

**Files**
- `logger/search-app/templates/recap.html` — "Salva modifiche", "Salva l'attività" and "Chiudi" arrive disabled, with new cache versions
- `logger/search-app/static/recap.js` — enables them once their handlers are attached
- `logger/search-app/static/recap.css` — a disabled button looks faded
- `logger/search-app/tests/test_child_pages_browser.py`, `logger/search-app/tests/test_editable_recap.py` — with the script held back, the buttons wait for it

**What changed for the participant**
The recap's buttons look faded for a moment when the page opens. A tap in that moment no longer does nothing without a sign.

**How it works**
The buttons were enabled before the deferred scripts had attached their handlers, so an early tap was lost. Rehearsal robots needed a second "Chiudi" tap for 4 to 9 children of 20. The independent review confirmed the cause.

**If something looks wrong after this, check**
- Buttons that stay faded → `recap.js` or a script before it did not load: the browser's console and network log.

**Left alone**
What each button does, and what is saved and logged.

**Verified**
A browser test holds `recap.js` back and checks the buttons, and the rehearsals on the production image.

## 2026-11-07 — Reopen a refused recap only once

**Commit:** pending · **Type:** fix · **Area:** session, task-flow

**Files**
- `logger/search-app/static/recap.js` — the reload on a refused save happens at most once in 30 seconds
- `logger/search-app/templates/recap.html` — new cache version
- `logger/search-app/tests/test_child_pages_browser.py` — a save that stays refused

**What changed for the participant**
No change in the normal case, including past the idle limit. If a save stayed refused while the page itself still opened, the page would have kept reloading. It now reloads once and then says "Salvataggio non disponibile. Riprova."

**How it works**
Text buffered on the tablet is sent again when the page opens, so a refusal could lead to another reload. `reopen()` keeps the time of its last reload in `sessionStorage`.

**If something looks wrong after this, check**
- A recap that answers "Salvataggio non disponibile" without reloading → the request's status, and `solRecapReopened` in the browser's storage.

**Left alone**
The idle limit and where the child goes past it.

**Verified**
CI found the repeat: its slower machine ran the test's refused save a second time. A browser test now keeps a save refused and checks there is no second reload.

## 2026-11-07 — Document the fixes from the second iPad test

**Commit:** pending · **Type:** content · **Area:** docs

**Files**
- `logger/docs/child_pages_2026-11.md` — fixes 15-18, the rehearsal, and what is left for Matthias
- `logger/docs/child_pages_2026-11/` — before pictures from the iPad, after pictures from the real app
- `logger/docs/follow_up_checks.md` — the check these fixes still need on a real device

**What changed for the participant**
No visible change.

**How it works**
Documentation only.

**If something looks wrong after this, check**
Nothing in the app.

**Left alone**
Everything else.

**Verified**
The pictures were looked at, and show test IDs and test answers only.

## 2026-11-07 — Log why a child could not start

**Commit:** pending · **Type:** infra · **Area:** session

**Files**
- `logger/search-app/student_progress.py` — the start page's failure now writes its reason to the server's log

**What changed for the participant**
No visible change.

**How it works**
`start_route` answered "Salvataggio non disponibile" without recording why. It now logs the exception first.

**If something looks wrong after this, check**
- A child who gets that page at the start → `docker compose logs search_app | grep "Could not admit"`.

**Left alone**
The page itself, and the 2-second wait in `admission_lock`, because 20 starts in the same instant answered within 0.33 s.

**Verified**
The start tests. One rehearsal run out of six showed this page once, for a reason that was not recorded then.

## 2026-11-07 — Send the child to the start page when the recap has passed the idle limit

**Commit:** pending · **Type:** fix · **Area:** session, task-flow

**Files**
- `logger/search-app/static/recap.js` — a save the server no longer recognises reopens the page
- `logger/search-app/tests/test_child_pages_browser.py`, `logger/search-app/tests/test_editable_recap.py` — the page reopens; past the limit the child reaches the start page, then the closing page

**What changed for the participant**
A recap left open for more than an hour no longer repeats "Salvataggio non disponibile. Riprova." for ever. The next tap or edit leads to the start page, as on every other page. Picking the number again shows "Hai risposto alle tre domande" and "Chiudi l'attività".

**How it works**
Past `STUDENT_IDLE_SECONDS` the recap's routes answer 404 and the session ends, and the script treated that as a failure to retry. It now reloads the page on a 4xx with no message of its own, and the server sends the child where they belong.

**If something looks wrong after this, check**
- A recap that reloads when tapped → which request answered 4xx, in the server's log.

**Left alone**
The 60 minutes, which Matthias chose. The rule that a returning browser never shows the recap again, which keeps one child's answers from the next. So recap changes not yet saved at that point are not kept: see `logger/docs/child_pages_2026-11.md`.

**Verified**
The limit passed on the production image with real IDs, for typing, "Salva modifiche", "Salva l'attività" and "Chiudi".

## 2026-11-07 — Repeat a save after a dropped connection and hold connections open longer

**Commit:** pending · **Type:** fix · **Area:** infra, task-flow

**Files**
- `logger/search-app/Dockerfile` — Gunicorn `--keep-alive 75`, up from its default of 2 seconds
- `logger/search-app/static/try-again.js` — new: tries a failed request three more times, within about 4 seconds
- `logger/search-app/static/recap.js`, `logger/search-app/static/first-answer.js`, `logger/search-app/static/final-answer-draft.js` — their saves use it, and show Italian if the connection stays down
- `logger/search-app/templates/recap.html`, `logger/search-app/templates/first_answer.html`, `logger/search-app/templates/layout.html` — load it, with new cache versions
- `logger/search-app/static/recap.css` — a little space between the answer box and its message, which the focus ring covered
- `logger/search-app/tests/test_child_pages_browser.py`, `logger/search-app/tests/test_first_answer_ui.py` — a dropped request, a connection that stays down, and the extra script

**What changed for the participant**
"Load failed" no longer appears while editing an answer. A real loss of connection says "Connessione non disponibile. Il testo resta qui: riprova.", and the text stays.

**How it works**
Gunicorn closed an idle connection after 2 to 3 seconds. A tablet that sent a save on a connection just being closed got an immediate failure, which Safari words as "Load failed". A child typing slowly hits this often, more so over a VPN. WebKit closed idle connections itself after about 29 seconds in our measurement, so at 75 seconds the browser closes first and the race goes away. The repeat covers what is left. The server accepts a repeat of the same recap save.

**If something looks wrong after this, check**
- Many open connections on the server → `--keep-alive` in the `Dockerfile`. An idle connection holds no worker thread.
- A rare "La bozza è cambiata" on a first or final answer → a repeat after a lost reply. The text stays, and "Conferma" still works.

**Left alone**
`/log_session`, which already keeps a batch until it is acknowledged, and what is saved and logged.

**Verified**
See "Load failed" in `logger/docs/child_pages_2026-11.md`: reproduced in WebKit on the production image, then repeated on the fix.

## 2026-11-07 — Warn the child in Italian whatever the tablet's language

**Commit:** pending · **Type:** fix · **Area:** task-flow

**Files**
- `logger/search-app/templates/first_answer.html`, `logger/search-app/templates/start.html` — `novalidate`, so the browser no longer words these warnings itself
- `logger/search-app/static/first-answer.js` — the warnings for no answer and no stars, in Italian
- `logger/search-app/search_app.py`, `logger/search-app/templates/error.html`, `logger/search-app/templates/layout.html` — the 404, 500, search-failure and missing-questions pages, the start page's message and the tab title
- `logger/search-app/tests/test_child_pages.py`, `logger/search-app/tests/test_child_pages_browser.py` — Italian on a browser set to English
- `logger/search-app/tests/test_session_draft_visibility.py`, `logger/search-app/tests/test_study_enrollment.py` — they pinned the English half of the start page's message

**What changed for the participant**
Tapping "Conferma" without stars says "Scegli quanto è giusta la tua risposta." instead of the iPad's "Select one of these options". The same goes for the empty answer box, and the error pages are in Italian.

**How it works**
A `required` field makes the browser write its own warning in the device's language. The forms turn that off, and `first-answer.js` sets the text with `setCustomValidity` before asking the browser to show it, so the warning still appears in the same place.

**If something looks wrong after this, check**
- A form that goes through with no stars → the `submit` handler in `first-answer.js`. The server refuses it anyway, with its own Italian message.
- The dashboard's 404 is now in Italian too, because the two share that page.

**Left alone**
`searchError` still logs `Connection Error`, so log analysis keeps its value. The dashboard's own pages.

**Verified**
A browser test set to English, on the production image, and the full suite. Matthias's iPad still has to confirm the warning, because the browser draws it.

## 2026-11-07 — Drop the question prompt once the first answer is confirmed

**Commit:** pending · **Type:** fix · **Area:** task-flow

**Files**
- `logger/search-app/templates/first_answer.html` — "Pensi di sapere la risposta a questa domanda?" appears only while the form is open
- `logger/search-app/tests/test_child_pages.py` — the prompt on the form, and not on the confirmed page

**What changed for the participant**
The page that shows the confirmed first answer no longer asks whether the child knows the answer. The question and the answer stay.

**How it works**
A condition on `first_answer` in the template.

**If something looks wrong after this, check**
- The prompt missing from the form → the condition in `first_answer.html`.

**Left alone**
What is saved and logged, and the same prompt's short form on the question's introduction.

**Verified**
A test on both states of the page, and on the production image.

## 2026-11-07 — Document the child page fixes with before and after pictures

**Commit:** pending · **Type:** content · **Area:** docs

**Files**
- `logger/docs/child_pages_2026-11.md` — each fix, the decisions, the awkward cases tried, and what was left for Matthias
- `logger/docs/child_pages_2026-11/` — before and after pictures, with test IDs and test answers only
- `logger/docs/follow_up_checks.md` — where the rehearsals stand

**What changed for the participant**
No visible change.

**How it works**
The iPad pictures are cropped to the page, so the server's address and the device's status bar stay out of a public repository.

**If something looks wrong after this, check**
- A picture that no longer matches the page → the page changed after 7 November, and this record did not.

**Left alone**
All code.

**Verified**
Each picture opened and checked for real IDs or answers. The review pictures are named by the clip each one shows, since question order is random.

## 2026-11-07 — Keep "Avvia animazione" off the answers

**Commit:** pending · **Type:** fix · **Area:** styling

**Files**
- `logger/search-app/static/study-review.js` — the button joins the page's buttons, and is not offered for a clip that cannot load
- `logger/search-app/static/study-review.css` — its old position removed
- `logger/search-app/tests/test_child_pages_browser.py` — both cases

**What changed for the participant**
A tablet that blocks autoplay offers "Avvia animazione" beside "Prossima domanda", not on top of an answer card. A clip that cannot load leaves its still on screen, with no button that does nothing.

**How it works**
`play()` rejected with `video.error` set means the file failed, so nothing is offered. Any other rejection means the browser wants a tap.

**If something looks wrong after this, check**
- No animation and no button → the MP4's address and `video.error` in the browser.

**Left alone**
What is logged, and the normal case where the clip plays by itself.

**Verified**
Browser tests with `play()` refused and with the MP4 blocked.

## 2026-11-07 — Back from an introduction no longer starts the question

**Commit:** pending · **Type:** fix · **Area:** task-flow

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
