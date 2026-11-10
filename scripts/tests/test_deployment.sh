#!/usr/bin/env bash
# Exercise the real orchestration scripts with synthetic config and command stubs.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE_BASE="$(cd "${TMPDIR:-/tmp}" && pwd -P)"
FIXTURE_DIR="$(mktemp -d "$FIXTURE_BASE/vp-deployment-test.XXXXXX")"
[[ "$FIXTURE_DIR" == "$FIXTURE_BASE"/vp-deployment-test.* && "$(cd "$FIXTURE_DIR/.." && pwd -P)" == "$FIXTURE_BASE" ]]
trap 'rm -rf -- "$FIXTURE_DIR"' EXIT
mkdir -p "$FIXTURE_DIR/bin" "$FIXTURE_DIR/config/secrets"
cp "$ROOT_DIR/virtual-patient-api/config/deployment.json" "$FIXTURE_DIR/config/deployment.json"
printf '%s\n' synthetic-worker-token-test-fixture-only > "$FIXTURE_DIR/config/secrets/video-processing-worker-token.txt"
cp "$ROOT_DIR/deploy-full.sh" "$ROOT_DIR/deploy-local.sh" "$FIXTURE_DIR/"
sed -e 's/change-me/synthetic/g' -e 's/^SECRET_KEY=.*/SECRET_KEY=synthetic-secret-with-at-least-32-characters/' "$ROOT_DIR/.env.full.example" > "$FIXTURE_DIR/.env.full"
cp "$FIXTURE_DIR/.env.full" "$FIXTURE_DIR/.env.local"
cat > "$FIXTURE_DIR/bin/docker" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$CALL_LOG"
STUB
cat > "$FIXTURE_DIR/bin/curl" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$CALL_LOG"
exit 0
STUB
chmod +x "$FIXTURE_DIR/bin/docker" "$FIXTURE_DIR/bin/curl"
ORIGINAL_PATH="$PATH"
export PATH="$FIXTURE_DIR/bin:$PATH"
export CALL_LOG="$FIXTURE_DIR/calls.txt"
for script in deploy-full.sh deploy-local.sh; do
  for action in setup up restart; do
    : > "$CALL_LOG"
    ENV_FILE="$FIXTURE_DIR/.env.full" bash "$FIXTURE_DIR/$script" "$action" > /dev/null
    grep -E '(up|restart).*video-processing-worker' "$CALL_LOG" > /dev/null || {
      echo "$script $action omitted the visual worker" >&2; exit 1;
    }
    if [[ "$script" == deploy-full.sh ]]; then
      grep -F 'http://127.0.0.1:8091/health' "$CALL_LOG" > /dev/null
    fi
  done
done
mv "$FIXTURE_DIR/config/deployment.json" "$FIXTURE_DIR/config/deployment.json.disabled"
if ENV_FILE="$FIXTURE_DIR/.env.full" bash "$FIXTURE_DIR/deploy-full.sh" up > /dev/null 2>&1; then
  echo 'Production accepted a missing deployment policy' >&2
  exit 1
fi
echo 'Deployment orchestration and missing-policy rejection: passed'

# Inspect the actual Compose contract with synthetic values, without starting it.
cp "$FIXTURE_DIR/.env.local" "$FIXTURE_DIR/.env.full"
export PATH="$ORIGINAL_PATH"
cd "$ROOT_DIR"
while IFS='=' read -r key _; do
  if [[ "$key" =~ ^[A-Z_][A-Z0-9_]*$ ]]; then unset "$key"; fi
done < "$FIXTURE_DIR/.env.full"
docker compose --env-file "$FIXTURE_DIR/.env.full" -f docker-compose.full.yml --profile tools config --quiet
docker compose --env-file "$FIXTURE_DIR/.env.full" -f docker-compose.full.yml --profile tools config --format json |
  docker compose --env-file .env.local.example -f docker-compose.local.yml exec -T api python -c '
import json, sys
from app.core.config import Settings
services = json.load(sys.stdin)["services"]
for service in ("api", "setup", "video-processing-worker"):
    env = services[service]["environment"]
    assert not {"MEDIA_CONSENT_POLICY_VERSION", "MEDIA_RETENTION_MONTHS",
                "VIDEO_PROCESSING_WORKER_TOKEN", "VIDEO_PROCESSING_WORKER_TIMEOUT_SECONDS"}.intersection(env)
    assert services[service]["configs"][0]["target"] == "/app/config/deployment.json"
    assert services[service]["secrets"][0]["source"] == "video_processing_worker_token"
    assert env["OMP_NUM_THREADS"] == "2"
    Settings(environment=env["ENV"], secret_key=env["SECRET_KEY"],
             recaptcha_secret_key=env["RECAPTCHA_SECRET_KEY"],
             superuser_password=env["SUPERUSER_PASSWORD"],
             video_processing_worker_token="synthetic-worker-token-test-fixture-only",
             media_retention_months=12)
print("Actual production Compose configuration and Settings: passed")
'
