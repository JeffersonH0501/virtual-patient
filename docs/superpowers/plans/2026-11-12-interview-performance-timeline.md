# Interview Performance Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist a real interview's safe timing events, delete them with that interview, and let only admins review them in the existing calibration dialog.

**Architecture:** Add an Alembic event table with a required cascading interview foreign key and a best-effort persistence helper that filters calibration-test interviews. Instrument existing interview-scoped performance boundaries, expose an admin-only timeline endpoint, and render the result in `CalibrationReferenceDialog` in review mode.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, React, TypeScript, i18next, existing Docker Compose services.

**Spec:** `docs/superpowers/specs/2026-11-12-interview-performance-timeline-design.md`

## Global Constraints

- All implementation code and technical messages in `virtual-patient/` are English; user-facing strings stay localized.
- Add migration `002_interview_performance_events` after `001_initial_schema`; do not rewrite the baseline.
- Persist only safe technical metadata; never persist media, transcript, prompt, clinical answer, or personal data.
- Persist only events tied to an existing, non-`calibration_test` interview.
- Exclude gaze calibration tests, nonverbal tests, and `PatientPreview` / “Prueba entrevista”.
- Only admins can read the timeline, and only in interview review through the existing calibration-reference dialog.
- Interview deletion removes its events by database cascade.
- Use the existing Docker environment for API/UI commands; no host dependency installs or alternate environments.
- Do not commit unrelated dirty changes.

## Review Focus

- A missing, deleted, or calibration-test interview ID must never create an event: enforce and verify at the persistence boundary.
- A non-admin must receive denial even with a valid interview ID: verify endpoint role enforcement.
- `PatientPreview` shares the speech hook: verify its STT request omits interview ID while real interview STT includes it.
- Failed event persistence must not change the measured operation's response: preserve best-effort behavior.
- Explicit interview graph deletion must remove timeline rows: verify DB cascade integration.

---

### Task 1: Add the durable event model and migration

**Files:**
- Create: `virtual-patient-api/app/models/interview_performance_event.py`
- Modify: `virtual-patient-api/app/models/__init__.py`
- Create: `virtual-patient-api/alembic/versions/002_interview_performance_events.py`
- Modify: `virtual-patient-api/app/models/medical_interview/medical_interview.py`

**Interfaces:**
- Produce `InterviewPerformanceEventDB` with required `medical_interview_id`, timestamp, component, operation, phase, status, nullable duration/trace ID, and JSON-safe metadata.
- Interview FK uses `ON DELETE CASCADE`; add relationship with delete-orphan behavior consistent with neighboring models.

- [x] Define the model and relationship using current SQLAlchemy conventions.
- [x] Add reversible migration `002` with an index on `(medical_interview_id, created_at, id)`.
- [x] Verify Alembic head and model metadata inside the API container.

### Task 2: Persist eligible performance events

**Files:**
- Modify: `virtual-patient-api/app/utils/perf.py`
- Create: `virtual-patient-api/app/utils/interview_performance.py`
- Modify: `virtual-patient-api/app/routers/interview_messages.py`
- Modify: `virtual-patient-api/app/routers/speech.py`
- Modify: `virtual-patient-api/app/routers/calibration.py`
- Modify: `virtual-patient-api/app/routers/medical_interviews.py`
- Modify: `virtual-patient-api/app/multimodal/pipeline.py`
- Modify: `virtual-patient-api/app/multimodal/turn_video_queue.py`
- Modify: `virtual-patient-api/app/multimodal/video_processing_worker.py`
- Modify: `virtual-patient-api/app/multimodal/evaluation_service.py`
- Modify: `virtual-patient-api/app/paraverbal/opensmile_extractor.py`

**Interfaces:**
- Add a best-effort writer accepting an existing DB session and structured event fields; writer checks interview existence and rejects `interview_metadata.calibration_test is True`.
- Keep `perf_event`/`track` signatures backward compatible; persist only when a valid interview ID and DB session are supplied.
- STT request accepts optional `interview_id`; real interview supplies it, preview omits it. Server validates interview eligibility/access before associating the event.

- [x] Instrument interview-scoped events from creation/calibration through session, speech, processing, and evaluation.
- [x] Preserve existing timing/status values; store safe structured metadata, never raw log text.
- [x] Ensure worker jobs use their persisted interview ID and discard global warmup/idle events from the durable timeline.
- [x] Keep event persistence failures isolated from the measured operation; requests running on an async event loop submit writes to a shared two-worker executor.
- [x] Verify targeted API module compilation inside the API container.

### Task 3: Add the admin-only read endpoint

**Files:**
- Create: `virtual-patient-api/app/routers/interview_performance.py`
- Modify: `virtual-patient-api/main.py`

**Interfaces:**
- `GET /medical-interviews/{interview_id}/performance-events` returns ordered event rows for an existing interview.
- Require `UserRole.ADMIN`; return 404 for unknown interview IDs and do not expose timeline data to owners or other roles.

- [x] Implement response schema and chronological query with stable `created_at, id` ordering.
- [x] Register the router under the existing API route conventions.
- [x] Verify route import and targeted API compilation inside Docker.

### Task 4: Show the timeline in interview review

**Files:**
- Create: `virtual-patient-ui/src/services/interviews/performanceEvents.ts`
- Modify: `virtual-patient-ui/src/services/speech/transcribeStudentAudio.ts`
- Modify: `virtual-patient-ui/src/speech/ServerSpeechTranscriptionProvider.ts`
- Modify: `virtual-patient-ui/src/hooks/useHandsFreeSpeech.ts`
- Modify: `virtual-patient-ui/src/components/ClinicalChat/index.tsx`
- Modify: `virtual-patient-ui/src/components/ClinicalChat/CalibrationReferenceDialog.tsx`
- Modify: `virtual-patient-ui/src/i18n/locales/en.json`
- Modify: `virtual-patient-ui/src/i18n/locales/es.json`

**Interfaces:**
- Fetch `GET /medical-interviews/{id}/performance-events` using `apiFetch`, with `AbortSignal` support.
- Pass optional `interviewId` through the speech hook, provider, and transcription service; only `ClinicalChat` supplies it, leaving preview transcription unassociated.
- Render only in the existing admin-only calibration-reference dialog, in review mode, alongside its interview replay context.

- [x] Add typed event response and service function.
- [x] Load the timeline when the existing dialog opens; show localized loading, empty, error/retry, and chronological event states.
- [x] Format timestamps and durations clearly without exposing arbitrary metadata as raw unbounded content.
- [x] Verify the affected UI build/lint inside the UI container.

### Task 5: Update operational documentation

**Files:**
- Modify: `virtual-patient/docs/performance-observability.md`

- [x] Document persisted per-interview scope, exclusions, admin review location, and cascade deletion.
- [x] Clarify stdout remains operational logging and is not the durable interview timeline.

## Plan self-review

- Spec coverage: model/cascade (Task 1), eligibility and complete event lifecycle (Task 2), admin-only access (Task 3), review dialog (Task 4), operational behavior (Task 5).
- Verification run: API compile/import/ORM mapper and Alembic head check; UI lint/build. Automated tests were not run.
- Endpoint and UI agree on `created_at`, `duration_ms`, `component`, `operation`, `phase`, `status`, `trace_id`, and safe metadata fields.
- Avoid adding a dashboard, general-purpose log ingestion, or changes to scientific pipeline behavior.
