# Client capture and completion contract

Fragment, message and turn-timing writes from one browser share an ordered queue
per interview. This prevents the browser's own requests competing for the same
transaction lock. Fragment file storage runs outside the interview transaction;
the server reacquires the lock and revalidates ownership, epoch, index, digest
and quota before publishing. A concurrent resume cannot restore an old writer.
Transport errors remain visible; the queue does not turn data conflicts into
automatic short-delay retries. Successful turn persistence clears its stale warning.

An interview owns one recording with ordered capture segments. Each segment
stores its ID, sequence, active-time offset, confirmed duration, available media,
capture configuration and verified calibration. Turns keep their IDs, message
association and global order, and reference the segment that captured them.
Legacy recordings remain readable without segment rows. Resuming legacy capture
imports it into one sealed segment before appending a new one.

Reentry offers Resume and Force termination. Resume preserves the same interview
and transcript, seals the previous segment, and requires fresh gaze calibration
and a camera reference authorized by the current resume attempt. Calibration
does not start the interview clock. A server patient reply not yet delivered is
played again from its existing message; it is never regenerated as a new turn.
Unsent student speech must be repeated. Forced interruption can close the server
record even when reload left no active recorders or recoverable local media.

The calibration screen binds its existing microphone/camera streams to the
newly created interview before navigating. The media provider retains those
exact streams for the handoff and releases them on other interview changes.
This preserves device identity, not evidence of empirical calibration accuracy.

## Timing and acceptance

Each capture segment uses a compensated `performance.now` origin; the counter
adds its elapsed time to the preceding sealed segments. Four continuous sources,
provisional STT timing and measured TTS playback timing remain in use. Completion
is blocked during STT submission, generation and patient delivery, including
keyboard events and repeated clicks before React renders. Audio failure keeps
the patient turn pending until explicit continuation with the written reply.
Opening completion discards unsent input, stops all four recorders and seals at
the last confirmed turn. Server trimming removes their unconfirmed tails.

Stopping capture freezes its duration before network waits. Retry uses the
same files, source durations, turn timestamps, message IDs and ROI offsets.
The server derives duration from sealed boundaries, excluding dialog and
recalibration waits. Start and end dates remain historical timestamps. Migration
008 corrects existing durations using a confirmed recording first, then the last
saved turn, otherwise NULL. History and review never substitute elapsed calendar
time or an encoded unconfirmed tail. Unknown durations are displayed as unavailable.

Patient ROI samples carry normalized viewport coordinates and an ordered
timestamp. Turn uploads use elapsed milliseconds within the turn. Final
uploads use elapsed milliseconds within the capture segment. The API rejects
invalid snapshots before media is persisted. Invalid historical snapshots
leave alignment evidence unavailable while retaining the original metadata.

The API caps each full recording video at 512 MiB, each full recording audio
file at 64 MiB, and each turn video at 64 MiB. The production proxy caps the
corresponding multipart requests at 1156 MiB and 68 MiB. Uploads over the
limit receive HTTP 413. Failed writes discard temporary and uncommitted files.
When a commit outcome cannot be verified, files remain eligible for the
recording's server-side retention purge.

Empty STT and encoding with no utterance chunks produce a recoverable
`transcription-empty` outcome, not invented text. A provider generation guard
ignores results/errors after stop or disposal. A separate playback generation
guard prevents late TTS requests from playing after the transcript unmounts.
The speech-detection constants and evaluation algorithms are unchanged.
Stopping input discards an unsubmitted phrase without announcing a committed
utterance; submission remains the explicit acceptance step.

## Retry and interrupted media

Pending turn operations remain queued on failure. A successful PUT by message
ID is retained while its POST by turn ID retries with the original clip bytes
and ROI snapshots. A lost PUT response may repeat the same idempotent request.
Continuous upload proceeds if the turn queue fails or does not drain within 15 seconds; preservation metadata records the pending count. Concurrent
finalization callers share one attempt and outcome. Recorder failures remain
explicit technical failures rather than valid empty observations.

Opening hypotheses seals capture and retains its media locally without uploading
or transcoding it. The saving message is shown only after submitting hypotheses.
Cancel waits only for the capture boundary and local preservation, then starts another
segment from the confirmed endpoint and reuses calibration only if camera
identity and capture geometry are unchanged; otherwise it enters recalibration.
Confirmed hypotheses are not posted again when media upload or completion fails.
Final submission uploads all retained segments before finalizing the recording.
Deferred uploads carry the latest capture ID, so an old tab cannot supply them.
Resume recovery lists all sealed segments, including earlier cancelled dialogs.
Current-page interruption preserves available media before closing. Reentry
interruption attempts recovery and can still close when local media is lost.

