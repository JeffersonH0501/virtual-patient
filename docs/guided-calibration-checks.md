# Visual calibration and guided checks

## Continuing without gaze evidence

After the first calibration quality failure, the participant must retry. From
the second distinct retained failed capture in the current preparation, the UI
also offers **Continue without gaze evidence**. Retransmitting an original and
processing errors do not count as additional failed calibration attempts.

`POST /calibration/without-gaze/{interview_id}` verifies ownership, lifecycle,
the retained failures and current stable geometry. It saves `status=without_gaze`,
version `multimodal_without_gaze_v1`, capture geometry and `failed_capture_ids`,
without an affine gaze profile or a fabricated baseline. A resume authorization
applies only to the new segment. Gaze orientation metrics and its integrated
label remain unavailable; the evaluator receives no gaze evidence. Audio, smile
and nod processing retain their independent quality rules. Unavailable gaze is
not negative performance.

Continuing preserves calibration originals and diagnostics for the existing
private administrator viewer. Started interviews keep the existing retention
and explicit deletion policy. Abandoned unstarted preparations still follow
the existing discard and expiry rules. This option does not validate gaze
estimation without calibration.

## Calibrated gaze

The official calibration uses MediaPipe eye-local iris geometry and openness, sampling video at up to 15 frames per second.
Both eyes must have a geometric openness ratio of at least 0.10 (previously
0.20). Two eyes below this cutoff are classified as closed; a single eye below
it makes the observation unavailable. This operational cutoff also applies to
per-turn MediaPipe gaze extraction and is not a validated clinical threshold.
Existing calibration results and interview evidence retain their original
values until explicitly reprocessed.
Guided face, gaze and smile coverage uses the configured sampling rate, capped by the source frame rate; missing samples reduce coverage. Previously saved diagnostic results keep their original calculation until reprocessed.
The browser presents five points (center and four corners) for three seconds
each, followed by a five-second camera reference. It excludes the first 250 ms
of each target from analysis. Stable viewport and camera geometry, private
capture storage, server-signed checkpoints and authenticated access remain
required. The supported setup is an upright laptop with a top-center camera.

The gaze gate requires all five targets, at least 50% valid samples and 300 ms
of valid support per target, at least 80% valid face and usable-image coverage,
stable geometry and a nondegenerate affine fit. Leave-one-target-out
median/P90 normalized errors must be at most 0.35/0.50
(`mediapipe_five_point_quality_v3`, previously 0.25/0.35 in v2). The camera gate requires
at least 1000 ms of valid support and at least 80% valid ocular/head coverage in
the ending segment. Raw eye-coordinate P90 dispersion must be at most 0.04;
the operational lens radius is bounded between 0.01 and 0.04 eye widths.

Per-turn gaze is classified relative to the calibrated camera and the
timestamped interaction area. With a calibration profile, an image passing the existing quality checks and two geometrically closed eyes, or a nonuniform usable image without a detected face, count as outside interaction and retain separate reasons. Ambiguous eyes and unusable images remain unavailable. The rules do not establish that a person is absent or inattentive and require local validation.
Smile uses MediaPipe blendshapes; head nods use CCDb-HG. These observations
do not directly measure empathy, attention or another psychological state.

A superuser can run the temporary nonverbal test without creating an interview.
It requires the official calibration checkpoints to pass, then analyzes a
separate prompted video and reports signal availability, smile activity and nod
counts. The browser retains the video and results only until the view is closed;
worker uploads use temporary files removed after processing. Prompt instructions
are not verified ground truth. The test does not authorize an interview.

The thresholds are operational, not clinical validation. Accuracy, device
transferability and correspondence with independently annotated recordings
remain open. Do not interpret screen-directed gaze as direct eye contact.
