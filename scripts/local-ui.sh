#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose=(docker compose --project-name sol-ui
  -f "$project_dir/logger/docker-compose.yml"
  -f "$project_dir/logger/docker-compose.local.yml")

case "${1:-start}" in
  start)
    "${compose[@]}" up -d --build --wait search_app
    printf '\nSOL+ preview: http://localhost:%s/welcome\n' "${LOCAL_UI_PORT:-7001}"
    printf 'Research dashboard: http://localhost:%s/dashboard\n' "${LOCAL_UI_PORT:-7001}"
    if [ ! -s "$project_dir/logger/research-secrets/password.hash" ]; then
      printf 'Set a local dashboard password with: ./scripts/local-ui.sh password\n'
    fi
    ;;
  password)
    mkdir -p "$project_dir/logger/research-secrets"
    "${compose[@]}" run --rm --no-deps --build \
      --volume "$project_dir/logger/research-secrets:/secrets" \
      search_app python tools/set_research_password.py /secrets/password.hash
    ;;
  demo-logs)
    "${compose[@]}" exec -T search_app python - --local-preview \
      --log-dir /app/logs --state-dir /app/research_state \
      < "$project_dir/logger/search-app/tools/seed_research_demo.py"
    printf '\nOpen http://localhost:%s/dashboard and click Refresh saved data.\n' "${LOCAL_UI_PORT:-7001}"
    ;;
  stop)
    "${compose[@]}" down
    ;;
  logs)
    "${compose[@]}" logs --follow --tail=50 search_app
    ;;
  status)
    "${compose[@]}" ps
    ;;
  *)
    printf 'Usage: %s [start|password|demo-logs|stop|logs|status]\n' "$0" >&2
    exit 2
    ;;
esac
