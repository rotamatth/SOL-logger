# Dashboard merge review — 23 October 2026

**Follow-up: the concurrency finding is corrected.** The complete dashboard
implementation and its required new files are included in this change. Merge
approval still requires green hosted CI for the exact committed candidate against
`matthias-dev`; consult PR #20 for its current run status. This is a
development-branch review, not approval to deploy or collect classroom data.

The original review withheld approval because of the reproducible input-loss bug,
uncommitted implementation and missing CI evidence for that working tree. The
sections below distinguish that review evidence from the subsequent correction.

## Candidate and target

- Working branch: `session-preparation-ux`. The original review covered committed
  head `5deb6b063ecb6a3ec48a27a6cba9ce06a1b378c5` plus tracked changes and new
  source/test files. The follow-up adds the concurrency correction described below.
- The user confirmed `matthias-dev` as the merge target on 23 October 2026.
  Its remote head was rechecked through GitHub after that confirmation:
  `16597caeee9668786e888b9d40f8905e0bd7da5f`. It matches the local remote-tracking
  ref and is an ancestor of the feature head. Integration would therefore be a
  fast-forward at these SHAs; no target-only commits need conflict resolution.
- Original review source snapshot SHA-256 (before the concurrency correction):
  `74d164dc6d71ea71de48ba9bdfa5c63d9e13693b622347e06fd5fdc18a4df15c`.
  It includes the relevant app, scripts, workflow and documentation, including
  untracked dependencies, and excludes `dist/`, credentials and study storage.
  Source files were checked against the snapshot after testing.

## Corrected finding

**P2 — A concurrent session removal turns a rejected save into HTTP 404 and loses
entered session details.**

Location: `search-app/research_dashboard/settings_views.py:374–419`, specifically
`session_history()` rejecting an out-of-range page at lines 379–381 while the POST
error page is being rendered.

Reproduction using isolated synthetic settings:

1. Configure 11 active grade-4 sessions in `2026/2027` and open session settings
   on `page=2`.
2. Keep that form's CSRF token/revision and edit a session name.
3. In another tab/transaction, remove one session, leaving only 10 active sessions.
4. Submit the first tab's original revision and edited name to its page-2 URL.

**Observed:** initial GET 200; rejected POST 404; entered name absent from the
response. The intended `settings_changed` conflict response never reaches the
researcher. The database revision check correctly prevents overwriting saved
settings, but the page renderer then discards the rejected form.

**Implemented correction:** failed POST re-renders clamp the history page to the
remaining page count. If the edited session is outside the resulting page/year or
has been removed, its submitted fields remain in a separate open editor. The
original submitted revision is retained, so clicking Save again cannot overwrite
another tab's changes. Invalid GET page numbers still return 404.

The conflict links to the saved session in a new tab at its current year/page, or
to its removal/restore controls. Researchers can review that state and explicitly
copy their intended changes without losing the original form. The shared form
partial is used by both normal history rows and the retained editor.

Four new server regressions failed with 404 before the correction and pass after
it. They cover another session's removal, the edited session's year change, the
edited session's removal, and a stale new-session submission. The edit cases also
verify repeated stale rejection, safe review, explicit restoration when required,
and successful saving after review. Three browser cases exercise EN/IT touch
layouts and JavaScript-disabled operation while opening saved state in a new tab.

## Source-control and CI gates

The original working tree contained four untracked dashboard dependencies. All
four are included in this change:

- `research_dashboard/year_controls.py`
- `research_dashboard/templates/research/year_input.html`
- `research_dashboard/static/question-library.js`
- `research_dashboard/static/question-library.css`

The new `templates/research/settings_session_form.html`, regression modules and
review documentation are included too. The generated
`dist/SOL-dashboard-demo-v2.zip` stays outside the source change.
No tracked credential/database paths were found by the focused filename check;
that check is not a scan of historical Git objects.

Before approval, require **Dashboard browser regressions** and **collection** on
the exact committed candidate/PR against the confirmed target. A green run on the
previous feature head does not verify the new correction or newly included files.

## Original review checks (before correction)

- Fresh full host run: **559 passed, no skips**, 156 existing Flask-Session
  deprecation warnings, **150.91 seconds**, with required Chromium mode.
- Production and local-preview Compose configurations validated.
- Syntax checks passed for dashboard/editor/library JavaScript, student logger,
  deployment/local-preview shell scripts; `git diff --check` and host `pip check`
  passed.
- A clean production Dockerfile build with `--pull` was attempted but the Docker
  registry request for `python:3.14.4-slim` failed with an EOF connection error.
  This was an infrastructure failure before application build steps ran.
- Fallback verification image built successfully from a cached Python **3.14.4**
  production runtime plus the exact source snapshot. Every installed production
  package matched the current lock file; `pip check` passed. This does not replace
  a fresh production Dockerfile build in CI.
- Isolated containers passed attempt/session persistence across replacement,
  idempotent upload retry, backup creation, archive verification, restore into a
  new directory and restored-attempt verification. Networking was disabled; a
  new disposable Docker volume was removed afterward. No preview or live study
  volume was mounted.
- Python 3.14 server-only run: **477 passed**, 12 browser modules skipped
  because the production image has no Playwright, and five Node-backed tests
  deselected because it has no Node binary. Those browser/Node checks passed in
  the full host run. An initial unrestricted container run failed to start those
  five Node checks; this was a test-tooling limitation, not an application failure.

## Merge checklist

Follow-up full host run after the correction: **566 passed, no skips**, with
required Chromium mode, 156 existing Flask-Session deprecation warnings, in
**154.92 seconds**. JavaScript syntax and staged diff checks also passed.

1. Correction and failure-before/pass-after synthetic regressions are included.
2. Include all required new files in the candidate commit; exclude generated data.
3. Recheck `matthias-dev` immediately before merging. If it moves from the reviewed
   SHA, retest the actual integration result.
4. Obtain green required CI, including the fresh image and replacement/restore jobs.

Physical iPad/Safari acceptance, real search-provider checks, institution-specific
network configuration and staging operational rollback remain release gates.
They should not be represented as completed by the local tests. Existing design
limits—one server/local storage, shared researcher login, and deferred durable
student resume/repeats/live monitoring—remain as documented and are not newly
introduced merge findings.
