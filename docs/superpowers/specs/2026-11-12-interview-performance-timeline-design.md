# Interview performance timeline design

## Intent

Persist a useful chronological record of technical timings for each real
interview, so its calibration, conversation, processing, and evaluation can be
reviewed together and are removed when that interview is deleted.

## Goals

- Persist performance events only when they belong to an eligible real
  interview.
- Associate each row with a required interview foreign key using database
  cascade deletion.
- Cover interview creation/calibration, interview start, conversation, speech,
  multimodal processing, and evaluation where the operation has a real
  interview identity.
- Provide a read endpoint restricted to admins and expose it only in the
  review view of an interview.
- Show the timeline inside the existing calibration-reference dialog opened
  from interview review next to the replay area.
- Store timing and safe technical metadata only; never store audio, video,
  transcripts, prompts, clinical answers, or personal data.
- Keep existing performance logging enablement behavior and avoid allowing
  observability failures to break interview work.

## Exclusions

- Admin gaze calibration tests and nonverbal tests, including persisted drafts
  marked `calibration_test=true`.
- `PatientPreview` / “Prueba entrevista”, which does not create a real
  interview.
- Global worker startup/warmup/idle events that have no interview identity.
- Existing operational logs may remain in container output, but the durable
  interview timeline must not duplicate events lacking an eligible interview.

## Approaches

1. Keep Docker stdout logs and correlate by interview ID. This requires no
   schema/API work, but deletion cannot remove one interview's lines and log
   retention is controlled by the container driver. Rejected because it does
   not meet per-interview deletion.
2. Add a database event table with a required interview foreign key, cascade
   deletion, and a protected read endpoint. This enables complete interview
   correlation and deletion while reusing the existing database and access
   checks. Selected because it meets the requested lifecycle with one durable
   source of truth.
3. Add a separate observability service. This adds infrastructure and still
   needs per-interview retention/deletion coordination. Rejected as unnecessary
   for the current scale.

## Proposed event contract

Each event stores its creation time, component, operation, phase/status,
duration in milliseconds when known, trace ID when available, and safe
technical metadata. `medical_interview_id` is required and references the
interview with `ON DELETE CASCADE`. Use a JSON metadata field for existing
safe dimensions rather than copying arbitrary log text. Do not persist the
event unless the referenced interview exists and is not marked as a
calibration test. Events are written best-effort and must not change the
measured operation's result.

The read endpoint returns events for one interview in chronological order and
allows only admins to read them. The UI exposes this query only in the review
view, inside the existing calibration-reference dialog opened from beside the
interview replay. Owners and other roles cannot access the timeline through the
API or UI.

Existing helpers and producers are adapted to write durable rows when an
eligible interview ID is present. Add interview identity to real-interview
STT and worker processing boundaries where it is available. Preview and test
callers do not pass an interview ID. Events without interview identity remain
ordinary diagnostics and are not stored in the timeline.

Calibration already has a database draft before `process-stage` runs:
`InterviewCalibration` creates it and sends its ID to the calibration route.
Thus ordinary calibration timings can be persisted immediately; calibration
test drafts use the same route but are rejected by the eligibility check.
Turn-video jobs and the multimodal pipeline already carry interview IDs in
their persisted job/pipeline inputs. STT currently has no interview ID; the
real interview caller will pass one through the existing speech request, while
`PatientPreview` will leave it absent. The server resolves eligibility from
the database and does not trust the client ID alone.

## Constraints and compatibility

- Add a reversible Alembic migration after the current `001_initial_schema`;
  do not rewrite the baseline.
- Keep timing event emission and interview-scoped persistence always enabled.
- Retain existing authorization and deletion behavior. Explicit graph deletion
  must allow the database cascade to remove timeline rows.
- Follow the repository's existing Docker environment for commands and
  validation.

## Non-goals

- A dashboard or a separate timeline page.
- Persisting raw logs, media, model content, or participant data.
- Capturing global worker health, preview activity, or calibration-test
  timings in the interview timeline.
- Changing interview, calibration, speech, multimodal, or evaluation behavior.

## Builder decisions

- Reuse existing SQLAlchemy model and router conventions.
- Keep payload metadata constrained to JSON-safe values and existing
  observability fields.
- Validate interview eligibility at the persistence boundary and admin role at
  the read boundary rather than trusting client-supplied IDs.

## Builder check resolutions

- Calibration identity is available before measurement because ordinary
  calibration creates a draft row first; calibration tests are identified by
  `calibration_test=true` and excluded.
- Background turn-video and multimodal processing already carry interview IDs.
  STT needs the existing real-interview caller to pass its ID; preview keeps
  the field absent.
