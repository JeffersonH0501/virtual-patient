"""Do not send sparse or technically invalid evidence to communication scoring."""
import pytest
from app.multimodal.quality_policy import family_evidence_available


@pytest.mark.parametrize("family,key", [("gaze_orientation", "valid_gaze_frames"), ("smile_activity", "valid_smile_frames"), ("head_nods", "valid_nod_predictions")])
def test_visual_quality_is_family_specific_and_requires_coverage(family, key):
    assert not family_evidence_available({"quality": {"expected_frames": 600, key: 1}}, family)
    assert not family_evidence_available({"integrated_labels": {}}, family)
    assert family_evidence_available({"quality": {"expected_frames": 10, key: 8}}, family)
    assert not family_evidence_available({"quality": {"expected_frames": 10, key: 7}}, family)


@pytest.mark.parametrize("issue", ["insufficient_voiced_duration", "clipping_unusable"])
def test_invalid_audio_is_unavailable(issue):
    for family in ("speech_timing", "prosodic_level", "prosodic_variability"):
        assert not family_evidence_available({"quality": {"issues": [issue]}}, family)


def test_clipping_observation_alone_does_not_discard_all_audio():
    for family in ("speech_timing", "prosodic_level", "prosodic_variability"):
        assert family_evidence_available({"quality": {"issues": ["clipping_detected"], "clipped_samples": 1}}, family)


def test_truncated_audio_preserves_eligible_acoustic_samples_but_not_timing():
    payload = {"quality": {"issues": ["truncated_audio"]}}
    assert not family_evidence_available(payload, "speech_timing")
    assert family_evidence_available(payload, "prosodic_level")
    assert family_evidence_available(payload, "prosodic_variability")


def test_nod_coverage_excludes_model_warmup_but_requires_predictions():
    payload = {"raw": {"turn_duration_ms": 2000}, "quality": {"nod_eligible_ms": 1000, "nod_evaluable_ms": 800}}
    assert family_evidence_available(payload, "head_nods")
    payload["quality"]["nod_evaluable_ms"] = 100
    assert not family_evidence_available(payload, "head_nods")
