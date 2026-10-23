# Dashboard foundation and progress-saving handover

This is the source integration guide for Samuele's [progress saving work (#6)](https://github.com/rotamatth/SOL-logger/issues/6).
The foundation covers dashboard configuration (#14), collection hardening (#18),
and permanent identity/yearly enrollment (#19). Durable draft/resume semantics
and researcher-authorized repeats remain #6/#15. Live monitoring remains #17.

For the 20 October 2026 checkpoint, outstanding merge/deployment checks and V2
decisions, read [Merge and V2 readiness](merge_v2_readiness.md) first. This document
defines the extension contract; it does not certify an untested merge or release.

## Branch integration

`longitudinal-participants` is based on local checkpoint `3e85a9e` on
`production-hardening`. That checkpoint includes the earlier dashboard and
collection-hardening work. This is a stacked change, not a standalone patch to
Samuele's older branch. Nothing in this handover publishes or merges branches.

`session-preparation-ux` builds on local `longitudinal-participants` checkpoint
`6934280`. It restores preparation as the dashboard entry point and keeps IDs and
questions within one session context. It adds no schema migration or student-route
contract change. Integrate this complete stack when choosing that UX for the release.

When the foundation is reviewed and shared, merge the complete foundation branch
into `samuele/study-progress` (or its agreed integration base), resolve any conflicts
in `search_app.py`, and run the tests below before adding progress persistence.
Do not copy dashboard files individually: templates, storage migration, collection
admission and deployment configuration belong to the same foundation.

## Code ownership and extension boundaries

| Module under `search-app/research_dashboard/` | Responsibility |
| --- | --- |
| `participants.py` | Permanent identities, annual enrollment, promotion and explicit historical links; no Flask dependencies |
| `state.py` | Authoritative SQLite schema, coherent settings reads, transactional writes, revision checks and admission |
| `study_config.py` | Resolve a participant's exact session questions and readiness, using the session's own year |
| `collection.py` | Freeze admission metadata, commit an attempt and publish its immutable sidecar |
| `log_store.py` | Durable upload receipts, idempotent retries and recoverable publication of original logs |
| `question_versions.py` | Working draft vs approved questions per session and participant (see "Question lifecycle") |
| `index.py`, `exports.py` | Rebuildable read models and provenance-preserving exports; never a source of attempt state |
| `runtime.py` | Persistent signing key and readiness support |

Dashboard web layer (Flask). `__init__.py` only wires these modules; each one
exposes `register_*(dash)` and receives the shared `Dashboard` context
(`dashboard.py`: blueprint, `state`, `index`, `u()`, `page()`, `problem()`, `data()`).

| Module | Responsibility |
| --- | --- |
| `security.py` | Login/logout, research session, CSRF, response headers (CSP), error pages |
| `template_context.py` | Values available in every template (translation, navigation context, question status) |
| `preparation_views.py` | Session preparation (the start page) and the researcher-only student preview |
| `question_views.py` | Question editor: Save draft / Approve / Discard, library reuse |
| `editor_views.py`, `editor_recovery.py` | Private 8-hour recovery of unsaved editor text |
| `enrollment_views.py` | Permanent participants, yearly enrollment, signed review/confirmation |
| `settings_views.py` | School year, session administration, original ID ranges (one handler per action) |
| `history_data.py`, `history_views.py` | Data and history read models; overview, participant, run and log pages; trash |
| `export_views.py` | ZIP downloads |

Add a new dashboard area as its own `*_views.py` module with a `register_*_routes(dash)`
function and call it from `init_dashboard`. Endpoint names stay `research.<function>`.

`search_app.py` composes these boundaries. New progress code should be a separate
module with narrow methods called by student routes. Keep SQL in the persistence
boundary and avoid adding another participant list or a second question resolver.

## Identity contract

An ID is an exact string. `1`, `001`, and `C-001` are different IDs. Never convert
an ID to an integer for storage or matching. Numeric sorting is presentation only.

| Value | Meaning and lifetime |
| --- | --- |
| `participant_id` | Researcher-facing ID, permanent for one child; never recycled |
| `participant_key` | Opaque permanent registry key; stable even while inactive |
| `enrollment_id` | Stable annual enrollment identity, unique per participant/year |
| `school_year` | September 1 through August 31; `2026/2027` includes 2027-08-31 |
| `study_session_at_collection` | Scheduled session ID; currently grade-scoped, monotonically numbered and never reused |
| `technical_session_id` | Current technical run UUID; **not** yet a durable cross-browser progress attempt identity |
| `question_id` | Stable question identity within the immutable admitted question set |
| `presented_number`, `topic_id`, `task_order` | Presentation position and shuffled topic mapping; preserve all three |

The current planning year does not determine eligibility. A session has its own
school year and date. `scheduled_assignment` checks today's date in Europe/Zurich
and enrollment in **that session's year**. Planning next year must not block this
year's scheduled collection. Inactivity blocks new starts; already admitted runs
keep their snapshots. It is not an emergency revocation mechanism.

Initial defaults reserve IDs 1–20 for grade 4 and 21–40 for grade 5. Researchers
must verify this initial roster, explicitly choose the first year, and correct
individual enrollments. Promotion copies active grade 3 → 4 and grade 4 → 5 into
the consecutive year; grade 5 IDs remain reserved without a new enrollment.
Individual exceptions, retention or late enrollment use the register's edit form.
A conflicting target enrollment blocks the entire promotion without partial writes.

Every active ID enrolled in a class/year is available in every session of that
class/year. There is no per-session attendance or participant selection. The
preparation shortcut can add new IDs or enroll known active IDs while retaining
their permanent keys and previous years. A change to an existing enrollment is
shown in the signed review before confirmation.

## Public reads and writes

`state.settings()` returns a coherent SQLite snapshot of settings and the registry:

```python
configuration = state.settings()
configuration['revision']
configuration['participant_registry']['1']  # key, active, created_at
configuration['enrollments']['2026/2027']['1']  # id, grade
configuration['participant_links']  # active, explicitly confirmed legacy links
```

The projection is read-only data. Do not mutate it and expect persistence.
`save_settings(value, expected_revision)` saves only `SETTING_FIELDS`; registry
writes use the dedicated method. Both serialize on `BEGIN IMMEDIATE` and reject
stale revisions with `ValueError('settings_changed')`.

```python
state.change_participants(
    'update', dict(uid='1', year='2026/2027', grade='4', active=True),
    expected_revision=configuration['revision'],
    dry_run=True,  # validate the same transaction and roll it back
)
```

Supported operations are `add`, `enroll`, `update`, `promote`, `link`, and `unlink` (see the
small functions in `participants.py` for arguments). Successful writes increment
the shared revision and append an audit record in the same transaction. Audit
records identify changes and revisions, not individual researchers: access still
uses one shared researcher credential. Do not claim per-user attribution.

The old range editor exists for compatibility during initial setup. Once multiple
years are recorded, it refuses range changes; use the permanent register instead.
Unchanged range templates never overwrite individual enrollment edits.

The bare `/dashboard` entry and login lead to `/dashboard/prepare`. Explicit
reporting links such as `/dashboard?collection=study&grade=4` retain the data view.
Preparation uses `grade`, `year` and `session`; its question/enrollment links carry
`prepare_session` to return to the same context. Enrollment review tokens bind that
session as well as the operation, arguments and settings revision. Other administration
links remain usable independently. Preparation reads only authoritative settings and
readiness, so a reporting-cache failure cannot block session setup.

## Admission contract for #6

The current student route uses this sequence:

```python
configuration = state.settings()
assignment = scheduled_assignment(configuration, user_id)
# None means unavailable; the caller returns the student-facing explanation.
# If present: session, enrollment, question_set, topics, source, settings_revision,
# ready, problem. Each mutable content object is copied.

metadata = record_run(
    log_directory, state, user_id, technical_session_id, log_id, task_order,
    assignment['topics'], settings=configuration,
    study_session=assignment['session'], question_set=assignment['question_set'],
    assignment_source=assignment['source'], admit=True,
)
```

Use `admit=True` for real collection. `State.admit_attempt` rechecks the current
revision, today's session, active enrollment, participant key and annual context
inside the same writer transaction as insertion into `study_attempts`. A race
with a researcher edit fails before an attempt is admitted. Session removal or a
change to a started session's year is rejected inside that transaction boundary.

`record_run` stores grade/year/enrollment and the full question set, original
text, metadata, theme, IDs and task order. Never resolve current settings to resume
an already-started attempt. `state.attempt_metadata(technical_session_id)` returns
the authoritative snapshot. The sidecar is an immutable publication of it; if
publication fails after commit, `publish_pending_runs` can recover it. The route
checks whether a durable attempt exists before deciding whether to restore the
previous browser session and report a start failure.

For #6, add an explicit durable attempt ID and progress tables/methods with a new
versioned migration. Associate multiple technical runs with the same attempt.
Preserve existing technical IDs and log formats. Implement the uniqueness rule
for one active attempt per participant/session in SQL, with transactional
start/resume/submit transitions; the current foundation deliberately does **not**
enforce that unfinished #6 policy. Starting again after a task has been searched
creates another run; a repeated start before that continues the untouched run.

Store first-answer, final-answer and recap drafts separately from submissions;
retain a progress revision for compare-and-swap writes. Retired/submitted attempts
must reject late writes. Recap edits need append-only revisions with before/after
values and authoring-session context. Repeats must preserve the original snapshot
and order and require #15's researcher authorization. None of these should depend
on whether the reporting index is available.

## Question lifecycle: working draft vs approved

Each study session holds two separate versions of its questions. Only the
approved version is ever used for admission.

| Field on the session | Written by | Read by admission |
| --- | --- | --- |
| `question_set` (and `participant_questions[id]`) | **Approve questions** only (`publish_questions`) | yes, if `approved` is true and complete |
| `question_draft` (and `participant_question_drafts[id]`) | **Save draft** (`save_question_draft`) | never |

Rules (implemented in `research_dashboard/question_versions.py`, validated in
`state.validate_settings`):

- Saving a draft never changes or withdraws the approved questions. Children who
  have not started keep receiving the approved version.
- Approving replaces the approved version for **new** starts and removes the draft.
  Already admitted attempts keep their immutable snapshot (`attempt_metadata`);
  never re-resolve current settings to resume one.
- An individual draft does not create an individual assignment: until it is
  approved the child keeps the class questions.
- **Discard working draft** removes only the draft. **Use shared questions** removes
  both the individual approved set and the individual draft.
- Older data may contain an unapproved `question_set` written before this split.
  It is kept as it is, shown as a draft, and never published implicitly.

Researcher form recovery (`editor_recovery.py`, `/dashboard/editor/recovery`) is a
separate, private concern: an 8-hour, per-browser copy of unsaved editor text. It
never touches settings, admission or student progress, and is not a model for
#6 student progress saving.

## Durable acknowledgement and logging

`LogStore.accept(run_id, batch_id, payload, prepare)` writes a durable intent,
publishes exact bytes under a process lock, then records completion and returns
the receipt. Retrying the same batch returns the same receipt, including after a
worker restart or task advancement; conflicting content is rejected. The browser
keeps a failed batch for retry and does not advance before confirmation.

Progress state and the upload journal are currently separate databases. Do not
promise atomic progress + log commits across them. For #6, use a transactional
outbox in the progress database (with stable event/batch IDs) and a retryable
publisher, or deliberately consolidate ownership with a migration. Define what
a successful response guarantees, test lost acknowledgements, and retain the
existing receipt semantics. Completion must not get ahead of durable submitted
answers. Publish #17 monitoring notifications only after durable success.

## History and exports

V2 IDs resolve through the permanent registry. Legacy IDs resolve only through a
researcher-confirmed, date-scoped link; matching numbers alone do not establish
continuity. Active links cannot overlap for one source ID. Revocation preserves
the original link and its audit record. Original source files are never rewritten.

`collection=study` participant views/exports combine a canonical participant's V2
runs and explicitly linked historical runs. Unlinked historical identities retain
a separate namespace. Source-specific `collection=v2` / `legacy` remain available.

Export entries retain original `participant_id`, `collection` and source folders,
and add `study_participant_id`, `participant_key`, `enrollment_id`,
`identity_source`, `identity_link_id`, and `identity_link_revision`. The manifest
also records the settings revision. Recorded grade/year takes precedence over
explicit historical assignments. Missing classification may use a confirmed
annual enrollment for the record's date and resolved identity. It never uses a
child's present grade to relabel an older record. Unconfirmed values remain unknown.

## Migration, recovery and deployment limits

`research.sqlite3` uses schema version 2. Upgrading schema 0/1 creates the permanent
registry, annual enrollments, link history and audit in one transaction. It reserves
IDs from all retained range revisions and durable attempts; removed IDs stay
reserved/inactive. It imports current-year enrollment only when an explicit valid
year exists. Sessions inherit that configured year only if their date fits it;
otherwise their year remains blank until a researcher resolves it. It appends a
settings revision rather than overwriting the old rows. It never guesses legacy
identity links or rewrites existing attempt snapshots.

Back up the stopped deployment before migration. An older image cannot open the
new authoritative schema; rollback requires the matching pre-upgrade backup and
image, not just an image switch. Follow [production readiness](production_readiness.md).
The reporting cache is disposable; the registry, settings, attempts, original
logs, upload journal, signing key and student sessions are authoritative/recovery data.

The supported topology is multiple workers on one server with local persistent
storage. SQLite transactions and filesystem locks are not a multi-server design.
Before multiple servers, move authoritative transactions and file publication to
coordinated shared services. The app currently supports one class per grade,
grades 3–5, and up to 100 monotonically numbered sessions per grade across years.
Add explicit class/school entities or general session IDs through migrations when
needed; do not encode these into permanent child IDs. Add individual researcher
accounts and permissions as a separate change if teachers need different access.

## Verification before merging progress work

From the repository root:

```bash
python -m pip install -r logger/search-app/requirements-test.txt
python -m pytest logger/search-app/tests -q \
  --ignore=logger/search-app/tests/test_back_navigation.py \
  --ignore=logger/search-app/tests/test_bfcache_simulation.py
```

The two legacy Selenium suites need their own browser/server setup. The main suite
covers migration, enrollment concurrency, signed previews, stale writes, identity
links/exports, promotion, immutable admitted runs and upload recovery. CI also
builds the release image and uses `tools/check_collection_restart.py` across fresh
containers and a verified backup/restore. That check compares permanent keys and
annual enrollments as well as snapshots, cookies and upload receipts.

CI separately requires the dashboard Chromium regressions. To run them locally:

```bash
python -m pip install -r logger/search-app/requirements-browser-test.txt
python -m playwright install --only-shell chromium
SOL_REQUIRE_BROWSER_TESTS=1 python -m pytest logger/search-app/tests/test_editor_browser.py -q
```

Required mode fails when the browser dependency or executable is unavailable;
an optional browser-module skip in the ordinary suite is insufficient for a
release baseline.

Add #6 tests for browser/server restart at every phase, lost acknowledgements,
concurrent start/resume, stale autosaves, retired attempts, recap revision history,
repeats and date boundaries. Verify the actual tablet and external search on
staging before classroom release; local tests cannot establish those properties.

### Verification of this foundation (19 October 2026)

- 300 automated tests passed; dependency consistency and diff checks passed.
- The production image built successfully. A synthetic attempt survived replacement
  containers and verified backup/restore with identical participant keys, annual
  enrollments, question snapshot and upload receipt, without duplicate answers.
- The Italian enrollment interface was checked in the browser: promotion review,
  confirmation, retained annual history, and explicit historical-link confirmation.
  The narrow layout was inspected as well. Only disposable synthetic records were used.
- Actual tablets, institutional deployment, external search and the two standalone
  legacy Selenium suites still require their release-environment checks.

### Preparation UX verification (20 October 2026)

- 313 automated tests passed, including draft return/reopen, class/year navigation,
  signed enrollment review, whole-class availability, permanent-key preservation,
  rejected stale/CSRF writes and actual student admission after preparation.
- The Italian browser walkthrough used synthetic data: create a session, add IDs,
  save and reopen a draft, approve questions, and open student entry. No institutional
  collection records were used.
- The final container built successfully; synthetic admission, upload receipts,
  permanent keys and annual enrollments survived replacement and backup/restore.
