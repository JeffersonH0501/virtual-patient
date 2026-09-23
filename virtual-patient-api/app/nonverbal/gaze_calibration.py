"""Versioned affine gaze calibration, quality, semantics, and time aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Sequence

import numpy as np

from app.models.calibration import CalibrationCaptureMetadata, GazeCalibrationMetadata
from app.nonverbal.gaze import GazeObservation

ALGORITHM_VERSION = "webeyetrack_affine_2x3_v1"
QUALITY_VERSION = "operational_calibration_quality_v1"
WEBEYETRACK_COMMIT = "75fbd2f5f784f2eb3a39675a8dcbf1b01c697f1c"
BLAZEGAZE_SHA256 = "5b011cfe82466896e27b1ac3e18130117cafbc02dbc964a1ad7315f62005cc05"
MIN_TARGET_VALID_RATIO = .50
MIN_FACE_VALID_RATIO = .80
MIN_TARGET_VALID_MS = 300.0
MAX_MEDIAN_ERROR = .15
MAX_P90_ERROR = .30
MIN_CAMERA_VALID_MS = 1000.0
MIN_SPEECH_VALID_MS = 3000
CAMERA_RADIUS_NORMALIZED = .12
PATIENT_MARGIN_RATIO = .10
DWELL_GAP_TOLERANCE_MS = 150.0
MAX_CALIBRATION_SAMPLE_GAP_MS = 150.0


def build_gaze_profile(observations: Sequence[GazeObservation], metadata: GazeCalibrationMetadata, *, face_valid_ratio: float) -> tuple[dict, dict, bool, str | None]:
    """Fit and validate the nine-point gaze checkpoint independently."""
    source, target, ids, target_quality = [], [], [], {}
    for item in metadata.targets:
        samples = [obs for obs in observations if item.observation_window_start_ms <= obs.timestamp_ms < item.observation_window_end_ms]
        valid = [obs for obs in samples if obs.valid and obs.unclipped_x is not None and obs.unclipped_y is not None]
        duration = _valid_duration(valid, item.observation_window_start_ms, item.observation_window_end_ms)
        ratio = len(valid) / len(samples) if samples else 0.0
        target_quality[item.target_id] = {"valid_ratio": ratio, "valid_duration_ms": duration, "valid_samples": len(valid)}
        for obs in valid:
            source.append([obs.unclipped_x, obs.unclipped_y])
            target.append([item.target_normalized_x, item.target_normalized_y])
            ids.append(item.target_id)
    if len(source) < 4:
        return {}, {"targets": target_quality}, False, "insufficient_gaze_samples"
    source_np, target_np = np.asarray(source), np.asarray(target)
    matrix = fit_affine(source_np, target_np)
    geometry = metadata.geometry
    errors = normalized_errors(apply_affine(source_np, matrix), target_np, geometry.viewport_width, geometry.viewport_height)
    quality = {
        "version": QUALITY_VERSION,
        "face_valid_ratio": face_valid_ratio,
        "targets": target_quality,
        "covered_targets": sum(v["valid_ratio"] >= MIN_TARGET_VALID_RATIO and v["valid_duration_ms"] >= MIN_TARGET_VALID_MS for v in target_quality.values()),
        "affine_fit_median_normalized_error": float(np.median(errors)),
        "affine_fit_p90_normalized_error": float(np.percentile(errors, 90)),
        "leave_one_target_out": leave_one_target_out_error(source_np, target_np, ids, geometry.viewport_width, geometry.viewport_height),
        "geometry_stable": metadata.geometry_stable,
    }
    checks = {
        "targets": quality["covered_targets"] == 9,
        "face": face_valid_ratio >= MIN_FACE_VALID_RATIO,
        "median_error": quality["affine_fit_median_normalized_error"] <= MAX_MEDIAN_ERROR,
        "p90_error": quality["affine_fit_p90_normalized_error"] <= MAX_P90_ERROR,
        "geometry": metadata.geometry_stable,
    }
    reason = next((name for name, passed in checks.items() if not passed), None)
    profile = {
        "algorithm": ALGORITHM_VERSION,
        "affine_matrix": matrix.tolist(),
        "webeyetrack_commit": WEBEYETRACK_COMMIT,
        "blazegaze_sha256": BLAZEGAZE_SHA256,
        "camera_radius_normalized": CAMERA_RADIUS_NORMALIZED,
    }
    return profile, quality, reason is None, reason


def fit_affine(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Official WebEyeTrack least-squares affine mapping, without MAML steps."""
    source = np.asarray(source, dtype=float)
    target = np.asarray(target, dtype=float)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 2 or len(source) < 4:
        raise ValueError("Affine calibration requires at least four paired 2D samples")
    matrix = np.linalg.lstsq(np.column_stack((source, np.ones(len(source)))), target, rcond=None)[0].T
    if matrix.shape != (2, 3) or not np.isfinite(matrix).all():
        raise ValueError("Invalid affine calibration profile")
    return matrix


