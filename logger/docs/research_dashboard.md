# Private research dashboard

The researcher entry point is **http://solar.usilu.net:7001/dashboard** on the
existing USI network/VPN. It has a shared password and switchable English/Italian
UI. It uses Flask/Jinja, with its own templates, styles, server-side authentication,
CSRF tokens and storage. Student session resets and browser storage do not grant
or reuse research access. The research pages never load the student logger.

## First deployment

1. Follow the [production readiness and recovery guide](production_readiness.md).
   Schedule the first upgrade after all children have finished: it replaces the old
   shared signing key. Back up all collection/state directories before upgrading.
2. Build the image and configure the private credentials below before running
   `scripts/deploy.sh`. The deploy script refuses a dirty server checkout, preserves
   the previous image, takes a verified backup and waits for readiness. Normal Compose
   builds from a clean checkout should supply the revision explicitly:
   `SOL_GIT_COMMIT="$(git rev-parse HEAD)" docker compose build search_app`
   (run from `logger`). The app-version label defaults to `v2`; override
   `SOL_APP_VERSION` at build time for later releases. Unknown revisions stay
   unknown; historical logs never inherit the currently running version.
3. From `logger` on the server, set a password interactively:

   ```bash
   mkdir -p research-secrets
   docker compose build search_app
   python3 search-app/tools/setup_runtime_secret.py research-secrets/student-secret
   docker compose run --rm --no-deps --volume "$PWD/research-secrets:/secrets" search_app python tools/set_research_password.py /secrets/password.hash
   ```

   The helper prompts without echo, stores a salted scrypt hash in a mode-0600
   file, and never prints the password or hash. The normal service mounts this
   directory read-only. Missing, unreadable, plaintext or invalid credential
   configuration disables research access (503), including exports and APIs.
   No credential is committed. Rotating the hash invalidates existing research
   sessions on their next request; no app restart is needed.
4. Open `/dashboard`, log in, choose a UI language, and open **Study settings**.
   Defaults are exact IDs `1`–`20` for 4th Grade and `21`–`40` for 5th Grade.
   Set **Current school year** (for example, `2026/2027`) for newly started runs.
   In **Sessions**, choose one grade. Expand a session in **Session history** to set
   its name or date and save that session. Use **New session** in the same grade view
   to add a dated session with an optional name, up to 100 per grade. History shows
   ten sessions at a time, newest first, with older pages available. Dates use Europe/Zurich.
   Prepare the three V2 sessions per grade with explicit dates; no monthly spacing is required.
   Use **Configure questions** for each session to enter three topics/questions or explicitly
   load previous questions from the library, edit them, and approve the assignment.
   Blank dates and incomplete/unapproved drafts stay unavailable to students.
   The library remains available without puzzle files. No old per-ID assignment is carried
   into V2 Session 1. Existing extra sessions and their history remain accessible.
   3rd Grade starts without any numbered sessions. Saved historical assignments
   remain active, but their editing controls are currently hidden.
5. Verify a test run, its question/answer association and a task/participant ZIP
   before classroom collection. **Participants** controls the shared roster. Its session
   selector shows readiness for the chosen session. All IDs use that grade/session
   shared question set unless **Set individual questions** saves an exception for that ID.
   Removing an exception returns that ID to the shared set. A saved incomplete exception
   blocks that participant rather than falling back to shared or legacy questions.
   Students can start only on the configured date in Europe/Zurich; otherwise the app
   displays **Session not available**. Missing an earlier session does not block today.
   Each child must retain the same ID across all study sessions; a tablet number
   may serve as that ID only if the assignment to the child is maintained.

The app must keep the configured data and state directories on the same server.
No importer, external collection service or cross-server synchronization is added.

## Storage and configuration

| Host directory (Compose) | Purpose |
| --- | --- |
| `logger/logs` | Existing archive, mounted read-only at `/app/legacy_logs` |
| `logger/logs-v2` | Fresh V2 log collection, mounted at `/app/logs` |
| `logger/research-state` | Private settings history, immutable attempt snapshots, auth, throttle state and rebuildable index |
| `logger/research-secrets` | Private password hash and stable student signing key; never indexed or exported |
| `logger/student-sessions` | Persistent student cookies’ server-side state and frozen task order/questions |

