"""Selector-to-CCDb-HG integration and invalid-input/resource regressions."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
import torch

from app.nonverbal import ccdbhg, mediapipe_extractor as extractor


class Capture:
    def __init__(self, fps):
        self.fps, self.index, self.released = fps, -1, False
    def get(self, key):
        return self.fps if key == cv2.CAP_PROP_FPS else self.index * 1000 / self.fps
    def read(self):
        self.index += 1
        return (True, np.zeros((8, 8, 3), dtype=np.uint8)) if self.index <= min(self.fps * 3, 90) else (False, None)
    def release(self):
        self.released = True


def detector():
    points = [SimpleNamespace(x=index / 1000, y=index / 2000, z=0) for index in range(478)]
    return SimpleNamespace(detect_for_video=Mock(return_value=SimpleNamespace(
        face_landmarks=[points], face_blendshapes=[], facial_transformation_matrixes=[np.eye(4)])), close=Mock())


@pytest.mark.parametrize("fps", [24, 25, 29.97, 30])
def test_actual_selector_produces_valid_windows_on_a_fixed_schedule(monkeypatch, fps):
    capture = Capture(fps)
    monkeypatch.setattr(cv2, "VideoCapture", lambda _: capture)
    observations = list(extractor.extract_video(Path("synthetic.webm"), landmarker=detector()))
    decoded = [index * 1000 / fps for index in range(int(fps * 3) + 1)]
    expected = [next(timestamp for timestamp in decoded if timestamp + 1e-6 >= target)
                for target in range(0, int(decoded[-1]) + 1, 100)]
    assert [item.timestamp_ms for item in observations] == expected
    windows = ccdbhg.resample_windows(ccdbhg.frame_features(observations))
    assert windows and all(value.shape == (31, 18) for _, value in windows)
    assert capture.released


@pytest.mark.parametrize("fps", [0, float("nan"), float("inf")])
def test_invalid_source_rate_releases_capture_and_owned_detector(monkeypatch, fps):
    capture, owned = Capture(fps), detector()
    monkeypatch.setattr(cv2, "VideoCapture", lambda _: capture)
    monkeypatch.setattr(extractor, "create_face_landmarker", lambda: owned)
    with pytest.raises(RuntimeError):
        list(extractor.extract_video(Path("synthetic.webm")))
    assert capture.released
    owned.close.assert_called_once()


@pytest.mark.parametrize("fps", [0, -1, float("nan"), float("inf")])
def test_invalid_requested_rate_is_rejected_before_native_resources(monkeypatch, fps):
    create = Mock(side_effect=AssertionError("Native allocation must not start"))
    monkeypatch.setattr(extractor, "create_face_landmarker", create)
    with pytest.raises(ValueError):
        list(extractor.extract_video(Path("synthetic.webm"), sample_fps=fps))


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_invalid_ccdbhg_values_are_technical_errors_not_negative_detections(invalid):
    features = [ccdbhg.CCDbHGFrameFeatures(index * 50, np.zeros(18)) for index in range(25)]
    features[10].values[0] = invalid
    with pytest.raises(ValueError, match="finite"):
        ccdbhg.resample_windows(features)


def test_invalid_native_logits_are_not_a_valid_zero_nod_result():
    features = [ccdbhg.CCDbHGFrameFeatures(index * 50, np.tile([0, 0, 0, 1, 0, 0], 3).astype(float)) for index in range(25)]
    features = [ccdbhg.CCDbHGFrameFeatures(item.timestamp_ms,
        np.r_[np.zeros(3), [0,0,0, 1,0,0, 0,1,0, -50,0,0, 50,0,0]]) for item in features]
    with pytest.raises(ValueError, match="finite"):
        ccdbhg.infer(features, np.ones((1, 1, 18)), lambda _: torch.full((1, 6), float("nan")))


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_invalid_smile_is_unavailable_instead_of_a_negative_observation(invalid):
    from app.nonverbal.shared_observations import SharedFrameObservation
    from app.nonverbal.smile import extract_smile
    shared = SharedFrameObservation(0, None, True, blendshapes={"mouthSmileLeft": invalid, "mouthSmileRight": .2})
    assert extract_smile(shared) is None
    from app.nonverbal.gaze import GazeObservation
    from app.nonverbal.video_observations import EnrichedFrameObservation, TurnWindow, build_turn_raw_features
    raw = build_turn_raw_features([EnrichedFrameObservation(shared, None,
        GazeObservation(0, False, "non_finite_output"))], TurnWindow("synthetic", 0, 1000, "patient"))
    assert raw.video_quality["invalid_smile_frames"] == 1
    assert raw.video_quality["valid_smile_frames"] == 0


def test_native_25fps_video_yields_repeatable_ccdbhg_analysis(tmp_path):
    frame = cv2.imread(str(Path(__file__).with_name("fixtures") / "face.jpg"))
    path = tmp_path / "synthetic_25fps.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25, (frame.shape[1], frame.shape[0]))
    try:
        for _ in range(76):
            writer.write(frame)
    finally:
        writer.release()
    observations = list(extractor.extract_video(path))
    assert observations and any(item.face_valid for item in observations)
    first = ccdbhg.analyze_nods(observations)
    assert first.evaluated and first.evaluated_timestamps_ms
    assert ccdbhg.analyze_nods(observations) == first


def test_cadence_tolerance_does_not_bridge_a_missing_selected_frame(monkeypatch):
    monkeypatch.setattr(cv2, "VideoCapture", lambda _: Capture(25))
    observations = list(extractor.extract_video(Path("synthetic.webm"), landmarker=detector()))
    features = ccdbhg.frame_features(observations)
    gap_start, gap_end = features[9].timestamp_ms, features[11].timestamp_ms
    remaining = [item for index, item in enumerate(features) if index != 10]
    windows = ccdbhg.resample_windows(remaining)
    assert windows
    assert all(end < gap_start or end - 1000 >= gap_end for end, _ in windows)


@pytest.mark.parametrize("missing", ["face_valid", "landmarks", "facial_transformation_matrix"])
def test_variable_cadence_does_not_bridge_an_explicit_invalid_face(monkeypatch, missing):
    from dataclasses import replace
    monkeypatch.setattr(cv2, "VideoCapture", lambda _: Capture(10))
    observations = list(extractor.extract_video(Path("synthetic.webm"), landmarker=detector()))
    assert observations[15].sampling_max_gap_ms == 200
    observations[15] = replace(observations[15], **{missing: False if missing == "face_valid" else None})
    windows = ccdbhg.resample_windows(ccdbhg.frame_features(observations))
    assert windows
    assert all(end < 1500 or end - 1000 > 1500 for end, _ in windows)
