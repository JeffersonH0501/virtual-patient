"""Turn-level semantics after the MediaPipe/BlazeGaze/CCDb-HG migration."""

import pytest

from app.multimodal.schemas import NonverbalRawFeatures, UnavailableReason
from app.nonverbal.preprocessing import preprocess_nonverbal_turn


def test_time_weighted_gaze_does_not_fill_invalid_or_long_gaps():
    from app.nonverbal.preprocessing import time_weighted_states
    samples = [{'timestamp_ms': 0, 'state': 'INSIDE'}, {'timestamp_ms': 100, 'state': 'OUTSIDE'},
               {'timestamp_ms': 200, 'state': 'UNAVAILABLE'}, {'timestamp_ms': 900, 'state': 'INSIDE'}]
    totals, _ = time_weighted_states(samples, end_ms=1000)
    assert totals == {'INSIDE': 200, 'OUTSIDE': 100}


def test_interaction_ratio_is_used_for_new_labels():
    from app.multimodal.config_loader import load_methodology_config
    from app.multimodal.threshold_engine import compute_nonverbal_base_labels
    from app.multimodal.label_engine import integrate_nonverbal_labels
    samples = [{'timestamp_ms': 0, 'state': 'INSIDE'}, {'timestamp_ms': 100, 'state': 'OUTSIDE'}]
    item = raw(gaze_semantic_observations=samples, extractor={'window_end_ms': 200})
    processed = preprocess_nonverbal_turn(item, 'listening', baseline=None).processed
    assert processed.interaction_gaze_ratio == .5
    assert processed.visual_alignment_ratio is None
    base = compute_nonverbal_base_labels(processed, load_methodology_config(), baseline_available=True, session_refs=None)
    assert integrate_nonverbal_labels(base, load_methodology_config()).gaze_orientation.value == 'interaction_gaze_inside'


def raw(**overrides):
    values = dict(
        face_score_samples=[], gaze_yaw_samples=[], gaze_pitch_samples=[],
        smile_activation_samples=[], head_pitch_samples=[], frame_timestamps_ms=[],
        sample_fps=10.0, turn_duration_ms=10_000,
        extractor={"name": "mediapipe_blazegaze_ccdbhg", "version": "1"},
        video_quality={},
    )
    values.update(overrides)
    return NonverbalRawFeatures(**values)


def process(features, context):
    return preprocess_nonverbal_turn(features, context, baseline=None)


def test_visual_alignment_remains_pending_until_calibration_wave():
    result = process(
        raw(gaze_yaw_samples=[0.1], gaze_pitch_samples=[0.2], frame_timestamps_ms=[0]),
        "speaking",
    )
    assert result.processed.visual_alignment_ratio is None
    assert result.processed.median_visual_alignment_dwell_ms is None
    assert result.reasons["visual_alignment_ratio"] == UnavailableReason.GAZE_CALIBRATION_PENDING


def test_ccdbhg_values_are_preserved_including_valid_zero():
    result = process(raw(nod_count=0, nod_rate_min=0.0), "listening")
    assert result.processed.nod_count == 0
    assert result.processed.nod_rate_min == 0.0
    assert "nod_count" not in result.reasons


def test_ccdbhg_unavailable_reason_is_preserved():
    result = process(
        raw(nod_unavailable_reason=UnavailableReason.EXTRACTOR_FAILURE), "listening"
    )
    assert result.processed.nod_count is None
    assert result.reasons["nod_count"] == UnavailableReason.EXTRACTOR_FAILURE


def test_smile_activity_uses_explicit_detection_samples():
    result = process(
        raw(smile_activation_samples=[0.2, 0.8, 0.5], smile_detected_samples=[False, True, True]),
        "speaking",
    )
    assert result.processed.smile_activity_ratio == pytest.approx(2 / 3)
    assert result.processed.mean_smile_activation == pytest.approx(0.5)


def test_missing_smile_evidence_is_unavailable():
    result = process(raw(), "speaking")
    assert result.processed.smile_activity_ratio is None
    assert result.reasons["smile_activity_ratio"] == UnavailableReason.INSUFFICIENT_SIGNAL


def test_smile_activity_without_detection_flags_is_unavailable():
    result = process(raw(smile_activation_samples=[0.7]), "speaking")
    assert result.processed.mean_smile_activation == pytest.approx(0.7)
    assert result.processed.smile_activity_ratio is None
    assert result.reasons["smile_activity_ratio"] == UnavailableReason.FEATURE_UNAVAILABLE


@pytest.mark.parametrize("context", ["speaking", "listening"])
def test_context_is_preserved(context):
    assert process(raw(nod_count=0, nod_rate_min=0), context).processed.context == context


def test_unknown_context_is_not_fabricated():
    assert process(raw(), "unknown").processed.context is None


def test_unavailable_frames_and_timestamp_gaps_break_alignment_dwell():
    for observations in (
        [{"timestamp_ms": 0, "state": "PATIENT"}, {"timestamp_ms": 1000, "state": "UNAVAILABLE"}, {"timestamp_ms": 5000, "state": "PATIENT"}],
        [{"timestamp_ms": 0, "state": "PATIENT"}, {"timestamp_ms": 5000, "state": "PATIENT"}],
    ):
        result = process(raw(gaze_semantic_observations=observations), "listening")
        assert result.processed.median_visual_alignment_dwell_ms == 0


def test_dominant_out_of_calibration_geometry_has_a_specific_unavailable_reason():
    features = raw(
        gaze_observations=[{"state": "outside_calibrated_geometry"}] * 3 + [{"state": "eyes_closed"}],
        gaze_semantic_observations=[{"timestamp_ms": index * 100, "state": "UNAVAILABLE"} for index in range(4)],
    )
    result = process(features, "listening")
    assert result.processed.visual_alignment_ratio is None
    assert result.reasons["visual_alignment_ratio"].value == "outside_calibrated_geometry"
    assert result.reasons["median_visual_alignment_dwell_ms"].value == "outside_calibrated_geometry"


def test_isolated_geometry_rejection_does_not_replace_the_missing_signal_reason():
    features = raw(
        gaze_observations=[{"state": "outside_calibrated_geometry"}] + [{"state": "eyes_closed"}] * 3,
        gaze_semantic_observations=[{"timestamp_ms": index * 100, "state": "UNAVAILABLE"} for index in range(4)],
    )
    assert process(features, "speaking").reasons["visual_alignment_ratio"] == UnavailableReason.INSUFFICIENT_SIGNAL