All five directories should be backed up with access restricted to researchers
and server administrators. Do not publish them through a web server's static root.
An empty V2 directory is intentionally separate from the old collection. **Legacy**
records have their own identities; numeric ID `6` in Legacy is not automatically
the V2 child `6`. Explicitly classified historical records appear alongside the
current collection in the dashboard's grade/session downloads, with separate
collection identities and archive folders. API exports explicitly selecting
`collection=v2` continue to contain only V2 sources.

| Setting | Default / meaning |
| --- | --- |
| `SOL_LOG_DIR` | `logs_v2` outside Compose; new student log destination |
| `RESEARCH_LEGACY_LOG_DIR` | `logs` outside Compose; earlier read-only collection |
| `RESEARCH_STATE_DIR` | `research_state` outside Compose |
| `RESEARCH_PASSWORD_HASH_FILE` | Private hash file; Compose sets `/app/research-secrets/password.hash` |
| `RESEARCH_PASSWORD_HASH` | Alternative secure server configuration; only used without a hash file |
| `RESEARCH_COOKIE_SECURE` | `0` for the explicitly selected existing HTTP/VPN deployment; set `1` with HTTPS |
| `SESSION_COOKIE_SECURE` | Student cookie HTTPS setting; set `1` with HTTPS |
| `SOL_ENV` | Compose sets `production`; production requires a configured private signing key |
| `SOL_SESSION_DIR` | Persistent filesystem sessions; Compose sets `/app/flask_session` |
| `FLASK_SECRET_KEY_FILE` | Stable private student key; Compose sets `/app/research-secrets/student-secret` |
| `FLASK_SECRET_KEY` | Alternative private environment value; at least 32 characters |
| `SOL_APP_VERSION`, `SOL_GIT_COMMIT` | Build-time version metadata captured for newly started runs |

For direct local Flask use from `search-app`, set `RESEARCH_LEGACY_LOG_DIR=../logs`
to inspect this checkout's existing archive. The `scripts/local-ui.sh` preview
uses separate Docker volumes for V2 logs, Legacy preview logs and research state;
it does not write to the server collection or this checkout's historical logs.
The preview shares the local password-hash mount, so configure a local test password.

### Connection and authentication limits

The user-selected initial URL uses **HTTP on the existing USI VPN/network**.
The dashboard password is access control, not transport encryption. Credentials,
auth cookies and research responses are not encrypted by Flask over HTTP;
protection in transit depends on the actual network/VPN path. This is an explicit
deployment limitation, not a claim of HTTPS security. Keep port 7001 restricted to
the existing private network. For an HTTPS reverse proxy, set both secure-cookie
flags to `1` and restrict direct HTTP access to the backend. No proxy-supplied
client-address headers are trusted by default.

The research cookie is opaque, HttpOnly, SameSite=Lax and scoped to `/dashboard`.
It expires after 30 minutes without a research request or 8 hours absolute. Logout
revokes the server record. Authentication and failed attempts are stored in SQLite,
shared by the two Gunicorn workers, independently from Flask's participant session.
Five failed attempts per source IP in a rolling 15-minute window (and a global cap
of 100 attempts) throttle further password checks. A NAT/proxy can make several
researchers share the same source-IP limit. All research POSTs, including login,
require a session-bound CSRF token. Research responses use `no-store`, escaped
templates, a restrictive CSP, and no credentialed CORS. Existing student CORS
explicitly excludes `/dashboard` and its descendants.

## Research interpretation

- A **study session** is the configured grade/date classroom experiment. It is
  separate from the technical session UUID, log ID and application run.
- New runs snapshot the explicitly selected session ID, name, date, question theme,
  stable question IDs, wording, metadata and randomized order. Editing the calendar or
  assignment does not change those snapshots or reclassify recorded runs. Older
  sidecars with a session ID keep that ID; records without an ID retain date-based
  historical classification. Crossing midnight does not change the chosen session. Every restart/run is retained;
  repeated runs appear separately and are never merged into one answer set.
