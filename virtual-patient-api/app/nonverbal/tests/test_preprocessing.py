"""Turn-level semantics after the MediaPipe/BlazeGaze/CCDb-HG migration."""

import pytest

from app.multimodal.schemas import NonverbalRawFeatures, UnavailableReason
from app.nonverbal.preprocessing import preprocess_nonverbal_turn


def raw(**overrides):
    values = dict(
        face_score_samples=[], gaze_yaw_samples=[], gaze_pitch_samples=[],
        au12_samples=[], head_pitch_samples=[], frame_timestamps_ms=[],
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
        raw(au12_samples=[0.2, 0.8, 0.5], smile_detected_samples=[False, True, True]),
        "speaking",
    )
    assert result.processed.smile_activity_ratio == pytest.approx(2 / 3)
    assert result.processed.mean_smile_activation == pytest.approx(0.5)


def test_missing_smile_evidence_is_unavailable():
    result = process(raw(), "speaking")
    assert result.processed.smile_activity_ratio is None
    assert result.reasons["smile_activity_ratio"] == UnavailableReason.INSUFFICIENT_SIGNAL


@pytest.mark.parametrize("context", ["speaking", "listening"])
def test_context_is_preserved(context):
    assert process(raw(nod_count=0, nod_rate_min=0), context).processed.context == context


def test_unknown_context_is_not_fabricated():
    assert process(raw(), "unknown").processed.context is None
