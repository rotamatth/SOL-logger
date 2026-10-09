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
mkdir -p logger/logs
mkdir -p logger/logs-v2 logger/research-state logger/research-secrets
# Stamp new run metadata with the revision actually built on the server.
export SOL_GIT_COMMIT="$(git rev-parse HEAD)"
if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
    export SOL_GIT_COMMIT="${SOL_GIT_COMMIT}-dirty"
fi

echo "==> Building and restarting containers"
cd logger
docker compose up --build -d --remove-orphans
docker compose ps
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
