"""Backend-only BlazeGaze inference over shared MediaPipe observations.

The adapter follows WebEyeTrack commit 75fbd2f5f784f2eb3a39675a8dcbf1b01c697f1c
and deliberately calls ``step`` with existing landmarks and pose. It never calls
WebEyeTrack's ``process_frame`` and therefore never runs a second Face Landmarker.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import sys

import numpy as np

from app.nonverbal.shared_observations import SharedFrameObservation

MODEL_PATH = Path(__file__).with_name("models") / "blazegaze_mpiifacegaze.keras"
CALIBRATION_STATE = "identity_calibration"
ALIGNMENT_UNAVAILABLE_REASON = "gaze_calibration_pending"


def _ensure_upstream_import_compatibility() -> None:
    """Bridge WebEyeTrack's legacy import to the pinned MediaPipe package."""
    import mediapipe

    sys.modules.setdefault("mediapipe.python", mediapipe)


@dataclass(frozen=True)
class GazeObservation:
    timestamp_ms: float
    valid: bool
    state: str
    unclipped_x: float | None = None
    unclipped_y: float | None = None
    display_x: float | None = None
    display_y: float | None = None


def create_tracker(*, affine_matrix: Any | None = None, kalman_enabled: bool = True) -> Any:
    """Create WebEyeTrack without constructing its private Face Landmarker."""
    _ensure_upstream_import_compatibility()
    from webeyetrack.blazegaze import BlazeGaze, BlazeGazeConfig
    from webeyetrack.filter import KalmanFilter2D
    from webeyetrack.webeyetrack import WebEyeTrack, WebEyeTrackConfig

    tracker = WebEyeTrack.__new__(WebEyeTrack)
    tracker.config = WebEyeTrackConfig(blazegaze_mlp_fp=MODEL_PATH)
    tracker.blazegaze = BlazeGaze(BlazeGazeConfig(weights_fp=MODEL_PATH))
    tracker.kalman_filter = KalmanFilter2D(
        dt=tracker.config.kalman_config.dt,
        process_noise=tracker.config.kalman_config.process_noise,
        measurement_noise=tracker.config.kalman_config.measurement_noise,
    )
    tracker.config.kalman_config.enabled = kalman_enabled
    tracker.face_width_cm = None
    tracker.intrinsics = None
    tracker.affine_matrix = None if affine_matrix is None else np.asarray(affine_matrix, dtype=float)
    if tracker.affine_matrix is not None and (
        tracker.affine_matrix.shape != (2, 3) or not np.isfinite(tracker.affine_matrix).all()
    ):
        raise ValueError("WebEyeTrack affine profile must be a finite 2x3 matrix")
    return tracker


def _landmarks_array(landmarks: Any) -> np.ndarray:
    return np.asarray(
        [[point.x, point.y, point.z, getattr(point, "visibility", 0.0) or 0.0,
          getattr(point, "presence", 0.0) or 0.0] for point in landmarks],
        dtype=np.float32,
    )


def extract_gaze(observation: SharedFrameObservation, tracker: Any, timings: dict[str, list[float]] | None = None) -> GazeObservation:
    if not observation.face_valid:
        return GazeObservation(observation.timestamp_ms, False, "face_unavailable")
    if observation.facial_transformation_matrix is None:
        return GazeObservation(observation.timestamp_ms, False, "pose_unavailable")

    _ensure_upstream_import_compatibility()
    from webeyetrack.data_protocols import TrackingStatus

    tracker_args = (
        observation.frame,
        _landmarks_array(observation.landmarks),
        np.asarray(observation.facial_transformation_matrix, dtype=np.float32),
    )
    upstream_durations: dict[str, float] = {}
    status, result = (
        tracker.step(*tracker_args, durations=upstream_durations)
        if timings is not None
        else tracker.step(*tracker_args)
    )
    if timings is not None:
        for name, seconds in upstream_durations.items():
            timings.setdefault(f"webeyetrack_{name.replace('&', 'and')}", []).append(float(seconds) * 1000)
    if status != TrackingStatus.SUCCESS or result is None:
        return GazeObservation(observation.timestamp_ms, False, "inference_failed")
    if result.gaze_state != "open":
        return GazeObservation(observation.timestamp_ms, False, "eyes_closed")

    point = np.asarray(result.norm_pog, dtype=float).reshape(2)
    if not np.isfinite(point).all():
        return GazeObservation(observation.timestamp_ms, False, "non_finite_output")
    x, y = float(point[0]), float(point[1])
    return GazeObservation(
        observation.timestamp_ms, True, CALIBRATION_STATE, x, y,
        float(np.clip(x, -0.5, 0.5)), float(np.clip(y, -0.5, 0.5)),
    )


def visual_alignment_unavailable() -> dict[str, str | None]:
    """Keep alignment metrics unavailable until participant calibration exists."""
    return {
        "visual_alignment_ratio": None,
        "visual_alignment_mean": None,
        "reason": ALIGNMENT_UNAVAILABLE_REASON,
    }
