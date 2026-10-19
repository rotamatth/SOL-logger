# Production collection and recovery

Issue #18 (`production-hardening`) adds durability to the existing #14 dashboard.
It supports a single server with local persistent storage and multiple Gunicorn
workers. It does not add cross-server coordination. Permanent participant identity
and yearly enrollment are tracked in #19; progress/resume in #6 and live monitoring
in #17 remain separate changes.

## Storage contract

Back up these directories together while collection is stopped:

| Directory under `logger/` | Authoritative contents |
| --- | --- |
| `logs` | Original read-only legacy collection |
| `logs-v2` | Original FULL/per-task logs, immutable `.run.json` snapshots, **hidden `.uploads.sqlite3` receipt journal** |
| `research-state` | `research.sqlite3`: settings revisions, immutable admitted attempts, authentication and research annotations |
| `research-secrets` | Dashboard password hash and private persistent `student-secret` |
| `student-sessions` | Student session files, frozen questions/order, current phase |

`research-state/index.sqlite3` is a disposable reporting cache. A corrupt cache is
quarantined under `index-corrupt-*` and rebuilt on the next reporting request.
Collection does not open this cache at startup. An unavailable cache can make the
dashboard return 503 without preventing student starts/uploads.

Do not delete `.uploads.sqlite3` as if it were a cache. Original log bytes and
upload receipts must remain together. Keep backups private: they contain research
data, session tokens and signing material. Store an additional encrypted copy off
this server using the institution's approved storage. Do not expose data folders
through the web server.

## Admission and upload boundaries

`State.admit_attempt` serializes eligibility, the settings revision and immutable
attempt creation against session removal. A new attempt is not started if this
commit fails; any previously active session is restored. Once admitted, the
snapshot remains in `study_attempts` even if its sidecar cannot be published.
Uploads and dashboard refresh retry pending sidecars. Original files are never
replaced by a conflicting snapshot.

`LogStore.accept` records each upload's exact bytes and destination offsets before
appending. Under a process lock, it recovers unfinished writes, flushes all files,
and only then returns a receipt. The browser persists a stable batch ID and the
exact request before sending; a lost response retries that request. Reusing an ID
with different bytes is rejected. Events queued during an upload remain queued.
A partially written batch is completed at its recorded offsets without duplication.
Unexpected changed/truncated original bytes stop recovery rather than overwrite data.
A busy publisher returns a retryable error instead of holding workers indefinitely.

After a failed answer submission, the retry dialog retains the answer and pending
batch across page reloads. It does not unlock editing an answer whose delivery is
uncertain. A missing logger or invalid acknowledgement cannot advance completion.
Server-side reward events also use stable receipts. Existing event formats and
FULL/per-task filenames are preserved.

Receipts currently retain batch contents indefinitely, so allow extra disk space
in addition to the log files. Retention/compaction needs a separately tested policy.
The index and exports can briefly observe an append before its matching task file
is complete; an upload is acknowledged only after both files are durable.

## First upgrade and deployment

The first upgrade replaces the old shared fallback signing key. Finish all active
classroom runs before installing it: old cookies cannot be made compatible with a
new private key. Subsequent replacements preserve active sessions when the same
key and all five storage directories are mounted. Do not rotate the key during a
study session. Filesystem sessions retain the application's existing expiry policy;
the search-entry route also keeps its existing 60-minute inactivity cutoff. This
is not a permanent progress archive.

On the server, from `logger/`, build and configure private credentials:

```bash
docker compose build search_app
mkdir -p research-secrets
python3 search-app/tools/setup_runtime_secret.py research-secrets/student-secret
docker compose run --rm --no-deps --volume "$PWD/research-secrets:/secrets" search_app python tools/set_research_password.py /secrets/password.hash
```

The secret helper creates a mode-0600 random key once and never replaces it. The
password helper prompts interactively. Production refuses a missing/short student
signing key. `/health/ready` checks research state, dashboard credential availability,
upload recovery, and writable collection/session/state storage; it returns no secrets.
It deliberately does not depend on the reporting cache or external search providers.

