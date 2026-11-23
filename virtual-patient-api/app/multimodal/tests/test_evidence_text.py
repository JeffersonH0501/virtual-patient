"""Evidence is selective, reproducible and excludes unavailable families."""
import copy
import re

import pytest

from app.multimodal.label_glossary import LABEL_GLOSSARY
from app.multimodal.evidence_text import render_family_evidence
def test_gaze_includes_calibrated_camera_and_whole_percentage():
    payload = {
        "integrated_labels": {"gaze_orientation": {"status": "ok", "value": "interaction_gaze_inside"}},
        "processed": {"interaction_gaze_ratio": .5},
        "raw": {"turn_duration_ms": 1000},
        "quality": {"evaluable_gaze_ms": 900},
    }
    text = render_family_evidence(payload, "gaze_orientation")
    assert "calibrated camera" in text and "(50% of the analysed time)" in text
    payload["quality"]["evaluable_gaze_ms"] = 100
    assert render_family_evidence(payload, "gaze_orientation") is None
def test_gaze_evidence_explains_closed_eyes_and_missing_face_when_they_are_notable():
    # Six dense samples of each cause: 0.6 s at 10 fps. Stretches under half a second are blinking and tracking noise.
    samples = ([{"timestamp_ms": 0, "state": "INSIDE"}]
               + [{"timestamp_ms": 100 * step, "state": "OUTSIDE", "reason": "eyes_closed"} for step in range(1, 7)]
               + [{"timestamp_ms": 100 * step, "state": "OUTSIDE", "reason": "face_not_detected"} for step in range(7, 13)]
               + [{"timestamp_ms": 1300, "state": "INSIDE"}])
    payload = {
        "integrated_labels": {"gaze_orientation": {"status": "ok", "value": "interaction_gaze_inside"}},
        "processed": {"interaction_gaze_ratio": .5},
        "raw": {"turn_duration_ms": 1400, "sample_fps": 10, "extractor": {"window_end_ms": 1400}, "gaze_semantic_observations": samples},
        "quality": {"evaluable_gaze_ms": 1400},
    }
    text = render_family_evidence(payload, "gaze_orientation")
    note = text.split("The time away includes", 1)[1]
    assert note == " closed eyes and face not detected."
    assert not any(character.isdigit() for character in note)
def test_long_pause_evidence_keeps_count_without_rate_median_or_share():
    payload = {
        "integrated_labels": {"speech_timing": {"status": "ok", "value": "intermittent_by_long_pauses"}},
        "processed": {"speech_rate_wpm": 126, "pause_count": 1, "median_pause_duration_ms": 2020, "pause_time_ratio": .3},
        "quality": {"issues": []},
    }
    text = render_family_evidence(payload, "speech_timing")
    assert "median pause" not in text and "%" not in text and "words per minute" not in text
    assert "1 internal pause of at least 500 ms" in text
def test_speech_boundary_note_is_explicitly_uncertain():
    payload = {
        "integrated_labels": {"speech_timing": {"status": "ok", "value": "no_reportable_pauses"}},
        "processed": {"speech_rate_wpm": 150},
        "quality": {"issues": ["speech_at_window_start"]},
    }
    assert "speech and its transcript may be incomplete" in render_family_evidence(payload, "speech_timing")


@pytest.mark.parametrize("family,label", [
    ("prosodic_level", "typical_loudness"),
    ("prosodic_variability", "reduced_f0_variability"),
])
def test_truncated_audio_keeps_its_quality_note_without_numeric_acoustic_values(family, label):
    payload = {
        "integrated_labels": {family: {"status": "ok", "value": label}},
        "processed": {"median_loudness": .93, "f0_p20_p80_range_semitones": 2.96},
        "quality": {"issues": ["truncated_audio"]},
    }
    text = render_family_evidence(payload, family)
    assert "The audio was truncated; this describes only the decoded portion." in text
    assert not re.search(r"\d", text)


@pytest.mark.parametrize("label", ["no_reportable_pauses", "fast_speech_few_pauses"])
def test_zero_pause_counts_add_no_details_beyond_the_label_description(label):
    payload = {
        "integrated_labels": {"speech_timing": {"status": "ok", "value": label}},
        "processed": {"speech_rate_wpm": 200, "pause_count": 0, "pause_time_ratio": 0},
        "quality": {"issues": []},
    }
    assert render_family_evidence(payload, "speech_timing") == LABEL_GLOSSARY[label]


def test_rendering_preserves_all_stored_measurements():
    payload = {
        "integrated_labels": {
            "speech_timing": {"status": "ok", "value": "intermittent_by_long_pauses"},
            "smile_activity": {"status": "ok", "value": "moderate_smile_activity"},
        },
        "processed": {"speech_rate_wpm": 126, "pause_count": 2, "median_pause_duration_ms": 2020,
                      "pause_time_ratio": .3, "smile_activity_ratio": .2},
        "raw": {"turn_duration_ms": 1000},
        "quality": {"evaluable_smile_ms": 1000, "issues": []},
    }
    before = copy.deepcopy(payload)
    for family in ("speech_timing", "smile_activity"):
        text = render_family_evidence(payload, family)
        assert text is not None
        assert not any(term in text for term in ("words per minute", "median pause", "%", "pauses took"))
    assert payload == before
