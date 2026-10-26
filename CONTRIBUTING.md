# Contributing to SOL-logger

This app collects data from children in real classroom sessions, so nothing reaches
the shared branches without automatic checks and a second pair of eyes. This guide
is for everyone who changes the code.

## Branches

| Branch | Purpose | How it changes |
| --- | --- | --- |
| `main` | What runs in classrooms. `scripts/deploy.sh` deploys it. | Only through a release pull request from `matthias-dev`. |
| `matthias-dev` | Shared integration branch for all finished work. | Only through pull requests from feature branches. |
| `<name>/<topic>` | One change, e.g. `samuele/reward-page`, `matthias/export-fix`. | Your own commits. Deleted after merging. |

Push feature branches to this repository (`rotamatth/SOL-logger`), not to a personal
fork: pull requests from forks cannot use the SonarQube Cloud token, so their quality
gate cannot run. Avoid long-lived personal branches; start each change from an
up-to-date `matthias-dev`.

## Everyday workflow

```bash
git switch matthias-dev && git pull
git switch -c samuele/reward-page          # one branch per change
# ...edit, commit...
git push -u origin samuele/reward-page
```

1. Open a **draft** pull request into `matthias-dev` straight away (GitHub's
   "Create draft pull request"). The checks run on every push; read them on the
   pull request's **Checks** tab and in the comments SonarQube Cloud adds.
2. Fill in the checklist of the pull request template, including the
   `logger/docs/CHANGELOG.md` entry.
3. When everything is green, click **Ready for review** and ask the other person
   to review.
4. After the approval, use **Squash and merge** and delete the branch.

Releases: open a pull request from `matthias-dev` into `main`, let the checks run,
get the approval, use **Create a merge commit**, then deploy `main` with
`scripts/deploy.sh`.

## The automatic checks

| Check | What it verifies | When it fails |
| --- | --- | --- |
| `collection` | 500+ server tests (collection, recovery, dashboard, logging), production image build, container restart, backup and restore. | Open the failing test's name in the log; reproduce it locally. |
| `Dashboard browser regressions` | Researcher and student pages in a real Chromium browser. | Usually a changed page, button or text the tests rely on. |
| `Code quality` | Python lint (Ruff, rules in `ruff.toml`), JavaScript syntax, known vulnerabilities in `requirements.lock`, test coverage, and the SonarQube Cloud quality gate. | The step name says which part failed; GitHub marks lint findings on the changed lines. |

The SonarQube Cloud quality gate ("Sonar way") looks at the code changed by the pull
request: no new bugs or vulnerabilities, security hotspots reviewed, at least 80%
test coverage of new Python code, at most 3% duplication. Security hotspots are
reviewed (safe or fixed) on the pull request's SonarQube Cloud page.

## Run the checks locally

From the repository root, in a virtual environment with Python 3.14 (CI) or 3.13:

```bash
python -m pip install -r logger/search-app/requirements-quality.txt
ruff check logger/search-app
pip-audit -r logger/search-app/requirements.lock --no-deps --disable-pip
python -m pytest logger/search-app/tests --ignore-glob='*browser.py' --cov --cov-report=term
```

Browser tests need Playwright's Chromium:

```bash
python -m pip install -r logger/search-app/requirements-browser-test.txt
python -m playwright install --only-shell chromium
SOL_REQUIRE_BROWSER_TESTS=1 python -m pytest logger/search-app/tests/test_*browser.py -q
```

In VS Code, the **SonarQube for IDE** extension shows the same kind of findings while
you type.

Dependencies: change `requirements.lock` deliberately (a pull request of its own),
run the audit and the full suite, and add a changelog entry.

## One-time setup (repository admin)

### 1. SonarQube Cloud (free for public repositories)

1. Sign in at [sonarcloud.io](https://sonarcloud.io) with GitHub. Create an
   organization from the GitHub account `rotamatth` (Free plan) and allow the
   SonarQube Cloud app to access `SOL-logger`.
2. Import `SOL-logger`. If it is not offered (the repository is a fork), create the
   project manually in that organization with the key `rotamatth_SOL-logger`.
3. Choose the analysis method **With GitHub Actions**. This switches Automatic
   Analysis off; the two cannot run together.
4. Copy the token SonarQube Cloud shows. In GitHub: **Settings → Secrets and
   variables → Actions → New repository secret**, name `SONAR_TOKEN`.
5. Check that the organization and project key in `sonar-project.properties`
   (`rotamatth`, `rotamatth_SOL-logger`) match what SonarQube Cloud shows.
6. Push any commit to a pull request. When the `Code quality` check shows the
   SonarQube Cloud step passing, add the repository **variable** (same page,
   **Variables** tab) `SONAR_REQUIRED` = `true`. From then on a missing token
   fails the check instead of skipping the quality gate.

### 2. Branch protection

Apply this to `matthias-dev` and to `main` once pull request #20 is merged into
`matthias-dev` (before that, other branches do not contain the workflow and could
never report the checks).

**Settings → Branches → Add classic branch protection rule**, for each branch:

- Require a pull request before merging; required approvals: **1**; dismiss stale
  pull request approvals when new commits are pushed.
- Require status checks to pass, with branches up to date: `collection`,
  `Dashboard browser regressions`, `Code quality`.
- Require conversation resolution before merging.
- Leave "Do not allow bypassing the above settings" off, so an admin can still act in
  an emergency. Force pushes and branch deletion stay blocked.

The same rule with the GitHub CLI:

```bash
for branch in matthias-dev main; do
gh api -X PUT "repos/rotamatth/SOL-logger/branches/$branch/protection" --input - <<'EOF'
{"required_status_checks": {"strict": true, "checks": [
   {"context": "collection"}, {"context": "Dashboard browser regressions"}, {"context": "Code quality"}]},
 "enforce_admins": false,
 "required_pull_request_reviews": {"required_approving_review_count": 1, "dismiss_stale_reviews": true},
 "required_conversation_resolution": true,
 "restrictions": null, "allow_force_pushes": false, "allow_deletions": false}
EOF
done
```

### 3. Repository settings

- **Settings → General → Pull Requests**: allow squash merging and merge commits;
  enable "Automatically delete head branches".
- **Settings → Code security**: enable Dependabot alerts, so newly published
  vulnerabilities in pinned packages are reported between pull requests.