- The roster preserves exact strings, including configured prefixes and digit
  padding. `01` and `1` are different. Overlapping generated IDs and duplicate dates
  for the same grade are rejected. Unknown or conflicting identities are visible
  in **All participants** for the current collection or **Historical collection**
  for the archive, never inferred from sanitized filenames.
- Grade and school year captured in new run metadata are preserved if settings
  later change. Historical assignments classify older records using their source
  collection, exact participant ID and date; current roster ranges provide a
  fallback for V2 records without a recorded grade or historical assignment.
  Calendar edits reclassify dates explicitly; prior settings revisions are retained in
  `research.sqlite3`, and exports name the revision used. Settings saves use an
  optimistic revision check to prevent concurrent researchers overwriting each other.
- Starting a V2 run writes an immutable `.run.json` sidecar containing the original
  participant ID, technical IDs, Swiss start date, grade, school year and session mapping then
  known, settings revision, actual app version/commit, and presented task order with
  topic IDs, titles and question text. The snapshot is first committed to
  `research.sqlite3` in the same transaction that rechecks admission. If sidecar
  publication fails, the snapshot remains recoverable; uploads and dashboard refresh
  retry publication. If durable admission fails, START fails visibly and preserves
  any existing student attempt. Historical questions and versions remain unknown
  when the original records do not contain them.
- A task is **Completed** when its canonical logs contain a `TaskEnded` event with a
  string-valued answer. An explicitly empty string is a submitted empty answer;
  an absent field or null/non-text value is not treated as a valid recorded answer.
  A run is **Completed** only when presented tasks 1, 2 and 3 all meet that rule.
  Conflicting task identities are flagged. Multiple answers are all retained and
  shown; none is silently selected as authoritative. `experimentFinished` separately
  confirms that final-save interaction. File existence and `rewardShown` alone do
  not prove completion. An incomplete run might still be in progress: the dashboard
  does not claim to know whether its browser is open.
- Full Task means all three tasks within **one run**. The full log is the canonical
  event view when available; task copies are not added. If absent, available logs
  are used with a visible warning. Differences between full/task copies are flagged;
  originals remain available in exports. Fallback file order is deterministic, not
  a claim about global event chronology.
- Metadata is written at run start; interaction logs still upload at task submission
  and experiment finish. No periodic browser upload or live activity tracking was
  added. Answers existing only in browser storage are not available to researchers.

## Index and data quality

`index.sqlite3` is disposable: with the app stopped, removing it rebuilds the index
from the configured source directories on the next authenticated data request.
Do **not** delete `research.sqlite3`, which stores settings history and login state.
The index checks directory entries at most every 30 seconds, or on **Refresh saved
data** / export, and reparses only files whose inode, size or modification time
changed. No browser request supplies filesystem paths. Symlinks and non-regular
files are rejected. Only direct `.log` and `.run.json` sources are considered.
The registry is deliberately not authoritative: the inspected archive had 96 logs,
but its registry referred to only 41 distinct task files and included repeated saves.

Overview requests read compact run summaries. Participant details load on demand;
individual run views load indexed event offsets in pages of 100. A source changed
since indexing produces a refresh message instead of reading stale offsets.
Malformed JSON, non-object records, incomplete final lines, conflicting identities,
unreadable sources and missing task/full files are surfaced without editing sources.
Lines over 1 MiB are not parsed into the UI; original bytes remain exportable. Up
to 50 line-level issues per file are indexed, with other file/run issues also shown.

## Dashboard navigation and downloads

The dashboard focuses on opening logs and downloading the selected participants
or a complete grade. Grade navigation offers **All participants**, **3rd Grade**,
**4th Grade** and **5th Grade**. The participant list is shown directly, without
participant search, status-filter cards, or a separate filtered-results download.
Old `q` and `status` URL/form parameters are ignored, so old links cannot hide rows.

Each participant row shows **Logs available** or **No saved data**, with the
completion ratio for any saved runs. Metadata without original log files is
labelled **Record without log files**. No saved data does not prove the student
has not started: the dashboard shows saved submissions. **Visualize logs** opens
the participant's saved runs and their details. Log management remains in the
row's **More actions** disclosure.

