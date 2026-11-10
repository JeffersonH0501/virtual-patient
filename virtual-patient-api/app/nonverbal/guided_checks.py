"""Prompt-conditioned diagnostics; no fitted detector or verified ground truth."""
import hashlib
import logging
from dataclasses import asdict
from pathlib import Path
import numpy as np

from app.nonverbal.gaze_calibration import MIN_FACE_VALID_RATIO
from app.nonverbal.iris import iris_geometry
from app.nonverbal.smile import aggregate_smile
from app.nonverbal.ccdbhg import analyze_nods, NodAnalysis, TARGET_STEP_MS


def analyze_guided_checks(observations, intervals, profile, *, environment=None, geometry=None,
                          protocol="guided_checks_v4_orientation", camera_result=None):
    nod_analysis = NodAnalysis((), False, "insufficient_signal")
    if any(item.kind in {"gaze_nod", "nod_still", "nod_three", "head_shake"} for item in intervals):
        try:
            nod_analysis = analyze_nods([item.shared for item in observations])
        except Exception:
            logging.getLogger(__name__).exception("Guided nod analysis failed")
            nod_analysis = NodAnalysis((), False, "extractor_failure")
    phases = []
    for interval in intervals:
        selected = [item for item in observations
                    if interval.observation_start_ms <= item.shared.timestamp_ms < interval.end_ms]
        expected = (interval.end_ms - interval.observation_start_ms) / 100
        target = None
        smiles, errors, samples = [], [], []
        gaze_valid = 0
        for item in selected:
            point = None
            valid = False
            frame_geometry = iris_geometry(item.shared)
            if profile:
                from app.nonverbal.mediapipe_calibration import gaze_observation
                source = gaze_observation(item.shared, profile)
                if source.valid and source.unclipped_x is not None and source.unclipped_y is not None:
                    mapped = np.asarray([source.unclipped_x, source.unclipped_y])
                    if np.isfinite(mapped).all():
                        point = mapped.tolist()
                        if target is not None:
                            errors.append(float(np.linalg.norm(mapped - target)))
                        valid = True
            gaze_valid += int(valid)
            if item.smile is not None:
                smiles.append(item.smile)
            samples.append({"timestamp_ms": item.shared.timestamp_ms,
                "gaze_point": point, "gaze_inside_calibration": valid,
                "geometry": frame_geometry.tolist() if frame_geometry is not None else None,
                "mouth_smile_left": item.smile.mouth_smile_left if item.smile else None,
                "mouth_smile_right": item.smile.mouth_smile_right if item.smile else None,
                "smile_detected": item.smile.smile_detected if item.smile else None})
        face_ratio = min(1., sum(item.shared.face_valid for item in selected) / expected)
        smile_ratio, activation = aggregate_smile(smiles)
        smile_available = len(smiles) / expected >= MIN_FACE_VALID_RATIO
        gaze_available = gaze_valid / expected >= MIN_FACE_VALID_RATIO
        nod_windows = sum(interval.observation_start_ms <= time < interval.end_ms for time in nod_analysis.evaluated_timestamps_ms)
        nod_coverage = min(1., nod_windows / ((interval.end_ms - interval.observation_start_ms) / TARGET_STEP_MS))
        nod_available = nod_analysis.evaluated and nod_coverage >= MIN_FACE_VALID_RATIO
        nod_events = [event for event in nod_analysis.events if interval.observation_start_ms <= event.midpoint_ms < interval.end_ms]
        nod_count = len(nod_events) if nod_available else None
        prompted_nods = {"nod_still": 0, "nod_three": 3, "head_shake": 0}.get(interval.kind)
        phases.append({"kind": interval.kind, "status": "available" if face_ratio >= MIN_FACE_VALID_RATIO else "insufficient_signal",
            "face_valid_ratio": face_ratio, "sample_count": len(selected), "target": target,
            "gaze_valid_ratio": gaze_valid / len(selected) if gaze_available else None,
            "gaze_error_median": float(np.median(errors)) if errors else None,
            "gaze_error_p90": float(np.percentile(errors, 90)) if errors else None,
            "smile_activity_ratio": smile_ratio if smile_available else None,
            "mean_smile_activation": activation if smile_available else None,
            "smile_activation_p10": float(np.percentile([item.smile_activation for item in smiles], 10)) if smile_available else None,
            "smile_activation_p90": float(np.percentile([item.smile_activation for item in smiles], 90)) if smile_available else None,
            "nod_count": nod_count, "prompted_nod_count": prompted_nods,
            "nod_count_difference": nod_count-prompted_nods if nod_count is not None and prompted_nods is not None else None,
            "nod_evaluable_windows": nod_windows, "nod_window_coverage": nod_coverage,
            "nod_unavailable_reason": None if nod_available else nod_analysis.reason or "insufficient_signal",
            "nod_events": [asdict(event) for event in nod_events],
            "samples": samples})
    analysis_source = Path(__file__).read_bytes()
    analysis_source += Path(__file__).with_name("guided_eye_geometry.py").read_bytes()
    analysis_source += Path(__file__).with_name("gaze_calibration.py").read_bytes()
    analysis_source += Path(__file__).with_name("mediapipe_calibration.py").read_bytes()
    return {"version": protocol,
            "analysis_sha256": hashlib.sha256(analysis_source).hexdigest(), "diagnostic_only": True,
            "environment": environment, "geometry": geometry, "environment_source": "user_reported",
            "decoded_video_dimensions": [{"width": width, "height": height} for width,height in sorted({
                (item.shared.frame_width, item.shared.frame_height) for item in observations
                if item.shared.frame_width and item.shared.frame_height})],
            "prompt_labels_verified": False, "phases": phases}