The `/recording/resume`, `/recording/segments`, segment `/seal` and `/media`
operations are idempotent. Turn, clip and lifecycle mutations validate the current
capture: `X-Capture-Segment` for hypothesis/finalize/complete/current-page abandon,
and `X-Resume-Attempt` for abandon during recalibration. Resume calibration and
recovered-media uploads carry the authorized attempt ID. Old tabs cannot replace
confirmed media, add late turns or close a newly resumed capture.

OPFS stores each delivered chunk with an independent committed writer, per source
and segment under `virtual-patient-recordings`. Recovery rejects missing chunk
indices and uploads available files with saved ROI/geometry. The server validates
decodability and coverage; invalid/incomplete sources remain explicitly unavailable.
Only sources acknowledged as preserved are removed locally. Unacknowledged bytes
remain for retry until the server-provided retention deadline; capture startup
and recovery purge expired checkpoints. Purging cannot run while the browser app is closed.
The memory fallback supports submission only while the page remains open.
Pre-segment browser `.part` files lack reliable segment/checkpoint metadata and
are not automatically imported or erased; this does not affect server legacy replay.

This is not crash-proof storage: a tab/process/OS crash may prevent asynchronous
flush, OPFS commits can fail, the final recorder interval may be lost, and the
memory fallback does not survive navigation. Do not claim all media survived an
abrupt browser exit. No participant media is exported by tests or written to
the repository.

## Verification boundary

Co-located Vitest tests exercise real hooks/providers/orchestration with
controlled network promises, recorder events and browser device mocks.
They cover delayed final chunks, nonempty ROI offsets, duplicate events,
empty/error/cancelled STT, stopped-capture retry and stream ownership. These
tests do not establish camera/microphone hardware behavior, audiovisual drift,
cross-browser codec correctness or clinical validity.

Backend regression, native trimming fixtures, migration checks and UI tests run
inside the existing Docker services. No dependencies, scientific thresholds,
evaluation labels or native process boundaries change. Physical iPad reload,
capture, codec and OPFS behavior remains unqualified by these controlled tests.

## Interrupted media preservation

Forced termination stays on the capture screen until the server acknowledges the
available continuous files. Upload failures and the five-minute upload timeout
permit retry using the same files and frozen metadata. Missing local sources are
recorded in `unavailableSources`; their buffers are retained. Pending turn writes
and capture errors are recorded under `preservation`.

Review presents one active timeline, seeking each source in local segment time.
The pipeline processes each segment with its own calibration and patient ROI.
Normal completion evaluates the full transcript with available evidence; missing
media retains text and explicit unavailable observations. Forced interruption
does not request communication evaluation.

Raw turn clips retain their storage keys after successful processing, failure,
and interruption. Confirmed media is removed only by explicit deletion or the
existing retention policy (at most 12 calendar months). Interrupted-interview
reprocessing and evaluation remain outside this change. Identical finalized
uploads remain idempotent; different files cannot replace confirmed media.
## Upload scheduling and iPad playback

Capture uploads preserve order within each source while allowing independent
sources to upload concurrently. Only acknowledged fragments leave the pending
queue; a failed acknowledgement retries the same source/index and bytes. Capture,
hypothesis and completion HTTP requests have bounded network waits; a timeout
does not authorize deleting local recovery media. Final source assembly retains
its existing five-minute deadline and idempotent server validation.

On iPad, the prepared native audio element provides audible patient playback;
decoded audio feeds only the recording destination, starting at the element's
actual playback offset. Physical-device audibility and long-duration drift still
require hardware verification.

## Private replay posters

`GET /medical-interviews/{id}/recording/assets/{asset_kind}/poster` accepts only
student_video and patient_video. It applies the same authenticated replay access,
organization/assignment checks, lifecycle gate and ready-asset lookup as streaming.
The existing API image's FFmpeg decodes one frame into a JPEG in memory, with one
thread per codec, a 640px width limit, local-file protocols and a 15-second timeout.
Responses are private/no-store; generated images are never persisted. No original
is changed or deleted, so explicit deletion and maximum 12-month retention remain
the existing media contract. Missing sources return 404; decode failures return 503.
Posters do not move the synchronized player clock or start playback.
