# Handoff for Codex — dashboard status, to-dos and known risks

_Last updated: 2026-10-20 · branch `session-preparation-ux` · previous checkpoint `ca66c95`_

**Open checks first:** [follow_up_checks.md](follow_up_checks.md) (added 2026-10-26,
review by 2026-11-09) lists what still has to be verified on real devices, the server
and in repository settings. Work through it before anything else and tick what you check.

Read this before changing the research dashboard or the student app. It covers what
was done since your assessment, what is still open, and the risks to keep in mind.
`docs/CHANGELOG.md` has the per-change detail (search it by **Area** tag).

The subsequent [22 October dashboard review](dashboard_review_2026-10-22.md)
records additional bug fixes, UI improvements, verification and the prioritized
follow-up plan, now implemented in the 23 October follow-up except physical-device
acceptance. The changes and their new source/test dependencies are included in the
23 October follow-up. The report records replacement of the retired Selenium
suites, lost-response coverage and final verification. The subsequent
[merge review and correction](merge_review_2026-10-23.md) records the session
concurrency fix and the requirement to check CI on the exact candidate.

For the current merge checklist, deployment gates, local demo inventory and V2
follow-up decisions, start with [Merge and V2 readiness](merge_v2_readiness.md).
That checklist supersedes older verification totals and release-status wording below.

## Working rules (from Matthias)

- **Do not commit unless Matthias asks.** Commits are made under his own name, with no AI
  co-author or signature lines.
- **Change only what the task needs.** Refactors must leave behaviour identical; prove it
  with tests, and with a page/flow comparison for anything that touches templates.
- **Devices:** the V2 experiment runs on **PC**, but everything must still work on **iPad**.
  Touch sizing lives under `@media (pointer: coarse)`, so mouse layouts stay unchanged.
- **Strict CSP:** `script-src 'self'`, no inline scripts or styles. New behaviour goes in
  `research_dashboard/static/editor.js` (dashboard) or the existing static files.
- **Tests use synthetic data only.** Never read or modify the real collection, logs or secrets.
- **Ask Matthias when in doubt**, especially about researcher-facing wording.

## Scope of the review checkpoint

`ca66c95` holds the dashboard workflow and module split (rounds 1–2). This review
checkpoint includes rounds 3–5 below, the two-row header and the final pale-gold
presentation. Matthias explicitly requested the commit on 20 October 2026.
Committing this checkpoint does not merge, publish or deploy the branch.

| Round | Topic | Files |
|---|---|---|
| 3 | Student app security review | `search_app.py`, `search_backend.py`, `templates/search.html`, `templates/layout.html`, `static/main.css`, `requirements.txt`, `requirements.lock`, three test files, docs |
| 4 | Fixes for your assessment (P1/P2 + adjacent issues) | `research_dashboard/{dashboard,security,editor_views,editor_i18n}.py`, `static/editor.{js,css}`, `templates/research/base.html`, `search_app.py`, `search_backend.py`, three test files (one new), docs |
| 5 | Remaining discard, error privacy, redirect and required-browser checks | `research_dashboard/static/editor.js`, `search_app.py`, `search_backend.py`, browser/security tests, new `test_backend_privacy.py`, `requirements-browser-test.txt`, collection workflow, docs |

### Round 3 — student app
- **Escaping:** search results and queries are escaped. The new `rich_text` filter keeps only
  `<b> <strong> <i> <em> <br>` from the engine.
- **Viewer and probe:** `/webpage` accepts only http(s) URLs. `/iframe_check` needs an active
  search and re-validates every redirect hop (at most 5).
- **Autocomplete:** `/autocomplete` needs a participant session.
- **Responses:** CORS removed, 16 MiB upload limit, `nosniff` / `SAMEORIGIN` /
  `same-origin` referrer headers.
- **Logs:** logging-contract warnings no longer include event contents.
- **Logging side effect:** queries containing `"` are now logged in full. Before, they were
  cut off at the first quote; none of the May data was affected.

### Round 4 — your findings, all fixed with regression tests
1. **Autosave vs. navigation:** `Recovery.flush()` now loops until the *current* form snapshot
   is acknowledged, up to 4 attempts. It no longer resolves `true` when a save of older text
   finishes.
2. **Recovery initialisation:**
   - `start()` treats only the server-rendered snapshot as safe.
   - Text typed while the GET is pending gets saved.
   - A recovered copy never overwrites it; instead the banner offers the earlier text
     (`editor_recovered_choice`).
3. **Stale tabs:**
   - Token refresh (`authCheck()` → `GET /dashboard/session`) is now separate from loading the
     recovery version. The sequence is adopted only on page load.
   - On 409, `reconcile()` adopts the server sequence only if the server copy equals what
     this tab sent (a lost response); otherwise the tab enters the conflict state.
   - A stale tab's explicit save can no longer clear the other tab's newer copy.
4. **Logout:** the session is revoked first; recovery cleanup is best-effort and logged.
5. **Guarded forms (IDs, session details, enrollment, links, promotion):**
   - Each form runs a login preflight before submitting.
   - On 401 nothing is sent, the values stay, and a notice offers sign-in in a new tab.
   - The form is then submitted natively, with the clicked button's value kept in a hidden
     input.
6. **Adjacent issues:**
   - Malformed result URLs redirect to the results instead of returning a 500.
   - The search backend uses a module logger and never logs corrected queries or suggestions.
   - Vertex failures raise explicitly; the same error page is shown.

### Round 5 — remaining assessment findings
- **Discard recovery:** pauses new autosaves, waits for a pending save (including its
  version reconciliation), then clears the acknowledged version. Only HTTP 200
  permits reload; conflict, expired login, storage and network failures keep the
  page and show the existing feedback. Another tab's newer copy is preserved.
