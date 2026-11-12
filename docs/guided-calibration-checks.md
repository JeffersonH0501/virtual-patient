# Visual calibration and guided checks

The official calibration uses MediaPipe eye-local iris geometry and openness, sampling video at up to 15 frames per second.
Guided face, gaze and smile coverage uses the configured sampling rate, capped by the source frame rate; missing samples reduce coverage. Previously saved diagnostic results keep their original calculation until reprocessed.
The browser presents five points (center and four corners) for three seconds
each, followed by a five-second camera reference. It excludes the first 250 ms
of each target from analysis. Stable viewport and camera geometry, private
capture storage, server-signed checkpoints and authenticated access remain
required. The supported setup is an upright laptop with a top-center camera.

The gaze gate requires all five targets, at least 50% valid samples and 300 ms
of valid support per target, at least 80% valid face and usable-image coverage,
stable geometry and a nondegenerate affine fit. Leave-one-target-out
median/P90 normalized errors must be at most 0.25/0.35. The camera gate requires
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
