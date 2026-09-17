from types import SimpleNamespace

import numpy as np

from app.models.calibration import CalibrationCaptureMetadata
from app.nonverbal.gaze_calibration import apply_affine, build_profile, classify_gaze, fit_affine


def test_affine_fit_recovers_known_mapping():
    source = np.asarray([[0, 0], [1, 0], [0, 1], [1, 1], [.5, .5]], dtype=float)
    expected = np.asarray([[.8, .1, .05], [-.05, .9, .1]])
    target = apply_affine(source, expected)
    assert np.allclose(fit_affine(source, target), expected)


def test_semantic_gaze_states_use_calibration_and_dynamic_patient_roi():
    profile = {"camera_reference_center": [.5, .1], "camera_radius_normalized": .08}
    roi = {"x_normalized": .25, "y_normalized": .25, "width_normalized": .3, "height_normalized": .4}
    assert classify_gaze((.5, .1), profile, roi) == "CAMERA"
    assert classify_gaze((.4, .4), profile, roi) == "PATIENT"
    assert classify_gaze((.9, .5), profile, roi) == "OTHER_INTERFACE"
    assert classify_gaze((1.2, .5), profile, roi) == "AWAY_OR_OUTSIDE"
    assert classify_gaze(None, profile, roi) == "UNAVAILABLE"


def test_quality_gate_requires_stable_geometry_and_all_targets():
    targets = []
    observations = []
    protocol = [("CENTER", .5, .5), ("TOP_LEFT", .1, .1), ("BOTTOM_RIGHT", .9, .9), ("TOP_RIGHT", .9, .1), ("BOTTOM_LEFT", .1, .9), ("TOP_CENTER", .5, .1), ("BOTTOM_CENTER", .5, .9), ("MIDDLE_LEFT", .1, .5), ("MIDDLE_RIGHT", .9, .5)]
    for index, (target_id, x, y) in enumerate(protocol):
        start = index * 1000
        targets.append({"target_id": target_id, "target_order": index + 1, "target_normalized_x": x, "target_normalized_y": y, "target_pixel_x": x * 1000, "target_pixel_y": y * 800, "presentation_start_ms": start, "presentation_end_ms": start + 900, "observation_window_start_ms": start, "observation_window_end_ms": start + 900})
        observations.extend(SimpleNamespace(timestamp_ms=start + offset, valid=True, unclipped_x=x, unclipped_y=y) for offset in range(0, 900, 50))
    observations.extend(SimpleNamespace(timestamp_ms=9500 + offset, valid=True, unclipped_x=.5, unclipped_y=.1) for offset in range(0, 1500, 50))
    metadata = CalibrationCaptureMetadata.model_validate({"geometry": {"viewport_width": 1000, "viewport_height": 800, "device_pixel_ratio": 1, "screen_width": 1000, "screen_height": 800, "orientation": "landscape", "video_width": 1280, "video_height": 720}, "targets": targets, "camera_reference_start_ms": 9500, "camera_reference_end_ms": 11000, "voice_baseline_start_ms": 11000, "voice_baseline_end_ms": 15000, "geometry_stable": False})
    _, quality, passed, reason = build_profile(observations, metadata, face_valid_ratio=1, voiced_duration_ms=4000, clipping=False)
    assert quality["covered_targets"] == 9
    assert passed is False
    assert reason == "geometry"
