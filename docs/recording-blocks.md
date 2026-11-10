# Reusable interview block transport

New UI-created interviews declare `interview_metadata.recording_transport = reusable_blocks_v1` before calibration. Existing drafts, active interviews and recordings retain their transport. Interview updates cannot change it.

One capture attempt is authorized through the existing segment/resume/calibration contract. Its ordered UUID blocks contain one muxed camera/microphone original, message IDs, speech/playback windows, delivery flags and patient-region snapshots. Calibration and geometry belong to the attempt.

## Review UI lifecycle

Review state is scoped to account, authority and interview identity. A change of
identity clears ephemeral state before displaying the next interview. Refreshing
the same interview retains confirmed content and mounted media. Periodic reads
are serialized; obsolete reads are aborted or ignored. Failed recap reads expose
a retry without removing the confirmed replay.

Block playback uses a dedicated client controller with paused, buffering, playing
and error phases. It keeps the current and next video prepared and preloads only
the current and next preserved patient audio. An audio currently playing remains
valid until it is no longer needed, and object URLs are released on departure.
The rendered video remains the master clock. When the browser reports a finite
duration substantially shorter than the confirmed block boundary, playback stops
with an error. If the browser cannot report a finite duration, playback uses the
server-confirmed block boundary without inferring truncation from the last frame.

Block replay uses actual media time as its master clock, aligns the exact patient
audio before playback and pauses synchronized media while required sources buffer.
Missing sources never generate synthetic elapsed time. Playback failures remain
visible and retryable. These presentation rules do not alter recorded windows,
encoded duration, extraction or evaluation.

## Preservation

`PUT /medical-interviews/{id}/recording/blocks/{blockId}` accepts multipart `file` and JSON `metadata`, with `X-Capture-Segment` and, during authorized recovery, `X-Resume-Attempt`.

Transfer and encoded timing inspection occur outside conversation locks. Publication revalidates capture ownership and commits immutable content/metadata hashes and durable turn jobs together. Identical retries return the existing receipt. Conflicting IDs, orders, messages and stale captures are rejected. Existing two-second capture lock waits apply.

Incomplete originals are preserved. Encoded duration remains null when unavailable. Unreliable alignment disables analysis windows and synchronized audio instead of inventing timing or dropping originals. Text remains available. Invalid metadata, wrong owners and conflicting content remain errors.

OPFS writes finish before fragment counts/boundaries commit to IndexedDB. WebKit without `createWritable` uses a dedicated worker's `createSyncAccessHandle`. Fragments are recovery data, never individual uploads. One queue per account/interview sends closed blocks. Only preservation acknowledgement or the existing retention deadline permits deleting local copies.

Transient delivery failures repeat the immutable request for the same consumer, including truncated response bodies. Private per-interview connectivity subscriptions pause only affected capture/clock on connection loss. Brief HTTP contention does not pause conversation. Account/capture changes never transfer write authority.

## Completion and recovery

Interview detail responses include a derived `lifecycle` projection. It exposes `phase`, owner-scoped `can_resume_capture`, `can_complete`, `can_retry_completion`, a safe failure code and recording transport. It is not another persisted status and does not bypass endpoint authorization. It remains available while assessments are blinded.

`capture_finalized` means the immutable block manifest is confirmed but `/complete` has not yet been accepted. Reopening that interview offers continuation of completion instead of capture resumption. The owner can continue without an active recorder/header only after block finalization; supplied stale capture headers are still rejected. A `processing` session URL resolves directly to review. Failed block jobs are retried from the verified original and source identity, without requiring a separate clip.

Opening hypotheses stops and discards only an unsent intervention locally, without sealing remotely or waiting for uploads. Cancellation starts a new block using unchanged geometry.

Starting a block attempt compares capture geometry with its signed calibration. Changes in geometry, track identity/availability or page visibility pause capture and require session recovery/recalibration. Cancelling hypotheses checks device identity as well as geometry before restarting. Connectivity recovery cannot clear a storage/device/calibration block. Startup retries retain the same server grant/request; failed local startup never permits patient playback before capture is ready.

`POST /recording/blocks/finalize` verifies `block_ids` and explicit `missing_message_ids`, freezes the recording and schedules the existing pipeline without waiting for extraction/evaluation. Existing hypothesis/completion endpoints then mark processing. Official duration sums confirmed encoded blocks, including recorded technical wait, excluding dialogs/calibration/preparation.

Reload recovery uses a server-authorized resume attempt, reconciles message keys, submits recoverable originals and records gaps through `POST /recording/blocks/recovery`. Incomplete copies remain locally until retention. Recalibration is still required. A pending patient message is replayed without a new conversation message. Forced completion bounds recovery uploads, records missing evidence and works without active recorders.

Recovery initiated in a live tab first stops MediaRecorder and awaits its final local writes without discarding the original. Message reconciliation pages beyond the first 100 entries using `/messages?offset=N`. Playback windows and missing-audio flags use the same durable boundary. A transcript that finishes during a network pause is held until capture recovers; converting its historical timestamps subtracts only pauses preceding those timestamps. Repeated stops cannot advance the frozen clock.

Forced recovery and abandonment share a 30-second network cancellation budget; uploads additionally retain their five-second recovery budget. Cancellation preserves unacknowledged local originals. This network bound does not establish a hardware/OPFS flush deadline or physical crash durability.

## Analysis and recap

The turn worker reads the original. Student audio ends at the measured speech boundary, preserving internal pauses. Visual context keeps existing one-second margins. Reaction analysis uses patient playback windows with the attempt's calibration/region. Source, methodology and runtime identity guard cached results. Superseded jobs cannot overwrite recovery replacements. Final evaluation retains the full conversation, rubric, text-only baseline and unavailable-evidence policy.

Recap returns ordered blocks with cumulative confirmed offsets. Playback uses the original camera/microphone file and exact preserved patient MP3; microphone playback is muted outside student speech. No continuous file is uploaded/assembled. Legacy contracts remain available. Originals and MP3s remain inside the recording's existing private retention/deletion directory.

## Qualification limits

Docker checks cover synthetic originals, greeting plus three exchanges, ten concurrent preservations/closures, idempotence, stale captures, incomplete evidence, analysis windows, storage failures, pause timing, slow uploads and playback offsets. This bounded scenario is not unlimited capacity.

Physical Safari/Brave iPad qualification remains required: sound, prolonged synchronization, suspension, reload at each stage and local storage. Mocks/synthetic signals do not validate hardware latency or gaze accuracy.
