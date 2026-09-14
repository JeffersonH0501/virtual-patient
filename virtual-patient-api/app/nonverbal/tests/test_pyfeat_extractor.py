from types import SimpleNamespace

import app.nonverbal.pyfeat_extractor as extractor


class FakeFex:
    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        return enumerate(self.rows)


def _settings(**overrides):
    values = {
        "pyfeat_sample_fps": 2.0,
        "pyfeat_gaze_alignment_max_radians": 0.2,
        "pyfeat_au12_active_threshold": 0.5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_best_face_rows_keeps_highest_confidence_face_per_frame():
    rows = extractor._best_face_rows(FakeFex([
        {"frame": 2, "FaceScore": 0.4, "gaze_yaw": 0.5},
        {"frame": 2, "FaceScore": 0.9, "gaze_yaw": 0.1},
        {"frame": 4, "FaceScore": 0.8, "gaze_yaw": 0.2},
    ]), source_fps=2.0)

    assert len(rows) == 2
    assert rows[0]["timestamp_ms"] == 1000
    assert rows[0]["face_score"] == 0.9
    assert rows[0]["gaze_yaw"] == 0.1


def test_summary_exposes_selected_values_and_temporal_dwell(monkeypatch):
    monkeypatch.setattr(extractor, "settings", _settings())
    rows = [
        {"timestamp_ms": 0, "face_score": 0.9, "gaze_yaw": 0.1, "gaze_pitch": 0.1, "au12": 0.2, "head_pitch": 0.0},
        {"timestamp_ms": 500, "face_score": 0.8, "gaze_yaw": 0.1, "gaze_pitch": 0.1, "au12": 0.8, "head_pitch": 0.1},
        {"timestamp_ms": 1000, "face_score": 0.8, "gaze_yaw": 0.5, "gaze_pitch": 0.1, "au12": 1.0, "head_pitch": 0.2},
    ]

    result = extractor._summarize_turn(rows)

    assert result["visual_alignment_ratio"] == 0.667
    assert result["median_visual_alignment_dwell_ms"] == 1000.0
    assert result["smile_activity_ratio"] == 0.667
    assert result["mean_smile_activation"] == 0.667
    assert result["nod_count"] is None
    assert result["nod_rate_min"] is None


def test_summary_marks_calibration_dependent_metrics_unavailable(monkeypatch):
    monkeypatch.setattr(extractor, "settings", _settings(
        pyfeat_gaze_alignment_max_radians=None,
        pyfeat_au12_active_threshold=None,
    ))
    result = extractor._summarize_turn([
        {"timestamp_ms": 0, "face_score": 0.9, "gaze_yaw": 0.1, "gaze_pitch": 0.1, "au12": 0.6, "head_pitch": 0.0},
    ])

    assert result["visual_alignment_ratio"] is None
    assert result["median_visual_alignment_dwell_ms"] is None
    assert result["smile_activity_ratio"] is None
    assert result["mean_smile_activation"] == 0.6


def test_summary_does_not_treat_missing_gaze_as_misalignment(monkeypatch):
    monkeypatch.setattr(extractor, "settings", _settings())
    result = extractor._summarize_turn([
        {"timestamp_ms": 0, "face_score": 0.9, "gaze_yaw": None, "gaze_pitch": None, "au12": 0.2, "head_pitch": 0.0},
    ])

    assert result["visual_alignment_ratio"] is None
    assert result["median_visual_alignment_dwell_ms"] is None
    assert "gaze_unavailable" in result["video_quality"]["issues"]