def apply_affine(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    matrix = np.asarray(matrix, dtype=float)
    if matrix.shape != (2, 3) or not np.isfinite(matrix).all():
        raise ValueError("Affine profile must be finite and 2x3")
    return np.column_stack((points, np.ones(len(points)))) @ matrix.T


def normalized_errors(predictions: np.ndarray, targets: np.ndarray, width: int, height: int) -> np.ndarray:
    """Compute CSS-pixel error divided by the CSS viewport diagonal."""
    predictions_px = np.asarray(predictions, dtype=float) * [width, height]
    targets_px = np.asarray(targets, dtype=float) * [width, height]
    return np.linalg.norm(predictions_px - targets_px, axis=1) / hypot(width, height)


def leave_one_target_out_error(source: np.ndarray, target: np.ndarray, target_ids: Sequence[str], width: int, height: int) -> dict:
    errors = []
    ids = np.asarray(target_ids)
    for target_id in dict.fromkeys(target_ids):
        train = ids != target_id
        test = ~train
        if train.sum() < 4:
            continue
        matrix = fit_affine(source[train], target[train])
        errors.extend(normalized_errors(apply_affine(source[test], matrix), target[test], width, height))
    return {"median_normalized_error": float(np.median(errors)), "p90_normalized_error": float(np.percentile(errors, 90))} if errors else {}


def _valid_duration(observations: Sequence[GazeObservation], start: int, end: int) -> float:
    times = sorted(item.timestamp_ms for item in observations if item.valid and start <= item.timestamp_ms < end)
    if len(times) < 2:
        return 0.0
    return float(sum(min(times[i + 1] - times[i], MAX_CALIBRATION_SAMPLE_GAP_MS) for i in range(len(times) - 1)))


def build_profile(observations: Sequence[GazeObservation], metadata: CalibrationCaptureMetadata, *, face_valid_ratio: float, voiced_duration_ms: int, clipping: bool) -> tuple[dict, dict, bool, str | None]:
    source, target, ids, target_quality = [], [], [], {}
    for item in metadata.targets:
        samples = [obs for obs in observations if item.observation_window_start_ms <= obs.timestamp_ms < item.observation_window_end_ms]
        valid = [obs for obs in samples if obs.valid and obs.unclipped_x is not None and obs.unclipped_y is not None]
        duration = _valid_duration(valid, item.observation_window_start_ms, item.observation_window_end_ms)
        ratio = len(valid) / len(samples) if samples else 0.0
        target_quality[item.target_id] = {"valid_ratio": ratio, "valid_duration_ms": duration, "valid_samples": len(valid)}
        for obs in valid:
            source.append([obs.unclipped_x, obs.unclipped_y]); target.append([item.target_normalized_x, item.target_normalized_y]); ids.append(item.target_id)
    if len(source) < 4:
        return {}, {"targets": target_quality}, False, "insufficient_gaze_samples"
    source_np, target_np = np.asarray(source), np.asarray(target)
    matrix = fit_affine(source_np, target_np)
    calibrated = apply_affine(source_np, matrix)
    geometry = metadata.geometry
    errors = normalized_errors(calibrated, target_np, geometry.viewport_width, geometry.viewport_height)
    camera_samples = [obs for obs in observations if obs.valid and metadata.camera_reference_start_ms <= obs.timestamp_ms < metadata.camera_reference_end_ms and obs.unclipped_x is not None]
    camera_calibrated = apply_affine(np.asarray([[obs.unclipped_x, obs.unclipped_y] for obs in camera_samples]), matrix) if camera_samples else np.empty((0, 2))
    camera_ms = _valid_duration(camera_samples, metadata.camera_reference_start_ms, metadata.camera_reference_end_ms)
    quality = {
        "version": QUALITY_VERSION, "face_valid_ratio": face_valid_ratio, "targets": target_quality,
        "covered_targets": sum(v["valid_ratio"] >= MIN_TARGET_VALID_RATIO and v["valid_duration_ms"] >= MIN_TARGET_VALID_MS for v in target_quality.values()),
        "affine_fit_median_normalized_error": float(np.median(errors)),
        "affine_fit_p90_normalized_error": float(np.percentile(errors, 90)),
        "leave_one_target_out": leave_one_target_out_error(source_np, target_np, ids, geometry.viewport_width, geometry.viewport_height),
        "camera_valid_duration_ms": camera_ms, "valid_speech_duration_ms": voiced_duration_ms,
        "clipping_detected": clipping, "geometry_stable": metadata.geometry_stable,
    }
    checks = {
        "targets": quality["covered_targets"] == 9, "face": face_valid_ratio >= MIN_FACE_VALID_RATIO,
        "median_error": quality["affine_fit_median_normalized_error"] <= MAX_MEDIAN_ERROR,
        "p90_error": quality["affine_fit_p90_normalized_error"] <= MAX_P90_ERROR,
        "camera": camera_ms >= MIN_CAMERA_VALID_MS, "speech": voiced_duration_ms >= MIN_SPEECH_VALID_MS,
        "clipping": not clipping, "geometry": metadata.geometry_stable,
    }
    reason = next((name for name, passed in checks.items() if not passed), None)
    profile = {
        "algorithm": ALGORITHM_VERSION, "affine_matrix": matrix.tolist(), "webeyetrack_commit": WEBEYETRACK_COMMIT,
        "blazegaze_sha256": BLAZEGAZE_SHA256,
        "camera_reference_center": np.median(camera_calibrated, axis=0).tolist() if len(camera_calibrated) else None,
        "camera_radius_normalized": CAMERA_RADIUS_NORMALIZED,
    }
    return profile, quality, reason is None, reason


def classify_gaze(point: tuple[float, float] | None, profile: dict | None, patient_roi: dict | None) -> str:
    if point is None or profile is None:
        return "UNAVAILABLE"
    x, y = point
    camera = profile.get("camera_reference_center")
    if camera and hypot(x - camera[0], y - camera[1]) <= profile.get("camera_radius_normalized", CAMERA_RADIUS_NORMALIZED):
        return "CAMERA"
    if 0 <= x <= 1 and 0 <= y <= 1:
        if patient_roi:
            margin_x = patient_roi["width_normalized"] * PATIENT_MARGIN_RATIO
            margin_y = patient_roi["height_normalized"] * PATIENT_MARGIN_RATIO
            if patient_roi["x_normalized"] - margin_x <= x <= patient_roi["x_normalized"] + patient_roi["width_normalized"] + margin_x and patient_roi["y_normalized"] - margin_y <= y <= patient_roi["y_normalized"] + patient_roi["height_normalized"] + margin_y:
                return "PATIENT"
        return "OTHER_INTERFACE"
    return "AWAY_OR_OUTSIDE"