Tick one or more participant checkboxes and use **Download selected** above the
list to receive their logs together in one ZIP. One checkbox selects that
participant's saved runs in the displayed grade/session/year scope. Participants
without downloadable logs cannot be selected. The button stays visible and becomes
enabled after selection in browsers supporting CSS `:has`; other browsers keep
server-validated submission available. The server rejects selections outside the
current view. A participant's individual download remains available on their
detail page.

**Download all [grade]** beside the grade navigation exports that grade's complete
history, including repeated and incomplete runs, across all years and sessions.
In **All participants**, **Download a full grade** offers the three grades. The
entire-grade export uses grade at collection, so earlier 4th-grade records remain
in the 4th-grade download even if a participant is now in 5th grade.

Session history and settings can open a view scoped to a specific session or
school year. A compact context strip identifies that scope and offers **Show full
history**. Populated session views also retain **Download session**, covering all
participants in that grade/session and displayed year. Switching grade navigation
returns to complete history. **Refresh saved data** preserves grade/session/year;
the last index time is visible beneath it.

**All participants** includes the current collection and classified historical
records with a **Grade at collection** column. It retains recorded IDs outside
the current roster. Historical source collections remain separate participant
entries even when their IDs match. School years and current-grade differences
remain visible on rows. Records with unknown/conflicting identity are shown in a
separate disclosure. Unclassified archive records remain accessible through
`/dashboard?collection=legacy&grade=all`. The compatibility `visible` selection
export API remains available, but has no dashboard button.

The participant page has an **All sessions / Session N** dropdown. All sessions
shows only sessions with saved runs; an empty history shows one **No data** message.
Selecting a particular session can show its empty state. **Visualize logs** reveals
the selected session's saved runs, each with its own **Visualize logs** and
**Download** buttons. The session **Download** button exports that participant's
entire study session. Empty sessions have no actions. Technical identifiers remain under
**Technical details** on run pages. Run pages retain task tabs, original files and
paginated events. Each original file also has **Visualize logs** and **Download log**:
the individual viewer displays only that source file, in pages of 100 events, even
when it differs from the full log used for the combined run view. Event details are
expandable; malformed records and changed/unreadable sources show a message.
All viewers and downloads require researcher authentication.

**Manage logs** opens a participant's run list. Each run has a collapsed **Move run
to Trash** control with a separate confirmation button; this targets one run and
all of its log files, rather than an ambiguous participant row. Trashed runs are
removed from dashboard views and all downloads. The original files remain on disk
and continue to be indexed; **Trash** in the header lists them and offers
**Restore**. This is a reversible dashboard exclusion, not physical file erasure.

**New session** opens a form for the selected grade and date, with an optional custom name.
Creation automatically assigns the next number for that grade and opens the new session in the dashboard.
Each grade supports up to 100 sessions. Existing IDs, dates, participant ranges and
logs are preserved; the initial 1–3 sessions remain available. Numbered study
sessions are independent of the three tasks within each run.

### Removing an unused session

Expand the session in Study settings, open **Remove session**, review its identity
and confirm. Removal retains a tombstone (`removed: true`) in settings history,
reserving its number and ID and preserving its questions and participant exceptions.
It hides the session from normal calendars and new student eligibility. Other
sessions are never renumbered. **Removed sessions** provides restore, with a date
field to resolve any date conflict. Removed entries still count toward the existing
100-number limit per grade.

The server refreshes the index and checks original records before removing a
session, including metadata-only starts, trashed runs and classified historical
records. A session with records is protected; uncertain source availability also
blocks removal. No log files are erased. Removal and durable attempt admission
share an atomic settings check: either removal wins and START is rejected, or
START wins and removal is blocked, including while a sidecar is still unpublished.
#6 should extend this admission boundary when adding durable progress. Removing/cancelling a session with
collected data is not provided by this unused-session control.

