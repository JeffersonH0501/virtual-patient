"""Operational constants for the multimodal pipeline."""

# Frames retain image and landmark arrays while waiting for gaze inference.
# Eight keeps the MediaPipe producer usefully ahead without accumulating the
# memory footprint of 32 full-resolution observations.
NONVERBAL_GAZE_QUEUE_CAPACITY = 8

# Keep the isolated visual stack warm between interview turns, then release its
# native memory when no more work arrives. The API process never imports the ML
# stack itself.
TURN_VIDEO_WORKER_IDLE_TIMEOUT_SECONDS = 300.0
TURN_VIDEO_JOB_TIMEOUT_SECONDS = 900.0
CALIBRATION_VISUAL_JOB_TIMEOUT_SECONDS = 180.0
