#!/usr/bin/env bash
#
# Relabel stored multimodal turns for one or more interviews without
# re-extracting media. Run inside the existing API container:
#   bash scripts/tools/relabel_multimodal.sh <interview_id> [<interview_id> ...]
set -euo pipefail

api_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "${api_dir}"
exec python -m scripts.tools.relabel_multimodal "$@"
