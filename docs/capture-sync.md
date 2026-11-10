# Durable capture synchronization

Migration `009_capture_operations` adds operation receipts with a unique
`(interview_id, operation_id)` key and an immutable payload hash. Receipts and
turn, hypothesis, segment-boundary or completion changes commit together.

## Client ownership and recovery

`CaptureCoordinator` owns a durable control queue per authenticated account and
interview. IndexedDB stores operation identity, immutable payload, receipt and
retention deadline; OPFS stores the original recorder fragments. Network requests
use current authentication, never credentials copied into the journal. An account
change prevents replay. Expired journal entries follow the capture deadline.

`POST /medical-interviews/{id}/capture/sync` accepts `segment_id` and ordered
`operations` (`operation_id`, `kind`, `payload`). Kinds are `turn`, `hypotheses`,
`seal`, `media` and `finalize`. Responses include acknowledgements, authoritative
status and confirmed active boundary. Missing fragment responses include explicit
received/expected counts. Identical operations replay their original receipt;
changed contents conflict. Confirmed data from old epochs can be acknowledged
without admitting new writes. Stale pending operations remain locally recorded
as blocked, rather than being silently removed.

Messages use the existing idempotent message endpoint through the same durable
coordinator. Student timing and ROI are frozen before sending and commit with the
student/patient message pair. Reply generation claims the interview briefly,
releases its row lock during model generation, and revalidates the claim and
capture epoch before publishing. Resumption revokes an unfinished claim.

`GET /medical-interviews/{id}/capture/state` reconciles capture ownership before
reactivating a paused client. A stale tab must not restart its clock or capture.
Normal completion cannot seal past unconfirmed turns. Canceling hypotheses does
not delete pending operations. The four recorders pause while synchronization is
pending; native patient playback pauses with capture and restarts its recording
source at the audible element's actual playback offset.

## Isolation and bounded work

Control operations serialize within an interview. At most two fragment uploads
run concurrently per interview, including deferred segments; each source retains
its own index order. Other interviews have independent queues and upload slots.
Capture database work runs in request threads, with a two-second PostgreSQL lock
timeout and consistent interview-before-recording lock order. Transient contention
returns 503; stale capture and content conflicts return 409. Only transient
failures receive bounded exponential backoff, while the UI remains recoverable.
Transient recovery stays inside the original operation promise: a recovered
response reaches its original caller instead of leaving the screen in an error
state while a separate background task succeeds. Permanent validation and
ownership errors still reject; retry waits wake when connectivity returns.

The browser waits for recorder shutdown and committed local fragments without
reconstructing complete files for incremental capture. `media` confirms that the
declared fragment originals exist remotely, or records explicitly unavailable
sources. `finalize` accepts only sealed, preserved segments and saved hypotheses,
sets the interview to processing, records its active duration, and returns 202.
Local bytes may then be released after their source preservation acknowledgement;
normal completion does not wait for encoding or evaluation.

The existing durable job runner retains one global resource slot. Preservation
jobs precede analysis jobs; each class retains FIFO ordering. Preservation assembles
and validates sources outside HTTP transactions, then schedules the existing
pipeline and conversation evaluation. Replaying preservation does not duplicate
completion jobs. Failures retain source fragments and keep the interview out of
the active-capture lifecycle. The owner can retry the same failed preservation job
through `POST /medical-interviews/{id}/capture/preservation/retry`; review exposes
the existing retry control for this failure.

Legacy upload endpoints and recordings remain supported. TEXT_ONLY, calibration
requirements, the communication rubric and missing-evidence semantics are unchanged.

## Verification boundary

Docker tests cover ten isolated simultaneous interviews/four sources, response
loss, operation conflicts, short lock contention, live generation concurrent with
capture, partial evidence, worker replay, native playback capture offsets and
encoded four-source origins/durations. Synthetic load gates require confirmation
P95 below two seconds and closure acceptance below five seconds after preservation.
These are development-environment measurements, not a deployment capacity claim.
Safari/Brave iPad audibility, suspension and long-duration physical synchronization
still require device qualification.

The reply-generation regression test must retain an ORM segment instance while
other requests append fragments, then commit student timing. Revalidation refreshes
that instance before merging ROI metadata, preserving every acknowledged manifest
entry. A paused playback watchdog must not report unavailable audio merely because
capture synchronization intentionally stopped playback. On an explicit remote
prefix-gap conflict, the upload queue automatically restores the missing suffix
from committed OPFS fragments and their original timing before continuing. It
reconciles once per flush, preserves content-conflict rejection, and never invents
indices, bytes or timestamps. Users do not have a manual retry-saving control.