- **Provider error privacy:** search/autocomplete backend logs and the autocomplete
  route log only the exception type, never raw provider messages, URLs, queries,
  credentials or tracebacks. Empty autocomplete fallback behavior is preserved.
- **Malformed redirects:** invalid `Location` parsing and plain `ValueError` from
  Requests' redirect preparation return structured unavailable results.
- **Required browser CI:** a separate job installs pinned Playwright and matching
  Chromium. `SOL_REQUIRE_BROWSER_TESTS=1` fails when the dependency or browser
  cannot run; optional local skips remain available.

### Earlier verification (before the final presentation changes)
- `python -m pytest -q logger/search-app/tests --ignore=logger/search-app/tests/test_back_navigation.py --ignore=logger/search-app/tests/test_bfcache_simulation.py`
  → **449 passed after round 5**, with pinned browser dependencies installed and
  `SOL_REQUIRE_BROWSER_TESTS=1`. All 10 Chromium cases ran; 156 existing
  Flask-Session deprecation warnings remain. See `docs/research_dashboard.md` for
  installation and the required browser command.
- Required mode without Playwright fails collection; without Chromium it fails
  setup. Workflow YAML, JavaScript syntax, dependency and diff checks passed.
- Production verification image built successfully from the current working tree
  using Python 3.14.4. Nothing was deployed, committed or tagged.
- `tests/test_editor_browser.py`:
  - Covers 10 real-Chromium cases: the original 5 (autosave + leave, typing during
    load, recovered copy vs. typing, stale tab, expired login on the ID form), plus
    discard during a delayed save and rejected/failed clear requests.
  - The original 5 fail on the pre-round-4 `editor.js`; discard regressions fail on
    the pre-round-5 implementation.
  - CI requires execution. Local runs may skip without Playwright/Chromium unless
    `SOL_REQUIRE_BROWSER_TESTS=1`; see `docs/research_dashboard.md` → Verification.
- **Page/flow comparison:** a crawl of 4,000 dashboard pages and 56 write flows showed changes
  only in the new `data-editor-session-url` attribute, three messages and `editor.js`.
  That comparison tool is not in the repo.

## Next work

Use [Merge and V2 readiness](merge_v2_readiness.md) as the actionable checklist.
The existing [integration guide](dashboard_integration.md) already supplies the
extension contract for Samuele; extend it when an agreed V2 design changes that
contract rather than creating a second participant or question resolver.

Before merging, run required CI on the actual proposed merge with refreshed main.
Before classroom release, complete PC/iPad acceptance, external-search checks and
staging restore/rollback. Durable student resume, authorized repeats and monitoring
remain separate V2 work. Wording changes about recovery/draft/approval still need
Matthias's review. Named accounts and HTTPS remain explicitly deferred decisions.

## Potential issues and design trade-offs to keep in mind

- **Earlier recovered text kept only on screen.** If a researcher types while a recovered copy
  is loading, the new text is autosaved over the server copy. The earlier text survives only
  in the on-page banner (with "copy" and "use this text"). This is deliberate: the window is
  sub-second, and the newest typing wins.
- **Lost-response reconciliation** (`Recovery.reconcile`) is not covered by a browser test.
  It compares fields by key and value and adopts the server sequence only on an exact match.
- **Flush limit.** `flush()` gives up after 4 save rounds if the text keeps changing, then
  shows the leave confirmation. Keep that in mind if autosave timing changes.
- **Native submit ignores `formaction`/`formmethod`.** Guarded forms are submitted with
  `HTMLFormElement.prototype.submit`, which ignores those attributes on the clicked button.
  None use them today; if you add one, extend `submitNatively()`.
- **Idle logout after 30 minutes.** Only the question editor has an autosaved recovery copy.
  Other guarded forms rely on the login preflight, so their values stay on the page but are
  not stored anywhere.
- **Recovery store limits:** 8 h TTL, 32 snapshots, 512 KiB per payload, scoped to the
  edit-cookie owner and the password fingerprint. A password change hides older copies by
  design.
- **The iframe probe** checks the address and then fetches it, which leaves a small DNS
  rebinding window. It sends HEAD requests and falls back to streamed GET on HTTP 405.
  Redirect validation does not pin the resolved address used by Requests. Keep this
  limitation explicit if extending the probe.
- **Browser checks must run.** The dedicated CI job requires Playwright/Chromium;
  do not remove `SOL_REQUIRE_BROWSER_TESTS=1` or count optional local skips as
  successful release verification.
- **Repository hygiene:** some older participant log files remain in the git history of the
  public repository. Removing them needs a history rewrite. **Matthias decides this — do not
  rewrite history.**
- **Container runs as root** (deployment). Low priority while it runs inside the VPN; revisit
  together with HTTPS.

## Where things live

| Area | Files |
|---|---|
| Dashboard wiring | `research_dashboard/__init__.py`, `dashboard.py` (shared context, JSON endpoints) |
| Auth, CSRF, headers, login preflight, logout | `research_dashboard/security.py` |
| Question drafts vs. approved | `question_versions.py`, `question_views.py` |
| Private editor recovery | `editor_recovery.py` (store), `editor_views.py` (routes), `static/editor.js` (client) |
| Settings / enrollment / preparation | `settings_views.py`, `enrollment_views.py`, `preparation_views.py`, `state.py` |
| History and exports | `history_data.py`, `history_views.py`, `export_views.py` |
| Student app | `search_app.py`, `search_backend.py`, `templates/search.html`, `static/logger.js` |
| Change history | `docs/CHANGELOG.md` (one entry per commit, with Area tags) |