Deploy a reviewed, pushed branch with `scripts/deploy.sh <branch>`. The script
builds before stopping collection, retains the previous image, copies old filesystem
sessions on the first volume migration, and creates a verified offline backup.
It waits for readiness. If startup fails, it attempts to restart the previous image
and preserves the backup for operator recovery. It does not restore old data
silently, since that could discard records written during a failed release.
The initial volume migration requires the prior container's `/app/flask_session`
to be readable. Inspect a failure before proceeding; do not discard that directory.

The current deployment intentionally retains the selected HTTP/VPN configuration.
Before collecting real data, the operator must verify VPN/firewall restrictions
on the server. For access outside that private network, configure HTTPS and set
`SESSION_COOKIE_SECURE=1` and `RESEARCH_COOKIE_SECURE=1`. Server network rules and
external search credentials cannot be proven by local tests.

## Verified backup and restoration

Run from `logger/` on the server. Choose a new backup filename each time:

```bash
docker compose stop search_app
python3 search-app/tools/backup_study.py create backups/study-before-release.zip --root .
python3 search-app/tools/backup_study.py verify backups/study-before-release.zip
docker compose up -d --no-build --wait --wait-timeout 120 search_app
```

The helper checks authoritative SQLite integrity, records SHA-256 checksums and
sizes, preserves hidden journal files, and verifies every archived file. It rejects
symlinks and unsafe archive paths. Stop all writers before creating a backup; the
helper cannot detect a separate collector still writing into these directories.

To rehearse restoration, use a new, nonexistent directory:

```bash
python3 search-app/tools/backup_study.py restore backups/study-before-release.zip --root /private/recovery/study-before-release
```

The parent must exist and be private. Restoration refuses an existing destination,
checks all checksums and databases, and leaves the live collection untouched.
Inspect the restored originals and run snapshots before activating recovery.
For actual recovery, stop collection, preserve the current directories separately,
then have the operator replace the five directories with the verified restored set.
Keep the matching image tag/Git revision with the backup record. Start that image,
check readiness, log in, and verify a synthetic attempt before reopening collection.
Never roll the database back while retaining newer upload files or receipt journals.

This release upgrades `research.sqlite3` from unversioned schema 0 to schema 1 in
one transaction, adding `study_attempts` and retaining existing settings/history.
Newer schema versions are refused. A future incompatible migration must provide its
own restore plan; image rollback alone is not enough. Original log formats remain
unchanged. Backups are recovery artifacts, not the dashboard's research export ZIPs.

## Verification and extension points

Install `requirements-test.txt` and run:

```bash
python -m pytest logger/search-app/tests -q --ignore=logger/search-app/tests/test_back_navigation.py --ignore=logger/search-app/tests/test_bfcache_simulation.py
```

Production and tests use the checked-in exact versions in `requirements.lock`.
`requirements.txt` lists direct dependencies; update the lock deliberately, run
`pip check`, the collection suite, and a fresh image build when changing versions.
CI runs the suite, validates Compose, builds the image, then seeds an attempt in
one disposable container and checks its cookie, snapshot and upload receipt in a
replacement container using `tools/check_collection_restart.py`. It also creates a
verified backup, restores it to a new directory, and repeats the check. All invocations
use one disposable volume; the seed refuses an existing study directory. Search is
stubbed and no actual API keys or participant data are used.

Local verification includes concurrent/repeated uploads, partial writes, corrupt
and unavailable reporting indexes, admission/removal races, private key setup,
readiness failure, and verified backup restoration. Browser testing uses synthetic
storage and an injected first-save failure: answer -> retry message -> reload ->
retry -> reward, checking that exactly one answer was recorded. A complete
three-question run and a final-save failure/retry were also checked: each task
recorded one answer and the run recorded one final completion event. The two older
Selenium suites require separate setup and are not part of this automated command.

Extend `study_attempts` for #6's progress state; preserve admitted question IDs,
order, provenance and settings revision. Extend this admission transaction for #19's
permanent registry and session-owned school years, without deriving historical
identity merely from matching numbers. Publish #17's monitoring updates only after
an upload receipt is committed; a live connection must not become the source of
research records. Multiple servers will require a coordinated database and storage
strategy in place of local filesystem locks.

Local checks do not establish production readiness by themselves. Before each
classroom release, rehearse restore and rollback on staging, verify external search,
complete a three-question run on the actual tablet/browser, and inspect its export.
Permanent enrollment protections (#19), durable resume/reset authorization (#6/#15)
and real-time monitoring (#17) are not claimed by this release.
