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
- [ ] **Dashboard v2 with a real class.** The live view was tested with one synthetic child at a
  time on a laptop. In the first real lesson: open it on the researcher's own device, check that
  finished questions appear within seconds with a full class, and watch server load (8 request
  slots are shared with the children). Also repeat on an iPad: the session list, the checkboxes
  under Participants, the ID menus (**Cerca un ID**, **Vai all'ID partecipante**), opening a child in
  the live view, and the guide. Done when these hold.
- [ ] **First V2 deploy rollback path.** If `scripts/deploy.sh` rolls back on the first
  V2 deployment, the old image starts with `logs-v2` mounted at `/app/logs` and would
  write old-format logs there. Watch the first deploy; if a rollback happens, stop and
  check where new logs go before collecting. _2026-11-06: rehearsed on real Linux. After a failed first deploy the old
  app answers, `/dashboard` is 404 and `logs-v2` is its log folder; deploying again from there succeeded. Do not let
  children use the old app in that state. After any failed release the checkout stays on the failed branch until a
  good one is deployed._

- [x] **Same ID on two tablets.** In the question flow of PR #23, a second tablet choosing an ID already in use joins
  the same run, its searches mix in one log, and its differing answers are refused. _2026-11-06, Matthias: this cannot
  happen, because children receive the iPad after their number is set for them. No guard is needed. Revisit if children
  ever choose their own number._
- [ ] **Read-only check of the real server, before Monday's deploy.** The rehearsal assumed a non-root operator and
  rootful Docker: `id`, `docker info --format '{{.SecurityOptions}}'`, `git log -1 --oneline`, `ls -ln logger/logs | head -3`,
  `df -h .`, `python3 --version`, `docker compose version`. Done when these match, or the differences are understood.
- [ ] **Repeat the rehearsal on the code actually released.** #28 combines #22 (with #23), #26, #27 and dashboard v2; #21 is
  not in it. The class, crash, fault and deploy rehearsals covered earlier heads. Done when they pass on the final merge.
- [ ] **Real search on both engines, on the server.** _2026-11-06: with the Discovery Engine Viewer role, a real query from a Mac
  returned results from each engine on its own topic. Vertex gave no suggestions for either, so autocomplete relies on the
  SerpAPI fallback._ Set the variables in `production_readiness.md` on the server and run `tools/check_search_engines.py`, then type
  in the search box. Done when each theme returns its own results and suggestions appear.
- [ ] **Orecchio questions.** Diletta enters them in the dashboard after the deploy, in animation order: slot 1 plays
  `Orecchio_01`. Keep the theme `orecchio`, which the setup pre-fills. Done when `5a orecchio` shows Published.
- [ ] **Fake May logs on the server.** `UserTestLog*` and `Utente*` are to be removed from `logs/`; a plain delete was refused,
  because the container owns the files. Done when their count is 0, with the class runs of 19 May still there.
- [ ] **Permanent test IDs on the server, Tuesday morning.** Run `TEST-spazio` and `TEST-orecchio` on an iPad with Brave before
  the class, then check the logs reached `logs-v2/test-runs` and nothing changed in Data and history. Done when both hold.

## Setup that needs Matthias

- [x] **SonarQube Cloud** (`CONTRIBUTING.md` → One-time setup → 1): account and import
  (the repository is a fork; create the project manually if it is not listed), secret
  `SONAR_TOKEN`, keys match `sonar-project.properties`, first analysis visible on a
  pull request, then variable `SONAR_REQUIRED=true`. Review the first quality gate and
  any security hotspots. _Done 2026-11-02: gate passes on PR #20 (commit `e080010`),
  hotspots 100% reviewed; S8706 and six S8707 marked false positive, S6845 to accept._
- [x] **Branch protection right after PR #20 is merged** into `matthias-dev`: protect
  `matthias-dev` and `main` (checks `collection`, `Dashboard browser regressions`,
  `Code quality`; 1 approval; admins may bypass). Command in `CONTRIBUTING.md` →
  One-time setup → 2. Not earlier: branches without the workflow could never pass.
  _Done 2026-11-03 on both branches, right after PR #20 was merged (merge commit
  `68ec75c`), and read back from GitHub._
- [x] **Repository settings:** automatically delete head branches; Dependabot alerts on.
  _Checked 2026-11-03: both on._
- [ ] **Samuele onboarding** after PR #20 is merged: bring his branches up to date with
  `matthias-dev` (otherwise his pull requests get no checks), push branches to
  `rotamatth/SOL-logger` rather than a fork, read `CONTRIBUTING.md`.
  _2026-11-03: PRs #21–#23 now target `matthias-dev`; their branches are already in
  `rotamatth/SOL-logger`. Each PR has a comment with the update steps (#22 with its two
  template conflicts, #23 with the one test to adjust). Open until the three branches
  are updated; `samuele-dev` is no longer used and can then be deleted._

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
  _2026-11-03: `.github/dependabot.yml` will propose these as a weekly grouped pull
  request into `matthias-dev` once the file reaches `main` (GitHub reads it only from
  the default branch)._
- [ ] **Dependabot secret:** add `SONAR_TOKEN` under Settings → Secrets and variables →
  **Dependabot** (same value as the Actions secret). Dependabot pull requests get no
  Actions secrets, so with `SONAR_REQUIRED=true` their `Code quality` check fails
  without it. Needed before the first release brings `dependabot.yml` to `main`.
