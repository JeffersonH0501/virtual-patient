"""Quality eligibility must precede per-feature/context quartile references."""
from types import SimpleNamespace
import pytest
from app.multimodal.turn_results import compute_session_references
from app.multimodal.schemas import NonverbalProcessedFeatures, NonverbalRawFeatures
from app.multimodal.schemas import ParaverbalProcessedFeatures, ParaverbalRawFeatures


def raw(valid):
    return NonverbalRawFeatures(face_score_samples=[], gaze_yaw_samples=[], gaze_pitch_samples=[],
        smile_activation_samples=[], head_pitch_samples=[], frame_timestamps_ms=[], sample_fps=10, turn_duration_ms=1000,
        video_quality={"expected_frames": 10, "valid_smile_frames": 10 if valid else 1,
                       "valid_nod_predictions": 10}, extractor={})


@pytest.mark.parametrize("values,expected", [([1,2,3,4,100], 3.25), ([1,2,3,100], None)])
def test_rejected_smile_cannot_change_quartiles_or_satisfy_four_references(values, expected):
    processed = {str(index): NonverbalProcessedFeatures(mean_smile_activation=value, nod_rate_min=value)
                 for index, value in enumerate(values)}
    raws = {key: raw(index < len(values) - 1) for index, key in enumerate(processed)}
    references = compute_session_references(processed_by_turn=processed, raw_by_turn=raws,
        feature_names=["mean_smile_activation", "nod_rate_min"], min_turns=4)
    assert references["nod_rate_min"]["p75"] is not None
    if expected is None:
        assert "mean_smile_activation" not in references
    else:
        assert references["mean_smile_activation"]["p75"] == expected


@pytest.mark.parametrize("feature", ["median_loudness", "loudness_p20_p80_range"])
def test_rejected_audio_is_excluded_per_relative_feature(feature):
    processed = {str(index): ParaverbalProcessedFeatures(**{feature: value}) for index, value in enumerate([1,2,3,4,100])}
    raws = {key: ParaverbalRawFeatures(word_count=1, voiced_duration_ms=1000, f0_samples_semitones=[1],
        loudness_samples=[1], pause_segments_ms=[], turn_duration_ms=1000, extractor={},
        audio_quality={"issues": ["insufficient_voiced_duration"] if key == "4" else []}) for key in processed}
    refs = compute_session_references(processed_by_turn=processed, raw_by_turn=raws,
        feature_names=[feature], min_turns=4)
    assert refs[feature]["p75"] == 3.25


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_invalid_feature_cannot_receive_a_valid_typical_label(invalid):
    from app.multimodal.threshold_engine import compute_nonverbal_base_labels
    from app.multimodal.config_loader import load_methodology_config
    result = compute_nonverbal_base_labels(NonverbalProcessedFeatures(mean_smile_activation=invalid),
        load_methodology_config(), baseline_available=True,
        session_refs={"mean_smile_activation": {"p25": .2, "p75": .6}})
    label = result.smile_activity["mean_smile_activation"]
    assert label.status.value == "unavailable" and label.reason.value == "processing_error"
