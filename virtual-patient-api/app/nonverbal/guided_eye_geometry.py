"""Calibrated MediaPipe ocular geometry."""
import numpy as np

from app.nonverbal.gaze_calibration import (
    apply_affine, fit_affine, normalized_errors, MIN_TARGET_VALID_RATIO,
    MIN_TARGET_VALID_MS, MAX_MEDIAN_ERROR, MAX_P90_ERROR, _valid_duration,
)
from app.nonverbal.iris import iris_observation
from app.nonverbal.gaze import GazeObservation
MEDIAPIPE_EYE_OPENNESS = .20


def mediapipe_eye_observation(shared):
    """Use MediaPipe geometry and eye openness."""
    landmarks = getattr(shared, "landmarks", None)
    valid = bool(shared.face_valid and landmarks is not None and len(landmarks) >= 478
                 and shared.frame_width and shared.frame_height)
    if valid:
        for indices in ((33,160,158,133,153,144), (362,385,387,263,373,380)):
            points = np.asarray([[landmarks[i].x * shared.frame_width,
                                  landmarks[i].y * shared.frame_height] for i in indices])
            width = np.linalg.norm(points[0] - points[3])
            openness = (np.linalg.norm(points[1]-points[5]) + np.linalg.norm(points[2]-points[4])) / (2 * width) if width > 0 else 0
            valid &= bool(np.isfinite(points).all() and openness >= MEDIAPIPE_EYE_OPENNESS)
    seed = GazeObservation(shared.timestamp_ms, valid, "mediapipe_geometry" if valid else "eyes_unobservable")
    return iris_observation(shared, seed)


def build_eye_geometry_reference(observations, metadata, *, expected_target_count=5, allow_quality_failure=False,
        max_median_error=MAX_MEDIAN_ERROR, max_p90_error=MAX_P90_ERROR):
    if any(getattr(item.shared, "timestamp_ms", None) is None for item in observations):
        return {"status": "unavailable", "reason": "missing_frame_timestamps"}
    source, target, ids, counts = [], [], [], {}
    coverage_passed = True
    for interval in metadata.targets:
        selected = [item for item in observations if interval.observation_window_start_ms
                    <= item.shared.timestamp_ms < interval.observation_window_end_ms]
        eyes = [mediapipe_eye_observation(item.shared) for item in selected
                if getattr(item.shared, "landmarks", None) is not None]
        valid = [item for item in eyes if item.valid and np.isfinite([item.unclipped_x, item.unclipped_y]).all()]
        counts[interval.target_id] = len(valid)
        eligible = bool(selected and len(valid) / len(selected) >= MIN_TARGET_VALID_RATIO
            and _valid_duration(valid, interval.observation_window_start_ms, interval.observation_window_end_ms) >= MIN_TARGET_VALID_MS)
        coverage_passed = coverage_passed and eligible
        if not valid or (not eligible and not allow_quality_failure):
            return {"status": "unavailable", "reason": "insufficient_target_coverage", "target_samples": counts}
        for item in valid:
            source.append([item.unclipped_x, item.unclipped_y])
            target.append([interval.target_normalized_x, interval.target_normalized_y])
            ids.append(interval.target_id)
    if len(counts) != expected_target_count:
        return {"status": "unavailable", "reason": "incomplete_targets"}
    source, target, ids = np.asarray(source), np.asarray(target), np.asarray(ids)
    errors, residuals, target_errors = [], [], {}
    try:
        for key in counts:
            train, test = ids != key, ids == key
            predictions = apply_affine(source[test], fit_affine(source[train], target[train]))
            residuals.extend(np.abs(predictions - target[test]))
            held_out = normalized_errors(predictions, target[test], metadata.geometry.viewport_width, metadata.geometry.viewport_height)
            errors.extend(held_out)
            target_errors[key] = {"median_normalized_error":float(np.median(held_out)),"p90_normalized_error":float(np.percentile(held_out,90))}
        matrix = fit_affine(source, target)
    except (ValueError, np.linalg.LinAlgError):
        return {"status": "unavailable", "reason": "degenerate_geometry"}
    quality = {"median_normalized_error": float(np.median(errors)),
               "p90_normalized_error": float(np.percentile(errors, 90)),"per_target":target_errors}
    accepted = coverage_passed and quality["median_normalized_error"] <= max_median_error and quality["p90_normalized_error"] <= max_p90_error
    usable = accepted or allow_quality_failure
    return {"version": "guided_ocular_geometry_v1", "status": "ready" if usable else "unavailable", "quality_passed":accepted,
            "reason": None if accepted else "insufficient_target_coverage" if not coverage_passed else "held_out_error", "quality": quality,
            "quality_limits": {"median_normalized_error": max_median_error, "p90_normalized_error": max_p90_error},
            "margin_source": "leave_one_target_out_axis_p90",
            "affine_matrix": matrix.tolist() if usable else None,
            "margin": np.percentile(residuals, 90, axis=0).tolist() if usable else None,
            "target_samples": counts}
