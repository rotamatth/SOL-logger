# Dashboard merge checkpoint and V2 follow-up

Updated 20 October 2026. Branch: `session-preparation-ux`. Previous checkpoint:
`ca66c95`. This document accompanies the requested local commit; it is not evidence
that main has been merged, hosted CI has run, or a classroom deployment is ready.

## What this checkpoint contains

- Session preparation, permanent identities, annual enrollment, approved question
  snapshots and durable collection from the stacked foundation branches.
- Student response escaping, same-origin access, safer URL/probe handling and
  provider/log privacy fixes.
- Editor race fixes, version-aware recovery/discard, login preflight, logout
  cleanup and required Chromium regression checks.
- The agreed header: decorative gold search mark at top left; Trash, EN/IT and
  Log out at top right; three centered primary categories on a separate row.
  Pale gold derived from the mark is used for light selections and panels, with
  neutral readable text. Existing status labels retain their semantic colors.

This is a foundation for the next V2 work, not an implementation of durable
student resume, authorized repeats or live monitoring. Researcher editor recovery
does not provide student progress persistence.

## Before merging into main

| Check | Status / action |
| --- | --- |
| Synthetic regression suite, required browser mode | Results recorded under Verification below. The two standalone legacy Selenium suites remain excluded. |
| Production image, replacement and restore checks | Results recorded below; these use disposable synthetic storage. |
| Latest main and branch integration | Refresh remote refs, inspect the full stack and test the actual proposed merge. Local `main` is older than the stored `origin/main`; neither is proof of the current remote head. |
| Hosted CI | Require both **Dashboard browser regressions** and **collection** for the proposed merge. A workflow being present does not configure branch protection or prove a successful hosted run. |
| Presentation acceptance | Review the final pale-gold interface in English and Italian on PC and a real iPad. Earlier browser walkthroughs do not establish acceptance of this final layout. |
| Files in the commit | Source, tests and documentation only. Keep credentials, generated logs, Docker volumes, backups and session databases out of Git. |

Integrate the complete stack: `session-preparation-ux` builds on
`longitudinal-participants` and `production-hardening`. Do not copy only dashboard
templates into main or Samuele's branch. Resolve shared `search_app.py`, admission,
logging and template changes together, then rerun the checks on that merge result.
Create or agree the integration baseline before building further V2 changes on it.

The local review found no newly confirmed merge blocker in the student/backend or
editor changes. The unperformed checks above remain open; this is not a claim of
full browser, production or future-V2 readiness.

## Before collecting classroom data

- Verify the actual participant IDs, annual enrollments, session-owned school
  years/dates and approved questions. Sample rosters and DEMO records are not a
  confirmed classroom configuration.
- On PC and a real iPad, prepare a session with realistic long questions; save a
  draft, leave/reopen, approve, preview, and complete a three-question student run.
  Check its answers, completion state, original logs and export.
- Repeat the editor workflow after idle expiry, on a slow connection and in two
  tabs. Verify the distinction between unsaved recovery, saved draft and approved
  questions in both languages. Changes to that wording need Matthias's review.
- Rehearse stopped-collection backup, restore and matching-image rollback on
  staging. Preserve all five authoritative directories together. SQLite schema 2
  rollback to an older application requires the matching pre-upgrade backup;
  switching the image alone is insufficient.
- Verify real search/autocomplete, provider credentials, server storage permissions,
  readiness, VPN/firewall restrictions and the institutional deployment path.
  Local stubbed tests do not validate external providers or server network access.
- Keep the current shared-password / HTTP-over-VPN deployment decision explicit.
  Named accounts and HTTPS were deferred by Matthias. Exposure outside the private
  network requires HTTPS and secure cookies before real collection.

Follow [production readiness](production_readiness.md) for the storage list,
backup commands, first signing-key upgrade and rollback procedure. Do not rotate
the student signing key during an active classroom run.

## What remains for the next V2 setup

The repository records #6 (progress/resume), #15 (authorized repeats) and #17
(monitoring). [The integration contract](dashboard_integration.md) is the source
of truth for their storage and admission boundaries. The earlier conversations
are not reproduced here as an agreed complete V2 specification. Confirm any
additional experiment phases, recap behavior and division of implementation work
against the agreed V2 plan before implementing those parts.

