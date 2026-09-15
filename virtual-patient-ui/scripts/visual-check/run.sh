#!/usr/bin/env bash
# Captures screenshots + layout metrics of the auth views with Playwright.
#
# This script expects the Vite dev server to be already running. Start it in a
# separate terminal first (Google's public reCAPTCHA test key lets the captcha
# render on localhost; it is not a secret):
#
#   VITE_RECAPTCHA_SITE_KEY=6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI \
#     corepack yarn dev --port 5173 --strictPort
#
# Then, from the virtual-patient-ui directory:
#
#   bash scripts/visual-check/run.sh [baseUrl]
#
# Output (screenshots + metrics.json) is written to scripts/visual-check/output/.

set -euo pipefail

UI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$UI_DIR"

BASE_URL="${1:-http://localhost:5173}"

if ! curl -sSf "$BASE_URL" >/dev/null 2>&1; then
  echo "Dev server is not reachable at ${BASE_URL}."
  echo "Start it first (see the header of this script), then re-run."
  exit 1
fi

echo "Capturing screenshots and metrics from ${BASE_URL} ..."
node scripts/visual-check/capture.mjs "$BASE_URL"
echo "Done."
