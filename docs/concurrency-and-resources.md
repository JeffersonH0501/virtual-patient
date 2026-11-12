# Concurrency, resources and priority — audit and changes

Goal: prepare VPMedChat for up to five concurrent clinical interviews, with
calibration and live conversation (P0) prioritized over deferred analysis (P2),
and a responsive UI — without breaking science, models or the shared host.

This documents the audit, the capacity found, the architecture before/after, the
changes made, the tests run, and the residual risks. It does not claim support
for five real simultaneous sessions with cameras, microphones and external
providers; see the checklist at the end for what still must be validated live.

## 1. Hardware / concurrency limits found (audit)

Backend is pure Uvicorn (no Gunicorn). Per-turn visual extraction runs in the
separate `media-processing-worker` service. The full multimodal pipeline also
uses an isolated child process spawned by the API; that child still shares the
API container's CPU and memory limits.

Protective limits (kept — science / model-safety / OOM):
- Native thread caps in `virtual-patient-api/config/native-runtime.conf`
  (OMP/OPENBLAS/MKL/NUMEXPR=2, TF intra=2/inter=1, MALLOC_ARENA_MAX=2).
- Visual worker is a cluster-wide singleton (PostgreSQL advisory lock
  `8642091731`) with a single processor thread → native visual work is
  concurrency=1. `media_processing_worker.py`.
- Full-pipeline cap of 2 concurrent runs across API processes (advisory locks
  `846217310/311`, `process_isolation.py PIPELINE_CAPACITY=2`).
- Single durable background-job runner (advisory lock `846217320`,
  `processing_jobs.py`).
- Interactive calibration reserve: 4 of 32 visual-queue slots
  (`CALIBRATION_QUEUE_RESERVE=4`) so turn-video backlog never starves calibration.
- `NONVERBAL_GAZE_QUEUE_CAPACITY=8`, model idle-release at 300s, native job
  timeouts (180s calibration / 900s turn-video / 22200s pipeline), `lru_cache(1)`
  model bundle, `lock_row` FOR UPDATE + 2s lock_timeout, per-interview
  `message_request` claim (120s). Per-interview and per-job locks serialize only
  within one interview/job — not globally.

Arbitrary / untuned caps found:
- SQLAlchemy pool left at defaults (5 + 10 overflow, no pre_ping, no recycle).
- Admission gates `Semaphore(4)` external + `Semaphore(2)` review in
  `core/database.py` (per-process fairness heuristic; kept).
- API Uvicorn workers: 1 (local, `--reload`) vs 4 (full, Dockerfile default).

## 2. Real capacity and risks

Measured on the local Docker VM: 8 CPUs, ~7.8 GB RAM, PostgreSQL
`max_connections=100`.

At audit time, `api` and `media-processing-worker` each had `mem_limit: 4g`
→ 8 GB of possible use on a 7.8 GB VM. The current configuration removes the
API cap as requested and keeps a fixed cap only on the visual worker. This
assumes interactive API work remains comparatively light; the API can now use
host memory without a container limit, so target-host monitoring remains
important.

Nature of the load for 5 interviews: the interactive P0 path (STT/LLM/TTS) is
I/O-bound on Azure — many threadpool threads waiting, little local CPU/RAM. The
P2 visual worker is serialized, but the API also launches up to two isolated
full-pipeline subprocesses. Removing the API container caps means these
subprocesses are no longer bounded by a container CPU or memory limit.

## 3. Execution architecture and priorities — before / after

Before: api 3 CPU / 4g, worker 3 CPU / 4g (8g on a 7.8g VM); DB pool at defaults;
no explicit P0 latency/concurrency instrumentation; priority ordering already
present in the visual worker and pipeline/background schedulers.

Current: API has no CPU/memory cap; local worker is fixed at 2 CPU / 2560 MiB
(P2 yields), and full deployment worker is fixed at 3 CPU / 4 GiB. PostgreSQL
pool settings are fixed in code (10 + 10, pre_ping, 1800s recycle). P0
conversation turns carry a `priority=P0` performance event with a
per-worker concurrent-turn gauge and a latency breakdown. Priority scheduling
(P0 calibration/turns preempt P2 turn-video via the reserve + priority queue;
P2 pipeline capped at 2; single background runner) was already correct and is
unchanged.

## 4. Changes implemented and why

- `docker-compose.local.yml`: removed API `cpus` and `mem_limit`; the worker
  keeps fixed limits of 2 CPU / 2560 MiB.
- `docker-compose.full.yml`: the API has no CPU/memory caps; only the visual
  worker is constrained. Its limits can be set with `WORKER_CPUS` and
  `WORKER_MEM_LIMIT`; defaults are 3 CPUs / 4 GiB in full Compose and 2 CPUs /
  2560 MiB in local Compose. These are the only resource-pool tuning variables
  exposed through the `.env` files.
- `app/core/database.py`: `create_engine` now sets `pool_size`, `max_overflow`,
  `pool_timeout`, `pool_pre_ping=True`, and `pool_recycle` as fixed application
  settings: 10 pooled connections, 10 overflow, 30-second checkout timeout, and
  1800-second recycle. `pre_ping` drops dead connections instead of failing a
  request. These pool values are per Python process.