| Area | Required design / missing implementation |
| --- | --- |
| Durable progress (#6) | Add an explicit durable attempt ID, versioned migration, transactional start/resume/submit transitions and a SQL uniqueness rule for the agreed active-attempt policy. A technical run UUID alone is not cross-browser progress identity. |
| Drafts and submissions | Keep first-answer, final-answer and recap drafts separate from submissions. Use progress revisions to reject stale autosaves and late writes to retired/submitted attempts. Define which acknowledgements make a phase complete. |
| Immutable experiment context | Resume from admitted metadata, not today's mutable configuration. Preserve participant/enrollment keys, session, question IDs/text/metadata, order, presented numbers and provenance. |
| Progress + logging | Progress state and upload receipts are separate databases. Choose a transactional outbox with stable event/batch IDs or a deliberate ownership migration. Do not promise atomic commits across the existing separate stores. |
| Repeats and resets (#15) | Define who authorizes a repeat, the recorded reason and its relationship to the original attempt. Preserve originals and audit the operation; repeated starts currently create separate runs. |
| Recap editing | Define append-only before/after revisions and authoring-session context, including stale-tab conflict behavior. |
| Monitoring (#17) | Publish notifications only after durable success. The live connection and reporting cache must never become authoritative research storage. |
| Enrollment and promotion | Reuse the permanent registry and exact string IDs, including prefixes/padding. Eligibility uses the session's own September–August year. IDs are never recycled; matching legacy numbers do not establish identity. |
| Capacity / topology | Current limits are one class per grade, grades 3–5, 100 monotonically numbered sessions per grade across years, and one server with local storage. Multiple classes/schools or servers need explicit entities, migrations and coordinated storage. |

Before V2 integration, add synthetic tests for every phase across browser/server
restart, lost acknowledgements, simultaneous start/resume, stale writes, retired
attempts, recap revisions, authorized repeats, and Zurich date/year boundaries.
Keep existing upload receipts and log formats compatible; preserve exactly-once
retry behavior even when a response is lost.

## Known follow-ups and technical considerations

- Add a Chromium regression for lost-response reconciliation. Existing tests cover
  conflicts and failed discard, but do not exercise that exact accepted-write /
  lost-response branch.
- The native guarded-form submission path currently ignores submitter
  `formaction` / `formmethod`. Current forms use neither. Extend and test the path
  before adding buttons that rely on those attributes.
- Add dedicated PyTerrier request/failure coverage if maintaining that optional
  backend, and a browser test that a quoted query is logged in full. Current
  escaping tests verify rendered HTML, not the entire event payload in a browser.
- Repair, replace or explicitly retire the two excluded legacy Selenium suites;
  exclusion is a coverage gap, not a passing result.
- Plan replacement of deprecated Flask-Session filesystem/signing interfaces.
  A session-store change needs restart/cookie compatibility checks.
- The upload receipt journal retains batch bytes indefinitely. Compaction and
  retention require a tested policy that preserves recovery and retry semantics.
- The frame probe validates addresses before Requests resolves them; a DNS
  rebinding window remains. It uses HEAD and a streamed GET fallback on HTTP 405.
- The container still runs as root. Historical participant logs already present
  in public Git history require a separate owner decision; do not silently rewrite
  that history as part of this feature.

## Local demo inventory and limits

All examples added in this session are in the isolated `sol-ui` Docker volumes,
served on loopback port 7001. They are not checked into Git and are not deployed
to the institutional collection. Existing local settings and logs were retained.

- `sol-ui-walkthrough-v1`: 10 existing grade-4 IDs across three recorded sessions,
  30 added runs. Session 1 falls in 2025/2026; use **All years** to compare all three.
- `sol-ui-matrix-v1`: 60 clearly prefixed DEMO IDs, 18 added sessions and 180 runs
  across grades 3–5 in 2026/2027 and 2027/2028. Each grade/year has 10 demo IDs,
  three approved sample-question sessions and mixed completion states.
- The matrix uses different synthetic cohorts in the two years. It demonstrates
  year filtering, not progression/promotion of the same child between grades.
- Older local fixtures and roster IDs remain visible outside those scopes. The
  2027/2028 view contains the clean 30-participant matrix cohort across three grades.
- Whole-class enrollment applies to every session. A demo session's shared
  questions are available to every local ID enrolled in that grade/year, including
  retained non-demo IDs; recorded DEMO logs still cover only the demo cohort.
- These fixtures are indexed log/sidecar examples, not attempts admitted through
  the student flow. They do not validate upload receipts, durable resume, monitoring
  or production admission. Those require the synthetic integration tests.
- One-off seeders were executed from `/tmp/sol_seed_walkthrough.py` and
  `/tmp/sol_seed_matrix.py`, with marked manifests in the local log volume. They
  are not a versioned fixture command. Before making this a shared acceptance
  baseline, package and test a reproducible fixture tool; the existing
  `scripts/local-ui.sh demo-logs` still creates the older, smaller example.
- A local pre-matrix SQLite snapshot exists in the local state volume. It is not
  a full collection backup or a replacement for the stopped five-directory backup.

Never export these DEMO volumes into the real collection or use them as evidence
of actual participant results. Do not commit the shared dashboard password.

## Verification of this checkpoint

Verification results are updated before the commit is created. Commands run from
the repository root; all data used by tests and container checks is synthetic.

- **449 passed**, no skips, in 64.72 seconds on Python 3.13.2, including all
  **10 Chromium regressions** with `SOL_REQUIRE_BROWSER_TESTS=1` and the pinned
  Playwright 1.64.0 / matching headless Chromium. The two standalone Selenium files
  were explicitly excluded. There were 156 existing Flask-Session deprecation warnings.
- The suite ran in the prepared test environment with the command below. See the
  integration guide for installing the pinned dependencies.

  ```bash
  SOL_REQUIRE_BROWSER_TESTS=1 python -m pytest logger/search-app/tests -q \
    --ignore=logger/search-app/tests/test_back_navigation.py \
    --ignore=logger/search-app/tests/test_bfcache_simulation.py
  ```

- `pip check`, `node --check` for dashboard `editor.js` and student `logger.js`,
  and `git diff --check` passed.
- Production Compose configuration validated. A separate verification image built
  successfully from this source using Python **3.14.4** and the pinned runtime lock;
  its `pip check` passed. The full pytest suite was run on the host Python 3.13.2,
  not rerun inside that runtime image; the Python 3.14 CI run remains required.
- Fresh containers passed synthetic seed and replacement verification, backup
  creation and verification, restore into a new directory, and restored-run
  verification. No live collection or preview volumes were mounted into these checks.
- The final header was inspected in Safari during the UI iterations; the final
  pale-gold stylesheet and three-category grouping were checked in the running
  local preview. Complete final-layout PC/iPad acceptance remains open.

The required desktop Chromium suite does not replace iPad/Safari acceptance.
Hosted CI, the current remote merge result and the institutional deployment are
not established by these local checks.

## Supporting documents

- [Technical handoff and earlier rounds](codex_handoff.md)
- [V2 integration and storage/admission contract](dashboard_integration.md)
- [Dashboard operation and interpretation](research_dashboard.md)
- [Deployment, backups and recovery](production_readiness.md)
- [Change log](CHANGELOG.md)
