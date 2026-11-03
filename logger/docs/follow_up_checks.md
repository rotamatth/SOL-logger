# Follow-up checks (open)

_Added 2026-10-26 · review by **2026-11-09** or before the next classroom session,
whichever comes first · branch `session-preparation-ux` (PR #20)._

For Codex, Claude and Matthias. Each item says what to verify and when it counts as
done. Tick it here (and in the same commit as any fix) instead of deleting it, so the
history of what was checked stays visible.

## Before the next classroom session

- [ ] **Real search after the dependency update.** The commit "Add code quality
  checks, patch vulnerable dependencies…" moved cryptography 48→50, urllib3 2.7→2.8,
  certifi, Werkzeug 3.1.9 and pyasn1 0.6.4 (and removed unused Pillow). Tests stub the search provider; only a synthetic
  Google service-account signature was checked. After deploying: one real Vertex
  search and one autocomplete on the server. Done when both return results.
- [ ] **Uploads during tasks, on real devices.** `static/logger.js` now uploads on page
  load, every minute and when the page is hidden. On an iPad (Safari): start a run,
  search, lock the screen, then check the run's `_FULL.log` grew before the task
  ended; finish a task and check `TaskEnded` appears once. Watch `/log_session`
  frequency in the server log during the first real lesson.
- [ ] **iPad/Safari acceptance** still outstanding from the 23 October review: start
  button double tap, multi-line questions on the task page, editor sticky action bar
  with the on-screen keyboard, dashboard tap targets. Since 3 November also: the two
  participant-ID pop-ups (open, tick, Annulla, review), the "Sei sicuro di voler
  uscire?" Sì/No pop-up (No, Sì, and the keyboard's Esc if one is attached), and
  ticking runs to download on a participant page.
- [ ] **Colleague re-test of the dashboard feedback (3 November).** Ask the researcher
  who recorded the feedback to repeat her walkthrough: new session from name and date,
  importing an ID from another class, the warning colour, Cestino on Dati e storico.
  Done when she confirms or files new points.
- [ ] **First V2 deploy rollback path.** If `scripts/deploy.sh` rolls back on the first
  V2 deployment, the old image starts with `logs-v2` mounted at `/app/logs` and would
  write old-format logs there. Watch the first deploy; if a rollback happens, stop and
  check where new logs go before collecting.

## Setup that needs Matthias

- [x] **SonarQube Cloud** (`CONTRIBUTING.md` → One-time setup → 1): account and import
  (the repository is a fork; create the project manually if it is not listed), secret
  `SONAR_TOKEN`, keys match `sonar-project.properties`, first analysis visible on a
  pull request, then variable `SONAR_REQUIRED=true`. Review the first quality gate and
  any security hotspots. _Done 2026-11-02: gate passes on PR #20 (commit `e080010`),
  hotspots 100% reviewed; S8706 and six S8707 marked false positive, S6845 to accept._
- [ ] **Branch protection right after PR #20 is merged** into `matthias-dev`: protect
  `matthias-dev` and `main` (checks `collection`, `Dashboard browser regressions`,
  `Code quality`; 1 approval; admins may bypass). Command in `CONTRIBUTING.md` →
  One-time setup → 2. Not earlier: branches without the workflow could never pass.
- [ ] **Repository settings:** automatically delete head branches; Dependabot alerts on.
- [ ] **Samuele onboarding** after PR #20 is merged: bring his branches up to date with
  `matthias-dev` (otherwise his pull requests get no checks), push branches to
  `rotamatth/SOL-logger` rather than a fork, read `CONTRIBUTING.md`.

## Decisions to revisit

- [ ] **No puzzle reward in V2 sessions.** Reused legacy sets carry no GIF metadata and
  the editor has no field for it, so children see "Avete completato la domanda" instead
  of puzzle pieces. Confirm with the research team whether this is intended.
- [ ] **Declined for now (2026-10-26):** Italian text for the search-provider error page
  children see (`templates/error.html` is English), listing only IDs that can start
  today on the start page, protecting against iPad swaps mid-run.
- [ ] **Researcher login (decided 2026-11-02):** keep one shared, non-expiring password,
  changed or reset only with `tools/set_research_password.py` (command in
  `research_dashboard.md`). Later options: SWITCH edu-ID single sign-on, or password
  recovery. Revisit when more researchers need their own accounts.
- [x] **SonarQube Cloud flag:** once the `Code quality` check shows the SonarQube step
  passing on a pull request, set the repository variable `SONAR_REQUIRED=true`.
  _Set 2026-11-02._
- [ ] **Not yet linted or analysed:** `logger/search-engine` (12 Ruff findings); add it
  to `ruff.toml` and `sonar-project.properties` if the PyTerrier service is used again.
- [ ] **GitHub Actions versions:** the workflow pins `actions/checkout@v4`,
  `setup-python@v5`, `setup-node@v4`; newer majors exist (checkout v7, setup-python v7).
  Update in a pull request of its own when runner deprecation warnings appear.
