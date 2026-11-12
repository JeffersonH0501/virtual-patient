"""Evidence is selective, reproducible and excludes unavailable families."""

from app.multimodal.evidence_text import render_family_evidence


def test_gaze_includes_calibrated_camera_and_time_denominator():
    payload = {
        "integrated_labels": {"gaze_orientation": {"status": "ok", "value": "interaction_gaze_inside"}},
        "processed": {"interaction_gaze_ratio": .5},
        "raw": {"turn_duration_ms": 1000},
        "quality": {"evaluable_gaze_ms": 900},
    }
    text = render_family_evidence(payload, "gaze_orientation")
    assert "calibrated camera" in text and "50.0%" in text
    payload["quality"]["evaluable_gaze_ms"] = 100
    assert render_family_evidence(payload, "gaze_orientation") is None


def test_gaze_evidence_explains_closed_eyes_and_missing_face():
    payload = {
        "integrated_labels": {"gaze_orientation": {"status": "ok", "value": "interaction_gaze_inside"}},
        "processed": {"interaction_gaze_ratio": .5},
        "raw": {"turn_duration_ms": 400, "sample_fps": 10, "extractor": {"window_end_ms": 400},
                "gaze_semantic_observations": [
                    {"timestamp_ms": 0, "state": "INSIDE"},
                    {"timestamp_ms": 100, "state": "OUTSIDE", "reason": "eyes_closed"},
                    {"timestamp_ms": 200, "state": "OUTSIDE", "reason": "face_not_detected"},
                    {"timestamp_ms": 300, "state": "INSIDE"}]},
        "quality": {"evaluable_gaze_ms": 400},
    }
    text = render_family_evidence(payload, "gaze_orientation")
    assert "closed eyes: 0.10 seconds" in text
    assert "face not detected: 0.10 seconds" in text


def test_long_pause_evidence_includes_median_and_voice_window():
    payload = {
        "integrated_labels": {"speech_timing": {"status": "ok", "value": "intermittent_by_long_pauses"}},
        "processed": {"speech_rate_wpm": 126, "pause_count": 1, "median_pause_duration_ms": 2020, "pause_time_ratio": .3},
        "quality": {"issues": []},
    }
    text = render_family_evidence(payload, "speech_timing")
    assert "2.02 seconds" in text and "30.0%" in text and "126.0 words" in text


def test_speech_boundary_note_is_explicitly_uncertain():
    payload = {
        "integrated_labels": {"speech_timing": {"status": "ok", "value": "no_reportable_pauses"}},
        "processed": {"speech_rate_wpm": 150},
        "quality": {"issues": ["speech_at_window_start"]},
    }
    assert "completeness of the speech and transcript is uncertain" in render_family_evidence(payload, "speech_timing")
