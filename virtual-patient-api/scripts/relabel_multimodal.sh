#!/usr/bin/env bash
#
# Relabel stored multimodal turns for one or more interviews without
# re-extracting media (Requirement 21.1, 21.3). Thin Bash entry point over
# scripts/relabel_multimodal.py; per AGENTS.md all automation entry points are
# Bash .sh (no PowerShell). On Windows, run via Git Bash or WSL:
#   bash scripts/relabel_multimodal.sh <interview_id> [<interview_id> ...]
#
# Runs from the API directory (the parent of this script's scripts/ folder) so
# the "app" and "scripts" packages import correctly.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
api_dir="$(dirname "${script_dir}")"

cd "${api_dir}"
exec python -m scripts.relabel_multimodal "$@"
