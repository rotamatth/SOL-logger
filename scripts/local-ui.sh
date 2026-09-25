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
    printf 'Usage: %s [start|stop|logs|status]\n' "$0" >&2
    exit 2
    ;;
esac
