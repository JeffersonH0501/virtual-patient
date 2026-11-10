# Calibration reference implementation plan

Preserve every uploaded calibration capture with its metadata and worker outcome.
Reuse private interview media storage, authenticated replay, interview deletion,
and the existing maximum twelve-calendar-month retention policy. Only authorized
superusers may inspect captures; the signed accepted checkpoints identify which
captures supplied the interview profile. Existing interviews have no invented media.

1. Add a capture model/migration and persistence around `calibration/process-stage`.
   Deduplicate identical uploads, preserve worker failures, enforce owner/pre-start
   access, and link capture IDs through signed checkpoints.
2. Add superuser-only listing/replay below `/medical-interviews`, using existing
   organization access and byte-range streaming. Extend expiry and deletion tests.
3. Add a lazy-loaded calibration dialog in the review profile header, with video,
   selected-checkpoint markers, outcomes and full structured diagnostics.
4. Test upload retries/failures/access/retention and UI loading/results/errors in
   existing Docker services. Apply the additive migration and update the documented
   media contract and thesis description without changing scientific thresholds.
