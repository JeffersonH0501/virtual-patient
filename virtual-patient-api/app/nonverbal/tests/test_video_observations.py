from types import SimpleNamespace

import numpy as np
import pytest

from app.nonverbal.gaze import GazeObservation
from app.nonverbal.shared_observations import SharedFrameObservation
from app.nonverbal.smile import SmileObservation
from app.nonverbal.video_observations import (
    EnrichedFrameObservation,
    TurnWindow,
    build_turn_raw_features,
    extract_nonverbal_video_observations,
    extract_nonverbal_video_observations_parallel,
    segment_nonverbal_observations_by_turn,
)


def enriched(timestamp, *, face=True, smile=True, gaze=True):
    shared = SharedFrameObservation(timestamp, np.zeros((2, 2, 3)), face)
    smile_value = SmileObservation(timestamp, 0.5, 0.2, 0.35, True) if smile else None
    gaze_value = GazeObservation(timestamp, gaze, "identity_calibration" if gaze else "inference_failed", 0.1 if gaze else None, 0.2 if gaze else None, 0.1 if gaze else None, 0.2 if gaze else None)
    return EnrichedFrameObservation(shared, smile_value, gaze_value)


def test_half_open_segmentation_preserves_absolute_timestamps():
    observations = [enriched(0), enriched(999), enriched(1000), enriched(1999)]
    windows = [TurnWindow("a", 0, 1000, "student"), TurnWindow("b", 1000, 2000, "patient")]
    segmented = segment_nonverbal_observations_by_turn(observations, windows)
    assert [item.shared.timestamp_ms for item in segmented["a"]] == [0, 999]
    assert [item.shared.timestamp_ms for item in segmented["b"]] == [1000, 1999]


def test_without_gaze_keeps_all_orientation_unavailable_but_preserves_smile_and_nods():
    from dataclasses import replace
    from app.nonverbal.ccdbhg import NodAnalysis, NodEvent
    from app.nonverbal.preprocessing import preprocess_nonverbal_turn
    from app.multimodal.calibration import read_calibration_profile
    from app.multimodal.config_loader import load_methodology_config
    from app.multimodal.threshold_engine import compute_nonverbal_base_labels
    from app.multimodal.label_engine import integrate_nonverbal_labels
    interview = SimpleNamespace(interview_metadata={'calibration': {
        'status': 'without_gaze', 'profile': {'gaze_source': 'mediapipe_five_point_v1', 'affine_matrix': [[1, 0, 0], [0, 1, 0]]}}})
    samples = [enriched(timestamp) for timestamp in range(0, 1000, 100)]
    samples[1] = replace(samples[1], gaze=GazeObservation(100, False, 'eyes_closed', None, None, None, None))
    samples[2] = replace(samples[2], gaze=GazeObservation(200, False, 'face_not_detected', None, None, None, None))
    raw = build_turn_raw_features(samples, TurnWindow('a', 0, 1000, 'patient'),
        calibration_profile=read_calibration_profile(interview),
        nod_analysis=NodAnalysis((NodEvent(200, 400, 300, .9),), True, evaluated_timestamps_ms=(100, 300)))
    assert raw.gaze_semantic_observations == []
    result = preprocess_nonverbal_turn(raw, 'listening', baseline=None)
    assert result.processed.interaction_gaze_ratio is None
    assert result.processed.interaction_gaze_duration_ms is None
    assert result.processed.outside_gaze_duration_ms is None
    assert result.processed.median_interaction_dwell_ms is None
    assert result.processed.nod_count == 1
    assert result.processed.smile_activity_ratio == 1
    config = load_methodology_config()
    base = compute_nonverbal_base_labels(result.processed, config, baseline_available=False, session_refs=None)
    integrated = integrate_nonverbal_labels(base, config)
    assert integrated.gaze_orientation.status.value == 'unavailable'
    assert integrated.gaze_orientation.value is None
    assert integrated.head_nods.status.value == 'ok'
    assert integrated.smile_activity.status.value == 'ok'
    from app.multimodal.evidence_text import render_family_evidence
    payload = {'integrated_labels': integrated.model_dump(mode='json'),
               'processed': result.processed.model_dump(mode='json'), 'raw': raw.model_dump(mode='json')}
    assert render_family_evidence(payload, 'gaze_orientation') is None


