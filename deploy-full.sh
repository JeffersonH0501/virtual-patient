#!/usr/bin/env bash
set +x
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.full.yml"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.full}"

if [[ ! -f "$ENV_FILE" || ! -r "$ENV_FILE" ]]; then
  echo "Missing or unreadable environment file: $ENV_FILE" >&2
  echo "Create it with: cp .env.full.example .env.full" >&2
  exit 1
fi

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1 | tr -d '\r'
}

validate_configuration() {
  local key value
  local required=(
    POSTGRES_PASSWORD SECRET_KEY AZURE_OPENAI_API_KEY AZURE_OPENAI_ENDPOINT
    SUPERUSER_EMAIL SUPERUSER_NAME SUPERUSER_PASSWORD
    AZURE_OPENAI_LLM_DEPLOYMENT_NAME AZURE_OPENAI_LLM_MINI_DEPLOYMENT_NAME
    AZURE_OPENAI_STT_DEPLOYMENT_NAME AZURE_OPENAI_TTS_DEPLOYMENT_NAME
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME
    VITE_RECAPTCHA_SITE_KEY RECAPTCHA_SECRET_KEY
  )

  for key in "${required[@]}"; do
    value="$(env_value "$key")"
    if [[ -z "$value" || "$value" == *change-me* ]]; then
      echo "Set a real value for $key in $ENV_FILE" >&2
      exit 1
    fi
  done

  local deployment_file
  for deployment_file in config/deployment.json config/secrets/video-processing-worker-token.txt; do
    if [[ ! -s "$ROOT_DIR/$deployment_file" ]]; then
      echo "Missing or empty deployment file: $deployment_file" >&2
      exit 1
    fi
  done

}

wait_for_ui() {
  local port
  local attempt
  port="${HTTP_PORT:-$(env_value HTTP_PORT)}"
  port="${port:-8091}"

  for ((attempt = 1; attempt <= 60; attempt++)); do
    if curl --fail --silent --show-error "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
      echo "UI is ready: http://127.0.0.1:${port}"
      return 0
    fi
    sleep 2
  done

  echo "The full deployment did not become healthy" >&2
  compose ps >&2
  return 1
}

verify() {
  wait_for_ui
  compose exec -T api python scripts/verify_deployment.py
}

action="${1:-setup}"
case "$action" in
  setup)
    validate_configuration
    compose up -d --build postgres
    compose --profile tools run --rm setup
    compose up -d --build api video-processing-worker ui
    verify
    ;;
  up)
    validate_configuration
    compose up -d postgres api video-processing-worker ui
    verify
    ;;
  verify)
    validate_configuration
    verify
    ;;
  restart)
    validate_configuration
    compose up -d --build --force-recreate api video-processing-worker ui
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
    echo "Usage: bash deploy-full.sh {setup|up|verify|restart|status|logs|down}" >&2
    exit 2
    ;;
esac
