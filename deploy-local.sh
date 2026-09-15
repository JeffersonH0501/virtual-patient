#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.local.yml"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.local}"

# Enable BuildKit so the Dockerfile pip/apt cache mounts are reused across
# rebuilds. This keeps a rebuild fast (only changed layers run) even when the
# heavy Py-Feat / PyTorch dependency layer must be revisited.
export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"
export COMPOSE_DOCKER_CLI_BUILD="${COMPOSE_DOCKER_CLI_BUILD:-1}"

if [[ ! -f "$ENV_FILE" ]]; then
  ENV_FILE="$ROOT_DIR/.env.local.example"
  echo "No .env.local found; using reproducible non-secret defaults."
fi

# ---------------------------------------------------------------------------
# Automatic rebuild detection.
#
# Application source code is bind-mounted into the containers (see the compose
# volumes), so editing Python or TypeScript never needs an image rebuild — a
# plain "up" (or the dev server's own reload) picks it up. An image rebuild is
# only required when the files baked INTO the image change: the dependency
# manifests and the Dockerfiles themselves.
#
# We track a content hash of exactly those files per service. On "up" we compare
# the current hash against the last-built hash and rebuild ONLY the service whose
# dependency inputs changed. This avoids both the slow "always --build" and the
# stale "never rebuild" failure modes.
# ---------------------------------------------------------------------------

STATE_DIR="$ROOT_DIR/.deploy-local"
mkdir -p "$STATE_DIR"

# Files whose changes require rebuilding each image. Keep these in sync with the
# COPY/RUN steps of the respective Dockerfile.
API_DEP_FILES=(
  "$ROOT_DIR/virtual-patient-api/requirements.txt"
  "$ROOT_DIR/virtual-patient-api/Dockerfile"
  "$ROOT_DIR/virtual-patient-api/.dockerignore"
)
UI_DEP_FILES=(
  "$ROOT_DIR/virtual-patient-ui/package.json"
  "$ROOT_DIR/virtual-patient-ui/yarn.lock"
  "$ROOT_DIR/virtual-patient-ui/.yarnrc.yml"
  "$ROOT_DIR/virtual-patient-ui/.yarn/releases/yarn-4.6.0.cjs"
  "$ROOT_DIR/virtual-patient-ui/Dockerfile"
  "$ROOT_DIR/virtual-patient-ui/.dockerignore"
)

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

# Portable file hash (prefers sha256sum, falls back to shasum).
hash_files() {
  local file
  for file in "$@"; do
    if [[ -f "$file" ]]; then
      cat "$file"
    else
      echo "missing:$file"
    fi
  done | { sha256sum 2>/dev/null || shasum -a 256; } | awk '{print $1}'
}

# Returns 0 (needs rebuild) when the dependency hash for a service differs from
# the last recorded one, or when the service image does not exist yet.
service_needs_build() {
  local service="$1"
  shift
  local current recorded state_file image_id
  current="$(hash_files "$@")"
  state_file="$STATE_DIR/$service.deps.sha256"
  recorded=""
  [[ -f "$state_file" ]] && recorded="$(cat "$state_file")"

  # Force a build if the image is not present, regardless of the hash state.
  image_id="$(compose images -q "$service" 2>/dev/null || true)"

  if [[ -z "$image_id" || "$current" != "$recorded" ]]; then
    return 0
  fi
  return 1
}

record_service_hash() {
  local service="$1"
  shift
  hash_files "$@" >"$STATE_DIR/$service.deps.sha256"
}

# Build only the services that need it, then record their new dependency hash.
# With no changed deps this is a no-op and "up" starts instantly.
build_if_needed() {
  local to_build=()

  if service_needs_build api "${API_DEP_FILES[@]}"; then
    to_build+=(api)
  fi
  if service_needs_build ui "${UI_DEP_FILES[@]}"; then
    to_build+=(ui)
  fi

  if [[ ${#to_build[@]} -eq 0 ]]; then
    echo "Dependencies unchanged; skipping image build."
    return 0
  fi

  echo "Dependency changes detected in: ${to_build[*]}. Building those images..."
  compose build "${to_build[@]}"

  # Record hashes only after a successful build so an interrupted build retries.
  local service
  for service in "${to_build[@]}"; do
    case "$service" in
      api) record_service_hash api "${API_DEP_FILES[@]}" ;;
      ui) record_service_hash ui "${UI_DEP_FILES[@]}" ;;
    esac
  done
}

record_all_hashes() {
  record_service_hash api "${API_DEP_FILES[@]}"
  record_service_hash ui "${UI_DEP_FILES[@]}"
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

action="${1:-up}"

case "$action" in

  setup)
    echo "Performing initial local environment setup..."

    # Explicitly build application images.
    compose build api ui
    record_all_hashes

    # Start database.
    compose up -d db

    # Initialize/update database.
    compose --profile tools run --rm setup

    # Start application using the already-built images.
    compose up -d --no-build api ui

    verify
    ;;

  up)
    # Default developer flow: rebuild ONLY when dependency inputs changed, then
    # start. Editing app source needs no rebuild (it is bind-mounted), so this
    # is a fast start in the common case.
    echo "Starting local development environment..."
    build_if_needed
    compose up -d --no-build api ui
    ;;

  build)
    echo "Building application images..."
    compose build api ui
    record_all_hashes
    ;;

  rebuild)
    echo "Forcing a full rebuild of application images..."

    compose build "${@:2}" api ui
    record_all_hashes
    compose up -d --force-recreate api ui

    verify
    ;;

  restart)
    echo "Restarting application containers without rebuilding..."

    compose restart api ui

    verify
    ;;

  ui)
    echo "Starting UI (rebuilding only if its dependencies changed)..."
    if service_needs_build ui "${UI_DEP_FILES[@]}"; then
      compose build ui
      record_service_hash ui "${UI_DEP_FILES[@]}"
    fi
    compose up -d --no-build ui
    ;;

  database)
    echo "Starting database and running setup..."

    compose up -d db
    compose --profile tools run --rm setup
    ;;

  test)
    shift || true
    compose exec -T api pytest "$@"
    ;;

  verify)
    verify
    ;;

  status)
    compose ps
    ;;

  logs)
    shift || true
    compose logs --follow --tail=200 "$@"
    ;;

  down)
    compose down
    ;;

  *)
    echo "Usage: bash deploy-local.sh {setup|up|build|rebuild|restart|ui|database|test|verify|status|logs|down}" >&2
    echo "" >&2
    echo "  up       Start dev env; auto-rebuilds only the service whose" >&2
    echo "           dependency files (requirements.txt / package.json /" >&2
    echo "           yarn.lock / .yarnrc.yml / Dockerfile) changed." >&2
    echo "  rebuild  Force a full rebuild and recreate (use after clearing" >&2
    echo "           caches or when in doubt)." >&2
    exit 2
    ;;

esac
