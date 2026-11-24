#!/usr/bin/env bash
set -euo pipefail

interview_id="${1:-}"
since="${2:-2h}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd -- "${script_dir}/.." && pwd)"
compose_file="${project_dir}/docker-compose.local.yml"
env_file="${ENV_FILE:-${project_dir}/.env.local}"

if [[ ! -f "${env_file}" ]]; then
  env_file="${project_dir}/.env.local.example"
fi

compose=(docker compose --env-file "${env_file}" -f "${compose_file}")

if [[ ! "${interview_id}" =~ ^[0-9]+$ ]]; then
  echo "Usage: bash scripts/inspect_multimodal_performance.sh INTERVIEW_ID [SINCE]" >&2
  echo "Example: bash scripts/inspect_multimodal_performance.sh 71 2h" >&2
  exit 2
fi

echo "Container resource snapshot"
mapfile -t container_ids < <("${compose[@]}" ps -q api ui db)
if (( ${#container_ids[@]} == 0 )); then
  echo "No running API, UI, or database containers were found."
else
  docker stats --no-stream "${container_ids[@]}"
fi

echo
echo "Durable interview flow for interview ${interview_id}"
"${compose[@]}" exec -T api \
  python -m scripts.tools.inspect_interview_flow "${interview_id}"

echo
echo "Available runtime events for interview ${interview_id} since ${since}"
# Scrape both the API and the media-processing-worker: multimodal performance
# events (calibration worker, turn video, pipeline) live in the worker logs.
events="$(
  "${compose[@]}" logs --since "${since}" api media-processing-worker 2>&1 \
    | grep -E \
      "interview_id=${interview_id}([^0-9]|$)|interview ${interview_id}([^0-9]|$)|/medical-interviews/${interview_id}([/?[:space:]]|$)" \
    | grep -Ev \
      "Interview found:|COMPLETE INTERVIEW PROMPT|Clinical case text|Hypotheses text|Patient Context|Message:|patient response" \
    || true
)"

if [[ -n "${events}" ]]; then
  printf '%s\n' "${events}"
else
  echo "No matching runtime events exist in the current API or worker container logs."
  echo "Docker removes a container's log history when that container is recreated."
fi

echo
echo "Hint: to see only performance_event lines, pipe to: grep performance_event"
echo "To follow one browser action end to end, grep by its trace id:"
echo "  ${compose[*]} logs --since ${since} api media-processing-worker 2>&1 | grep 'trace_id=<ID>'"