**Study settings** shows one section at a time: **School year**, **Sessions** or
**Participants**. School year is the entry view and applies to newly started runs.
Sessions and Participants have compact grade navigation; links retain the selected
grade and language. **New session** creates the next number for that
grade and date; its optional name can be changed later without changing the number or
which runs belong to that session. **Session history** shows ten sessions per page,
newest first. Expand a session to edit its name or date with **Save session** or to open
its dashboard results. Older pages keep all 100 sessions accessible. **Participants**
opens a saved setup view with readiness counts and ten participants per page.
**Need tasks** filters IDs whose selected session configuration is incomplete.
Choose **Edit setup** to edit only the selected grade's ID range; custom ID formatting
is optional. **Review changes** validates the draft without saving and opens a review
screen showing the proposed IDs and readiness for the selected session. **Back to editing** retains
the draft; **Save changes** applies it and returns to the saved setup view.
The other grades, school year and session calendars are preserved.
The review identifies IDs gaining or losing a complete assignment for the selected
session. The participant list shows exact IDs, assigned questions and any missing
date, incomplete questions or pending approval. A 3rd-grade roster is optional.
Student login lists roster IDs; the server checks the current Zurich date and that
participant's approved session assignment before creating a run. Configuration is
shared across workers without an app restart. Started runs keep their questions,
metadata and order if settings later change.
Removing IDs from the current roster does not delete their collected logs.
Each save changes only its named setting, so editing a session does not change
the year or participant ranges.
Validation errors keep the relevant editor and entered values visible. Concurrent
edit conflicts also retain the submitted revision until **Reload saved settings**,
so retrying cannot silently overwrite another researcher's change.
Numbers and session IDs stay stable. Missing date fields in a settings submission
do not clear other sessions. Dates must be unique within a grade; different grades may
use the same date. Adding sessions and updating dates retain prior settings
revisions, reject stale simultaneous edits, and never edit original log files.

## Future experiments and schools

The current collection has the stable study ID `sol-longitudinal`. New V2 run
sidecars capture that ID; older records without it are interpreted as part of
this study. Exports identify the study for each run and use a study folder in the
ZIP. A run explicitly tagged with another valid study ID cannot enter this study's
participant list or grouped downloads. This protects repeated participant IDs
and session numbers from accidental cross-study analysis.

For a later experiment, use a separate study with its own stable ID and student
collection configuration. Within that study, researchers should filter by school,
grade, school year and session. Its configuration must include school identities,
grade labels, participant-ID rules and dated sessions scoped to that study. A new
run must capture study and school IDs, grade and year at collection. Reusing the
current study's settings for a different experiment would change how old records
are classified, so it is not a substitute for a new study.

The dashboard currently operates one configured study. Creating or activating
another study, adding schools and configuring its student questions are future
work that needs the actual experiment's details. The grade, session and download
controls are dropdowns so they can accept more choices without adding more tabs
or header buttons.

## Historical grade and school-year setup

Historical assignment editing is temporarily unavailable in Study settings. Rules
already saved in research state remain in force and are retained by all Study
settings saves. The dashboard still distinguishes grade at collection from the
current roster grade, and recorded V2 grades remain available without assignments.
Unclassified old archive records remain accessible through the authenticated
`/dashboard?collection=legacy&grade=all` route. New assignments cannot be made
through the dashboard until an archive management workflow is designed.

The stored assignment format specifies source collection, grade at collection,
school year in `YYYY/YYYY` format, inclusive date range, and exact participant-ID
range, with optional prefix and digit padding. Rules covering the same IDs, dates
and source collection cannot overlap. The same IDs can have different grades in
different years.

For last year's cohorts, assign the former 3rd-grade records to **3rd Grade** and
the former 4th-grade records to **4th Grade**, using the actual dates and IDs from
that collection. Today's roster can remain 4th/5th grade. No year boundaries or
historical ID ranges are guessed or configured automatically. Inspect the historical
collection before setting up the future archive workflow. Create dated sessions
for those earlier grades as needed; numbering remains stable and can continue
across school years.

A recorded grade or school year takes precedence over a later assignment. A
conflicting assignment is flagged on the run page and in exports; the source
metadata stays unchanged. Participant and run pages distinguish **Grade at
collection**, **School year**, and the current roster grade when different. The
manifest includes classification provenance, the assignment ID and settings revision.
Existing assignments retain their prior settings revision; no Study settings action
deletes or changes an assignment.

**Current school year** is captured only for newly started V2 runs. Changing it
does not relabel earlier runs. Historical records from different source collections
remain separate participant entries, labelled **Historical records**, even if their
numeric IDs match. Linking those entries requires confirmation that the IDs identify
the same children across years; this feature does not make that assumption.

