#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.local.yml"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.local}"

if [[ ! -f "$ENV_FILE" ]]; then
  ENV_FILE="$ROOT_DIR/.env.local.example"
  echo "No .env.local found; using reproducible non-secret defaults."
fi

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local attempts="${3:-60}"
  local attempt

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if curl --fail --silent --show-error "$url" >/dev/null 2>&1; then
      echo "$name is ready: $url"
      return 0
    fi
    sleep 2
  done

  echo "$name did not become ready: $url" >&2
  compose ps >&2
  return 1
}

verify() {
  wait_for_url "API" "http://127.0.0.1:8000/health"
  wait_for_url "UI" "http://127.0.0.1:5173/"
  compose exec -T api python scripts/verify_deployment.py
}

action="${1:-setup}"
case "$action" in
  setup)
    compose up -d --build postgres
    compose --profile tools run --rm setup
    compose up -d --build api ui
    verify
    ;;
  up)
    compose up -d api ui
    ;;
  ui)
    compose up -d --build --force-recreate --no-deps ui
    ;;
  database)
    compose up -d postgres
    compose --profile tools run --rm setup
    ;;
  verify)
    verify
    ;;
  restart)
    compose up -d --build --force-recreate api ui
    verify
    ;;
  status)
    compose ps
    ;;
  logs)
    compose logs --follow --tail=200 "${@:2}"
    ;;
  down)
    compose down
    ;;
  *)
    echo "Usage: bash deploy-local.sh {setup|up|ui|database|verify|restart|status|logs|down}" >&2
    exit 2
    ;;
esac