- `app/utils/perf.py`: added a process-local, thread-safe concurrency gauge
  (`active_gauge`, `gauge_value`) on top of the existing performance_event layer.
- `app/routers/interview_messages.py`: the patient-reply path increments the
  `active_interview_turns` gauge and emits a `priority=P0` performance event with
  `generation_ms`/`persistence_ms`/`total_ms` and the concurrent-turn count. No
  behavioral change to message handling.

Not changed (deliberately): the visual worker singleton + concurrency=1, the
2-slot pipeline cap, the background-runner singleton, the calibration reserve,
all native thread caps and timeouts, every prompt/model/threshold/criterion.

## 5. Concurrency test results

Synthetic / unit, with the live local stack (no real cameras or Azure):
- Perf gauge: 5 threads enter `active_gauge` concurrently → peak gauge = 5,
  returns to 0 after each block and on exception (`app/utils/tests/test_perf.py`,
  8/8).
- Backend concurrency suites: `test_recording_blocks.py` (10 interviews preserve
  independent originals), `test_speech_concurrency.py`, `test_recording_segments.py`
  (stale-writer fencing), `test_conversation_concurrency.py` → 31/31.
- API responsiveness under 20 concurrent `/health` requests: all < 60 ms (most
  < 25 ms), sequential ~5–7 ms, api CPU ~11%, mem ~165 MiB of 4.5 GiB, worker idle.
- Full backend suite after changes: 839 passed, 0 failed, 0 regressions.

Not run (needs external providers / hardware): five real simultaneous STT→LLM→TTS
conversations and five concurrent camera calibrations. Those require Azure
credentials and real media and must be measured on the target VM.

## 6. Latency / utilization comparison

- Memory limits now apply only to the visual worker (2.5 GiB local, 4 GiB full).
  API memory is uncapped, so total host memory use is not bounded by these two
  Compose services.
- DB connections: each process can open up to 20 pooled connections, with
  `pre_ping` for stale connections. Full deployment has four API workers plus
  one video worker, so their combined theoretical pool ceiling is 100 before
  auxiliary pipeline and administrative connections; this is not spare
  capacity relative to a PostgreSQL `max_connections=100`.
- P0 latency is now measurable per turn via the `priority=P0` performance event
  (`generation_ms`, `persistence_ms`, `total_ms`, `active_interview_turns`); query
  with the inspect script / `grep 'priority=P0'`. A real before/after latency
  comparison under load requires Azure and is left for the live validation.

## 7. Residual risks and deployment recommendations

- The dominant cross-interview stall under real load is the shared Starlette
  threadpool (~40 threads/process): each turn holds threads for the LLM, the
  translator LLM, checkpointer round-trips and the TTS stream. If five interviews
  saturate it, unrelated DB reads queue behind it. Mitigation if observed: raise
  Uvicorn workers (full already runs 4) and/or the AnyIO threadpool; measure first.
- `process_interview_message` opens two Postgres connections on the event loop
  per turn (`from_conn_string`) and rebuilds the LangGraph workflow uncached. This
  is a known on-loop cost; left unchanged because a safe refactor of the
  checkpointer/store lifecycle is out of scope for this pass. Flagged for a
  follow-up once live latency shows it matters.
- The local worker defaults were tuned for the 8-CPU / 7.8 GB VM; production
  defaults are 3 CPUs / 4 GiB. Both can be changed through the worker variables
  in `.env.local` or `.env.full`; the API is uncapped. If target hardware changes,
  adjust those limits and pool values in `app/core/database.py`, then check host
  RAM and PostgreSQL connection headroom. Production's four API workers plus
  one video worker have a theoretical
  pool ceiling of 100 connections (20 per process), before auxiliary pipeline
  processes and administrative connections; that ceiling must be compared with
  the target PostgreSQL `max_connections`.
- `process_isolation.py` starts full-pipeline child processes inside the API
  container. They are not constrained by the visual worker limits; with the API
  now uncapped, monitor host CPU/RAM during deferred pipeline runs.

## 8. Checklist to validate five real simultaneous interviews

1. Confirm the worker limit configured in the target `.env` fits the VM; the
   API has no container CPU/memory caps.
2. Confirm PostgreSQL `max_connections` can support the fixed pool ceiling plus
   auxiliary pipeline and administrative connections; current full Compose
   settings can reach 100 connections across API and worker processes.
3. With performance timing events always enabled, run five real sessions (camera + mic + Azure):
   calibrate all five, then run overlapping conversation turns.
4. During the run, watch `docker stats` (no container near its mem_limit; host not
   swapping) and `grep 'priority=P0'` for `total_ms`/`active_interview_turns`.
5. Start a sixth-interview turn-video backlog (P2) and confirm a new calibration
   (P0) still completes promptly (reserve working) and the visual queue does not
   return sustained 503s.
6. Verify data integrity: each interview's turns, media and evaluation are
   correct and isolated (no cross-interview leakage); finalize and recover one
   mid-session.
7. Confirm the UI stays responsive (no frozen loaders, audio plays, navigation
   works) on all five clients throughout.
8. Compare P0 latency (calibration, audible-reply) against the single-session
   baseline; investigate if it degrades beyond an acceptable threshold before
   declaring five-session support.
