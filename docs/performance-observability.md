# Performance observability

A lightweight layer for measuring the cost of interview operations (calibration,
conversation, multimodal processing, automatic evaluation). It reuses the
existing `performance_event` log convention and persists interview-scoped
events in PostgreSQL so an interview's timeline can be reviewed and deleted
with that interview. It adds no service or dependency and does not change
algorithms or results.

## What it emits

One structured line per measured operation, on a single greppable line:

```
performance_event component=<name> operation=<name> phase=<complete|error> status=<success|error> trace_id=<id> duration_ms=<float> <safe key=value fields...> worker_pid=<pid> worker_rss_mb=<mb>
```

- `duration_ms` uses a monotonic clock (`time.perf_counter`).
- `trace_id` correlates frontend → API → worker (see below).
- Fields carry only safe technical metadata: sizes, counts, durations, ids,
  status. Never audio, video, transcripts, prompts, clinical answers, tokens or
  personal data.

Source: `virtual-patient-api/app/utils/perf.py`.
- `perf_event(component, operation, *, phase, status, duration_ms, trace_id, **fields)` — emit one line.
- `track(component, operation, *, trace_id, **fields)` — context manager that
  times a block, emits `phase=complete status=success` on success or
  `phase=error status=error error_type=<Exc>` on exception (and re-raises).
  Yields a mutable dict for late metadata: `with track(...) as e: e["chars"] = n`.

Both are no-ops when disabled and never raise into the measured operation.
Events with a real, eligible `interview_id` are also stored in
`interview_performance_events`; storage failures do not fail the measured
operation.

## Durable interview timeline

Each stored row has a required foreign key to one interview and is removed by
the database cascade when that interview is deleted. Only admin accounts can
read these rows, through the calibration-reference dialog in interview review.
The API rejects non-admin access even when the interview ID is known.

Stored events cover real interview creation and calibration, session start,
conversation, server speech transcription and synthesis, multimodal processing,
paraverbal extraction, and evaluation when the producer has an interview ID.
The server checks that the interview exists and is not marked
`calibration_test=true` before writing an event. Gaze calibration tests and
nonverbal tests are excluded. Global
worker warmup/idle events without an interview ID remain in stdout only.

Metadata is limited to safe technical scalars such as stage, status, counts,
durations, byte sizes, and internal IDs. Raw logs, media, transcripts, prompts,
clinical answers, and personal data are not stored in the timeline.

## Activation

Performance timing events are always enabled. There is no environment variable
or runtime switch to disable their log emission or per-interview persistence.

## Correlation (trace_id)

The UI sends an `X-Trace-Id` header on every request (a stable per-tab id added
centrally in `virtual-patient-ui/src/utils/apiFetch.ts`). `TraceIdMiddleware`
(`app/core/trace.py`) binds it for the request and echoes it back in the
`X-Trace-Id` response header (exposed via CORS). Any `performance_event` emitted
while handling that request carries the same `trace_id`. When no header is sent
(non-browser caller), a short server id is generated so each request is still
self-correlatable.

Durable work that outlives the request (multimodal pipeline, worker jobs)
continues to correlate by `interview_id` / `recording_id` / `turn_id`, as before.

## Instrumented boundaries

Already present before this layer (kept as-is): calibration reception
(`routers/calibration.py`), text evaluation and completion
(`routers/medical_interviews.py`), paraverbal extraction
(`paraverbal/opensmile_extractor.py`), multimodal pipeline and per-turn video
(`multimodal/pipeline.py`, `turn_video_queue.py`, `media_processing_worker.py`).

Added by this layer:
- Conversation STT and TTS (`routers/speech.py`): `component=conversation operation=stt|tts`.
- Patient-response request, controller, and workflow stages are always recorded with `interview_id`.
- Multimodal evaluation (`multimodal/evaluation_service.py`): `component=evaluation operation=multimodal_evaluation`.
- Per-interview completion snapshot (`routers/medical_interviews.py`):
  `component=interview_completion operation=turn_jobs_snapshot`. Emitted once
  when analysis becomes terminal, it reports how many durable turn jobs
  finished before the interview closed versus how many were still pending
  (`turn_jobs_completed`, `turn_jobs_failed`, `turn_jobs_pending`,
  `turn_jobs_finished`, `turn_jobs_total`), alongside the real participant wait
  (`duration_ms`) from the completion request to analysis being terminal.
  Calibration and isolated tests never contribute, because they create no
  per-interview turn jobs and are excluded from the durable timeline.

## Querying in local development and Docker

Operational logs still go to Docker's default driver; query a service with
`docker compose logs`. A container's log history is lost when it is recreated.
The admin interview-review dialog reads durable per-interview timing rows from
the database; deleting an interview deletes its timeline rows as well.

Per-interview flow plus a resource snapshot (API + worker):

```bash
cd virtual-patient
bash scripts/inspect_multimodal_performance.sh <INTERVIEW_ID> 2h
```

Only performance events:

```bash
docker compose -f docker-compose.local.yml logs --since 2h api media-processing-worker 2>&1 \
  | grep performance_event
```

Follow one browser action end to end by its trace id (read it from the
`X-Trace-Id` response header in the browser devtools Network tab):

```bash
docker compose -f docker-compose.local.yml logs --since 2h api media-processing-worker 2>&1 \
  | grep 'trace_id=<ID>'
```

### Example: reconstruct a full calibration and find its slowest phase

```bash
# 1. All events for the interview, API + worker:
bash scripts/inspect_multimodal_performance.sh 71 2h | grep performance_event

# 2. Just calibration, newest last:
docker compose -f docker-compose.local.yml logs --since 2h api media-processing-worker 2>&1 \
  | grep performance_event | grep 'component=calibration\|operation=calibration'

# 3. Rank phases by duration (the worker pipeline emits a timings_ms=<json> map;
#    the calibration event carries capture_duration_ms, upload_bytes, duration_ms):
docker compose -f docker-compose.local.yml logs --since 2h api media-processing-worker 2>&1 \
  | grep performance_event \
  | grep -oE 'operation=[^ ]+ .*duration_ms=[0-9.]+' | sort -t= -k3 -nr | head
```

The `duration_ms` on each stage/phase line, and the `timings_ms` breakdown on
the pipeline/turn-video events, identify the slowest sub-phase to target later.
This layer only measures; it does not optimize anything.