| Button | Location | Exact scope |
| --- | --- | --- |
| **Download log** | Original log files in a run/task view | One original `.log` file, downloaded directly with its original filename |
| **Download selected** | Above the participant list | Only checked participant rows, including their saved runs within the displayed grade/year/session |
| **Download** (participant session) | Populated participant session | One participant, one numbered study session, all saved runs within the displayed school year |
| **Download session** | Context strip in a populated session view | All participants in that grade and selected study session, within the selected school year |
| **Download all [grade]** | Beside grade navigation | Grade at collection across its entire history, including classified archive records and runs with unmapped dates; independent of year/session context |
| **Download participant** | Participant heading | That participant's history in the selected collection, within the displayed grade/year filters |
| **Download** (run) / **Download run ZIP** | Populated session's run row / Full Task view | That single technical run, including its full/task logs and metadata |

All grouped downloads include repeated and incomplete runs, with each run kept
separate. Selecting a session or school year in the overview does not narrow the
grade downloads. Legacy remains a separate source archive with
its own authenticated participant, run and original-log download routes. Classified
archive records can join the grade/session exports without merging participant
identities. Session-wide downloads never combine similarly
numbered sessions from different grades, whose study dates may differ.

## Export implementation

Full run, participant study-session, grade study-session, participant, current-view selection and grade
downloads use the same disk-backed ZIP implementation. The archive contains original `.log` bytes
(JSON Lines, not renamed `.json`), applicable original run metadata, derived task
questions/answers, and `manifest.json`. A task ZIP includes only its original task
file(s) and selected-task metadata. If that original file is missing, the manifest
reports the gap; the full log is not passed off as an individual task file.
The existing task-ZIP endpoint remains available for compatibility; task pages
now offer original-file downloads instead.

Direct log downloads use authenticated, server-resolved run/source identifiers,
never browser-supplied filesystem paths. They stage and hash-verify the indexed
byte prefix on private temporary disk using the same capture helper as ZIPs.
Later appends are excluded, original bytes (including malformed/partial lines)
are preserved, and a replaced, modified or unreadable file returns a refresh/retry
error rather than sending different contents. Missing task files are shown as
missing; no task-only file is synthesized from the full log.

Folders include study ID, collection, grade, a safe participant component with a hash, stable
study-session ID (or unassigned), and unique run ID. Safe source names map back to
exact original filenames in the manifest. Repeated runs and unusual participant
IDs cannot collide. The manifest identifies the selected scope, source IDs, session
dates, recorded versions, available sessions, settings revision, missing answers and
files, data-quality issues, export time, schema version and per-source SHA-256 hashes.
It also records the requested collection/grade/study-session/participant/run scope
and explicitly confirms that repeated and incomplete runs are included.
It explicitly warns that full and task logs can contain the same events. Credentials,
Flask/browser session storage, index/auth databases, unrelated participants and
nonexistent diagrams are never exported.

Exports refresh the index, then stream its captured source byte prefixes into a private
temporary ZIP on disk, verifying their hashes against the indexed versions. New appends
after each indexed length are excluded. Each source prefix is staged on private temporary
disk and verified before it enters the ZIP; a replaced or modified prefix is omitted
and reported rather than risking a scope mismatch. Partial
last lines are preserved and flagged. Concurrent replacement/truncation/read errors
are reported. This is **not an atomic snapshot across full/task files**, nor a lock
on classroom collection. A file can change while a different file is captured;
manifests report changed sources. Derived metadata comes from the refreshed index.
Use a completed collection for analysis requiring a quiescent snapshot. Temporary
ZIP handles close when the response closes; allow disk space for one archive plus its
largest source file per concurrent download. No full class archive is accumulated in RAM.

## Diagram integration

Diagram generation is not implemented. This release does not generate
research results, accept uploads, or add an unused diagram service. The future
contract is documented in [research_diagram_contract.md](research_diagram_contract.md).

## Verification

Run from the repository root in an environment with Flask, Flask-Cors, Flask-Session,
Flask-WTF, cachelib, requests, pytest and Node installed:

```bash
python -m pytest -q logger/search-app/tests --ignore=logger/search-app/tests/test_back_navigation.py --ignore=logger/search-app/tests/test_bfcache_simulation.py
```

