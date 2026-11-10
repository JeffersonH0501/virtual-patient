"""Versioned affine gaze calibration, quality, semantics, and time aggregation."""

from __future__ import annotations

from math import hypot
from typing import Sequence

import numpy as np

from app.nonverbal.gaze import GazeObservation

MIN_TARGET_VALID_RATIO = .50
MIN_FACE_VALID_RATIO = .80
MIN_TARGET_VALID_MS = 300.0
MAX_MEDIAN_ERROR = .15
MAX_P90_ERROR = .30
MIN_CAMERA_VALID_MS = 1000.0
CAMERA_RADIUS_NORMALIZED = .12
PATIENT_MARGIN_RATIO = .10
DWELL_GAP_TOLERANCE_MS = 150.0
MAX_CALIBRATION_SAMPLE_GAP_MS = 150.0


def fit_affine(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Fit a finite least-squares affine mapping."""
    source = np.asarray(source, dtype=float)
    target = np.asarray(target, dtype=float)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 2 or len(source) < 4:
        raise ValueError("Affine calibration requires at least four paired 2D samples")
    design = np.column_stack((source, np.ones(len(source))))
    if not np.isfinite(source).all() or not np.isfinite(target).all() or np.linalg.matrix_rank(design) < 3:
        raise ValueError("Calibration samples must be finite and span two dimensions")
    matrix = np.linalg.lstsq(design, target, rcond=None)[0].T
    if matrix.shape != (2, 3) or not np.isfinite(matrix).all() or np.linalg.matrix_rank(matrix[:, :2], tol=np.finfo(float).eps * max(1.0, np.linalg.norm(matrix)) * 3) < 2:
        raise ValueError("Invalid affine calibration profile")
    return matrix


def apply_affine(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    matrix = np.asarray(matrix, dtype=float)
    if matrix.shape != (2, 3) or not np.isfinite(matrix).all() or np.linalg.matrix_rank(matrix[:, :2], tol=np.finfo(float).eps * max(1.0, np.linalg.norm(matrix)) * 3) < 2:
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


def classify_gaze(point: tuple[float, float] | None, profile: dict | None, patient_roi: dict | None, *, camera_match: bool | None = None) -> str:
    if point is None or profile is None:
        return "UNAVAILABLE"
    x, y = point
    camera = profile.get("camera_reference_center")
    if camera_match is True or camera_match is None and camera and hypot(x - camera[0], y - camera[1]) <= profile.get("camera_radius_normalized", CAMERA_RADIUS_NORMALIZED):
        return "CAMERA"
    if 0 <= x <= 1 and 0 <= y <= 1:
        if patient_roi is None:
            return "UNAVAILABLE"
        if patient_roi:
            margin_x = patient_roi["width_normalized"] * PATIENT_MARGIN_RATIO
            margin_y = patient_roi["height_normalized"] * PATIENT_MARGIN_RATIO
            if patient_roi["x_normalized"] - margin_x <= x <= patient_roi["x_normalized"] + patient_roi["width_normalized"] + margin_x and patient_roi["y_normalized"] - margin_y <= y <= patient_roi["y_normalized"] + patient_roi["height_normalized"] + margin_y:
                return "PATIENT"
        return "OTHER_INTERFACE"
    return "AWAY_OR_OUTSIDE"


def classify_interaction_gaze(point, profile, interaction_area, *, camera_match=False):
    """Classify the calibrated lens and observed interaction rectangle as interaction."""
    if point is None or profile is None:
        return 'UNAVAILABLE'
    x, y = point
    if not np.isfinite([x, y]).all():
        return 'UNAVAILABLE'
    if camera_match:
        return 'INSIDE'
    if interaction_area is None:
        return 'UNAVAILABLE'
    left = interaction_area['x_normalized']
    top = interaction_area['y_normalized']
    return 'INSIDE' if (left <= x <= left + interaction_area['width_normalized']
                        and top <= y <= top + interaction_area['height_normalized']) else 'OUTSIDE'
