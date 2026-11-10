"""Ocular calibration requires valid and separable MediaPipe observations."""
from dataclasses import replace

from app.nonverbal.guided_eye_geometry import build_eye_geometry_reference
from app.nonverbal.tests.test_independent_mediapipe import calibration


def test_five_target_geometry_has_held_out_quality():
    observations, metadata = calibration()
    reference = build_eye_geometry_reference(observations, metadata, max_median_error=.25, max_p90_error=.35)
    assert reference["status"] == "ready"
    assert reference["quality"]["p90_normalized_error"] < 1e-10
    assert len(reference["target_samples"]) == 5


def test_missing_target_coverage_is_unavailable():
    observations, metadata = calibration()
    assert build_eye_geometry_reference(observations[30:], metadata)["status"] == "unavailable"


def test_missing_frame_timestamps_are_unavailable():
    observations, metadata = calibration()
    observations[0] = replace(observations[0], shared=replace(observations[0].shared, timestamp_ms=None))
    assert build_eye_geometry_reference(observations, metadata)["reason"] == "missing_frame_timestamps"
