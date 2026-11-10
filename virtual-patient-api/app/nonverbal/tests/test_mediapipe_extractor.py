from types import SimpleNamespace

import numpy as np
import pytest

from app.nonverbal.mediapipe_extractor import observation_from_result


def test_missing_face_is_unavailable_and_preserves_timestamp():
    result = SimpleNamespace(
        face_landmarks=[], face_blendshapes=[], facial_transformation_matrixes=[]
    )
    observation = observation_from_result(123.5, None, result)
    assert observation.timestamp_ms == 123.5
    assert observation.face_valid is False
    assert observation.reason == "face_not_detected"


def test_valid_result_exposes_shared_outputs():
    category = SimpleNamespace(category_name="mouthSmileLeft", score=0.4)
    matrix = object()
    landmarks = [object()]
    result = SimpleNamespace(
        face_landmarks=[landmarks],
        face_blendshapes=[[category]],
        facial_transformation_matrixes=[matrix],
    )
    observation = observation_from_result(50.0, None, result)
    assert observation.face_valid is True
    assert observation.landmarks is landmarks
    assert observation.blendshapes == {"mouthSmileLeft": 0.4}
    assert observation.facial_transformation_matrix is matrix


def sampled_frames(monkeypatch, timestamps, source_fps=47, sample_fps=10):
    import cv2
    import mediapipe as mp
    from app.nonverbal.mediapipe_extractor import extract_video

    class Capture:
        index = -1

        def read(self):
            self.index += 1
            return (True, np.zeros((2, 2, 3), dtype=np.uint8)) if self.index < len(timestamps) else (False, None)

        def get(self, key):
            return source_fps if key == cv2.CAP_PROP_FPS else timestamps[self.index]

        def release(self):
            pass

    result = SimpleNamespace(face_landmarks=[], face_blendshapes=[], facial_transformation_matrixes=[])
    detector = SimpleNamespace(detect_for_video=lambda image, timestamp: result)
    monkeypatch.setattr(cv2, "VideoCapture", lambda path: Capture())
    monkeypatch.setattr(mp, "Image", lambda **kwargs: None)
    return list(extract_video("unused.webm", sample_fps=sample_fps, landmarker=detector))


def test_sampling_stays_on_a_fixed_schedule_without_accumulating_frame_delay(monkeypatch):
    timestamps = [round(index * 1000 / 47) for index in range(100)]
    observations = sampled_frames(monkeypatch, timestamps)
    expected = [next(timestamp for timestamp in timestamps if timestamp >= target)
                for target in range(0, timestamps[-1] + 1, 100)]
    assert [item.timestamp_ms for item in observations] == expected


def test_variable_frame_timing_supports_nod_windows_without_bridging_missing_samples(monkeypatch):
    from app.nonverbal.ccdbhg import CCDbHGFrameFeatures, resample_windows

    timestamps = [round(index * 1000 / 47) for index in range(160) if index % 3 != 2]
    observations = sampled_frames(monkeypatch, timestamps)
    features = [CCDbHGFrameFeatures(item.timestamp_ms, np.zeros(18), item.sampling_max_gap_ms)
                for item in observations]
    assert len(observations) >= 32
    assert resample_windows(features)
    # Missing face observations must not be reconstructed across a long gap.
    assert not resample_windows([item for item in features if item.timestamp_ms < 400 or item.timestamp_ms > 2900])


def test_decoder_gap_does_not_inflate_interpolation_tolerance(monkeypatch):
    observations = sampled_frames(monkeypatch, [0, 21, 64, 107, 150, 193, 700, 743, 786, 829])
    assert max(item.sampling_max_gap_ms for item in observations) <= 143


def test_low_sampling_rate_uses_its_requested_interval(monkeypatch):
    observations = sampled_frames(monkeypatch, np.arange(0, 4000, 40), source_fps=25, sample_fps=2)
    assert len(observations) == 8
    assert all(item.sampling_max_gap_ms <= 200 for item in observations)


@pytest.mark.parametrize("timestamps", [[0, float("nan")], [0, 42, 21]])
def test_invalid_decoded_timestamps_are_rejected(monkeypatch, timestamps):
    with pytest.raises(RuntimeError, match="strictly increasing"):
        sampled_frames(monkeypatch, timestamps)


def test_duplicate_timestamps_are_skipped_without_fabricated_frames(monkeypatch):
    observations = sampled_frames(monkeypatch, [0,0,100,100,200])
    assert [item.timestamp_ms for item in observations] == [0,100,200]


def test_brightness_is_measured_even_when_no_face_is_detected():
    result = SimpleNamespace(face_landmarks=[],face_blendshapes=[],facial_transformation_matrixes=[])
    observation = observation_from_result(0,np.full((16,16,3),80,dtype=np.uint8),result)
    assert observation.frame_brightness_mean == 80
    assert observation.frame_brightness_std == 0
