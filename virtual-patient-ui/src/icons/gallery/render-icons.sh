#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
OUTPUT_FILE="$SCRIPT_DIR/icon-gallery.png"
SERVER_LOG="$SCRIPT_DIR/vite.log"
PORT=4174

find_browser() {
  local candidate
  for candidate in \
    "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
    "/c/Program Files/Microsoft/Edge/Application/msedge.exe" \
    "/c/Program Files/Google/Chrome/Application/chrome.exe" \
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
    "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe" \
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" \
    "msedge" \
    "google-chrome" \
    "chromium"; do
    if [[ "$candidate" == /* && -x "$candidate" ]] || command -v "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

BROWSER="$(find_browser || true)"
if [[ -z "$BROWSER" ]]; then
  echo "No supported Chromium browser was found." >&2
  exit 1
fi

cd "$PROJECT_DIR"
corepack yarn vite --host 127.0.0.1 --port "$PORT" >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" >/dev/null 2>&1 || true' EXIT

for _ in {1..30}; do
  if curl --silent --fail "http://127.0.0.1:$PORT/src/icons/gallery/index.html" >/dev/null; then
    break
  fi
  sleep 1
done

if ! curl --silent --fail "http://127.0.0.1:$PORT/src/icons/gallery/index.html" >/dev/null; then
  echo "The icon gallery server did not start. See $SERVER_LOG" >&2
  exit 1
fi

SCREENSHOT_PATH="$OUTPUT_FILE"
if command -v cygpath >/dev/null 2>&1; then
  SCREENSHOT_PATH="$(cygpath -w "$OUTPUT_FILE")"
elif command -v wslpath >/dev/null 2>&1; then
  SCREENSHOT_PATH="$(wslpath -w "$OUTPUT_FILE")"
fi

"$BROWSER" \
  --headless \
  --disable-gpu \
  --hide-scrollbars \
  --window-size=1400,2050 \
  --screenshot="$SCREENSHOT_PATH" \
  "http://127.0.0.1:$PORT/src/icons/gallery/index.html"

echo "Icon gallery generated at: $OUTPUT_FILE"