def test_partial_feature_availability_is_preserved_per_turn():
    window = TurnWindow("a", 0, 1000, "student")
    raw = build_turn_raw_features(
        [enriched(10, smile=False, gaze=True), enriched(20, smile=True, gaze=False)],
        window,
    )
    assert raw.frame_timestamps_ms == [10, 20]
    assert len(raw.smile_activation_samples) == 1
    assert raw.gaze_observations[0]["valid"] is True
    assert raw.gaze_observations[1]["valid"] is False


def test_unobservable_face_and_closed_eyes_are_separate_outside_reasons():
    from dataclasses import replace
    samples = [replace(enriched(100, smile=False, gaze=False), gaze=GazeObservation(100, False, 'eyes_closed')),
               replace(enriched(200, face=False, smile=False, gaze=False), gaze=GazeObservation(200, False, 'face_not_detected')),
               replace(enriched(300, smile=False, gaze=False), gaze=GazeObservation(300, False, 'capture_quality'))]
    raw = build_turn_raw_features(samples, TurnWindow('a', 0, 400, 'student'), calibration_profile={})
    assert raw.gaze_semantic_observations == [
        {'timestamp_ms': 100, 'state': 'OUTSIDE', 'reason': 'eyes_closed'},
        {'timestamp_ms': 200, 'state': 'OUTSIDE', 'reason': 'face_not_detected'},
        {'timestamp_ms': 300, 'state': 'UNAVAILABLE'},
    ]
    assert raw.smile_activation_samples == [] and raw.nod_count is None


def test_invalid_historical_roi_leaves_alignment_unavailable_without_losing_smile():
    snapshots = [None]
    raw = build_turn_raw_features(
        [enriched(100)],
        TurnWindow("a", 0, 1000, "student"),
        calibration_profile={"camera_reference_center": [0.9, 0.9]},
        patient_roi_snapshots=snapshots,
        roi_duration_ms=1000,
    )
    assert raw.gaze_semantic_observations == [{"timestamp_ms": 100, "state": "UNAVAILABLE"}]
    assert raw.smile_detected_samples == [True]
    assert snapshots == [None]


def test_future_roi_is_not_assigned_to_an_earlier_observation():
    raw = build_turn_raw_features([enriched(100)], TurnWindow("a", 0, 1000, "student"),
        calibration_profile={"camera_reference_center": [.9, .9]},
        patient_roi_snapshots=[{"timestampMs": 500, "xNormalized": 0, "yNormalized": 0,
                                "widthNormalized": .5, "heightNormalized": .5}], roi_duration_ms=1000)
    assert raw.gaze_semantic_observations == [{"timestamp_ms": 100, "state": "UNAVAILABLE"}]


def test_video_preserves_order_and_marks_uncalibrated_gaze_unavailable(monkeypatch):
    from app.nonverbal import video_observations as module
    shared = [enriched(timestamp).shared for timestamp in (0, 100, 200)]
    monkeypatch.setattr(module, "extract_video", lambda *args, **kwargs: iter(shared))
    monkeypatch.setattr(module, "extract_smile", lambda item: None)
    result = module.extract_nonverbal_video_observations_parallel(None)
    assert [item.shared.timestamp_ms for item in result] == [0, 100, 200]
    assert all(item.gaze.state == "gaze_calibration_pending" for item in result)
    assert all(item.shared.frame is None for item in result)


def test_video_propagates_extraction_error(monkeypatch):
    from app.nonverbal import video_observations as module
    def failing(*args, **kwargs):
        raise RuntimeError("extraction failed")
        yield
    monkeypatch.setattr(module, "extract_video", failing)
    with pytest.raises(RuntimeError, match="extraction failed"):
        module.extract_nonverbal_video_observations_parallel(None)