Research tests use temporary synthetic data and stub the search backend when testing
student integration. No real participant files, credentials or external searches
are used or changed. Existing Selenium suites additionally require a running app,
browser driver and a configured test participant.


## Session question contract for progress saving (#6)

The additive configuration keeps `schema_version: 1` and the existing append-only
SQLite settings revisions. Each `sessions` entry may contain:

```json
{
  "id": "grade-4-session-1",
  "grade": "4",
  "number": 1,
  "date": "2026-10-15",
  "name": "Nature",
  "question_set": {
    "theme": "Rivers",
    "approved": true,
    "metadata": {"condition": "shared"},
    "questions": [
      {"id": "river-name", "topic": "River names", "question": "Name a river."},
      {"id": "river-source", "topic": "River sources", "question": "Where does it begin?"},
      {"id": "river-mouth", "topic": "River mouths", "question": "Where does it end?"}
    ]
  },
  "participant_questions": {}
}
```

`participant_questions` maps exact participant ID strings to full question-set
objects of the same shape. Absent exceptions inherit the shared set; an explicit
incomplete exception never inherits it. Question IDs are stable source identities;
`presented_number` and existing positional `topic_id` remain distinct. Optional
set/question `metadata` objects preserve experimental conditions. Loading a legacy
library set preserves its condition columns and source question identity; it never
copies the old participant ID or approves the assignment automatically.

Use `research_dashboard.study_config.assignment_for(settings, uid, session_id)` to
inspect an assignment and its `ready`/`problem` fields. Use
`scheduled_assignment(settings, uid, now=None)` for student eligibility. It returns
only today's approved assignment in Europe/Zurich, including copied `session`,
`question_set`, renderer `topics`, `source`, and `settings_revision`. It reads no
process-local cache: callers obtain the latest `State.settings()` revision per
operation. Settings saves use atomic SQLite revision checks; a stale editor must
reload and retains its draft without overwriting another researcher's save.

The authenticated editor lives at `/dashboard/settings/questions/<session_id>`;
`?participant=<exact ID>` edits an individual exception. Library loading is an
unsaved draft. Signed form drafts preserve selected IDs and metadata across workers.
Use **Save draft** to persist incomplete work, **Save draft and return to session**
to persist and leave the editor, and **Approve questions** when the assignment is
complete. Session settings and the selected session overview show saved question
text, draft/approved status and a link to resume the editor without retyping.
The displayed current setup remains separate from immutable historical run labels.
Loading a library choice displays **Unsaved changes** until explicitly saved.

Individual reuse choices are grouped by normalized topic and question wording,
ignoring case and repeated whitespace. Experimental variants remain separate
complete-set choices. Standalone copying preserves common source metadata; when a
complete set's explicit condition is already selected, an unambiguous matching
source retains that condition. Conflicting source metadata is never chosen arbitrarily.
Only saving creates a settings revision. Approval requires three complete questions;
puzzle media are optional and missing media use the ordinary completion controls.
Student pages receive only their current question, never future session assignments.
Question editor POSTs allow up to 4 MiB for signed metadata drafts; other dashboard
forms retain their 64 KiB limit. Each metadata object remains limited to 32,000
serialized characters and is validated before saving.

New `.run.json` sidecars include `study_session_snapshot`, `question_set_snapshot`,
`assignment_source`, stable per-task `question_id` and `question_metadata`, alongside
the existing `tasks`, `task_order` and log identity. These snapshots are immutable.
#18 also stores this snapshot in `study_attempts` at START. #6 should extend that
record instead of creating a second source of attempt identity; #15's authorized
reset/repeat must reuse the source attempt's original snapshot/order instead of
resolving the latest settings. Durable resume, repeat authorization and completion
gating belong to #6/#15 and are not supplied by this configuration change.

Issue #14 validation: 212 automated tests passed, including settings races, stale
and tampered drafts, library provenance, metadata boundaries, student flow,
historical snapshots and existing logging contracts. The offline checker reported
no warnings on synthetic FULL/per-task logs from complete three-question runs.
The editor and readiness were also checked in a browser using synthetic data.
The two pre-existing Selenium suites were not run; external search was stubbed.
