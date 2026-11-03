#!/usr/bin/env bash
set -euo pipefail

# Manual Git-based deploy of SOL-logger to solar.usilu.net.
#
# Prerequisites:
#   - You are connected to USI VPN or on the USI network.
#   - The server has the repo cloned at ~/SOL-logger.
#   - The server has Docker + Docker Compose installed.
#   - The server has these gitignored files:
#       ~/SOL-logger/logger/search-app/API_keys.json
#       ~/SOL-logger/logger/search-app/service_account.json
#
# Usage:
#   scripts/deploy.sh                 # deploy main
#   scripts/deploy.sh deployment-test # temporary branch deploy

SERVER_USER="${SERVER_USER:-rotam}"
SERVER_HOST="${SERVER_HOST:-solar.usilu.net}"
SERVER_REPO="${SERVER_REPO:-SOL-logger}"
DEPLOY_BRANCH="${1:-${DEPLOY_BRANCH:-main}}"
git check-ref-format --branch "$DEPLOY_BRANCH" >/dev/null
[[ "$DEPLOY_BRANCH" =~ ^[A-Za-z0-9_./-]+$ ]] || exit 2
[[ "$SERVER_REPO" =~ ^[A-Za-z0-9_./-]+$ ]] || exit 2

echo "==> Pre-flight checks"

if ! nc -z -G 3 "$SERVER_HOST" 22 >/dev/null 2>&1; then
    echo "    ERROR: $SERVER_HOST:22 is not reachable from here." >&2
    echo "    Are you connected to USI VPN or on the USI network?" >&2
    exit 1
fi
echo "    $SERVER_HOST:22 reachable"

echo ""
echo "==> Deploying origin/$DEPLOY_BRANCH on $SERVER_USER@$SERVER_HOST:~/$SERVER_REPO"

ssh "$SERVER_USER@$SERVER_HOST" "DEPLOY_BRANCH='$DEPLOY_BRANCH' SERVER_REPO='$SERVER_REPO' bash -s" <<'REMOTE'
set -euo pipefail

cd "$HOME/$SERVER_REPO"

echo "==> Updating git checkout"
git diff --quiet && git diff --cached --quiet || { echo "Commit or save server changes before deployment." >&2; exit 1; }
git fetch origin
git checkout "$DEPLOY_BRANCH"
git pull --ff-only origin "$DEPLOY_BRANCH"

echo "==> Checking server-side secrets"
for f in logger/search-app/API_keys.json logger/search-app/service_account.json; do
    if [ ! -s "$f" ]; then
        echo "ERROR: missing or empty file on server: $HOME/$SERVER_REPO/$f" >&2
        exit 1
    fi
done

chmod 600 logger/search-app/API_keys.json logger/search-app/service_account.json
mkdir -p logger/logs logger/logs-v2 logger/research-state logger/research-secrets logger/student-sessions logger/backups
if [ ! -s logger/research-secrets/password.hash ]; then
    echo "Set the private dashboard password before deployment; see logger/docs/research_dashboard.md." >&2
    exit 1
fi
python3 logger/search-app/tools/setup_runtime_secret.py logger/research-secrets/student-secret
export SOL_GIT_COMMIT="$(git rev-parse HEAD)"
cd logger

# Retain the running image before the build changes its tag.
container_id="$(docker compose ps -aq search_app)"
rollback_image=""
if [ -n "$container_id" ]; then
    previous_image="$(docker inspect --format '{{.Image}}' "$container_id")"
    rollback_image="sol-logger-search_app:rollback-$(date +%Y%m%d-%H%M%S)"
    docker image tag "$previous_image" "$rollback_image"
fi

echo "==> Building release before stopping collection"
docker compose build search_app
stopped=0
rollback_file="$(mktemp)"
chmod 600 "$rollback_file"
cleanup() {
    result=$?
    trap - EXIT
    if [ "$result" -ne 0 ] && [ "$stopped" -eq 1 ] && [ -n "$rollback_image" ]; then
        echo "==> Release failed; restoring the previous image" >&2
        python3 - "$rollback_image" "$rollback_file" <<'PYROLLBACK'
import json, sys
with open(sys.argv[2], 'w') as target:
    json.dump({"services": {"search_app": {"image": sys.argv[1], "healthcheck": {
        "test": ["CMD-SHELL", "curl -fsS http://127.0.0.1:7001/welcome >/dev/null || exit 1"]}}}}, target)
PYROLLBACK
        docker compose -f docker-compose.yml -f "$rollback_file" up -d --no-build --wait --wait-timeout 120 search_app || \
            echo "Rollback needs operator attention; preserved backup and image are available." >&2
    fi
    rm -f "$rollback_file"
    exit "$result"
}
trap cleanup EXIT

echo "==> Taking a consistent backup with collection stopped"
docker compose stop search_app
stopped=1
# First upgrade: copy the old container's filesystem sessions into durable storage.
if [ -n "$container_id" ] && [ -z "$(ls -A student-sessions)" ]; then
    docker cp "$container_id:/app/flask_session/." student-sessions/
fi
backup="backups/study-$(date +%Y%m%d-%H%M%S).zip"
python3 search-app/tools/backup_study.py create "$backup" --root .

echo "==> Starting release and waiting for collection readiness"
docker compose up -d --no-build --wait --wait-timeout 120 search_app
stopped=0
docker compose ps
echo "Verified backup: $backup"
if [ -n "$rollback_image" ]; then echo "Previous image: $rollback_image"; fi
REMOTE

echo ""
echo "==> Deploy complete."
echo ""
echo "Smoke-test from your laptop while on VPN:"
echo "    curl -I http://solar.usilu.net:7001/welcome"
echo "    Research dashboard: http://solar.usilu.net:7001/dashboard"
echo ""
echo "Tail live logs:"
echo "    ssh $SERVER_USER@$SERVER_HOST 'cd ~/$SERVER_REPO/logger && docker compose logs -f search_app'"
