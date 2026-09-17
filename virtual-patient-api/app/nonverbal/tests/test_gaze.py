from dataclasses import dataclass

import numpy as np

from app.nonverbal.gaze import extract_gaze, visual_alignment_unavailable
from app.nonverbal.shared_observations import SharedFrameObservation


@dataclass
class Point:
    x: float = 0.5
    y: float = 0.5
    z: float = 0.0


class Tracker:
    def __init__(self, point=(-0.2, 1.3), state="open"):
        self.point = point
        self.state = state
        self.calls = 0

    def step(self, frame, landmarks, matrix):
        from webeyetrack.data_protocols import GazeResult, TrackingStatus

        self.calls += 1
        return TrackingStatus.SUCCESS, GazeResult(
            facial_landmarks=landmarks, face_rt=matrix, face_blendshapes=None,
            eye_patch=None, head_vector=None, face_origin_3d=None, metric_face=None,
            metric_transform=None, gaze_state=self.state,
            norm_pog=np.asarray(self.point), durations={},
        )


def observation(valid=True):
    return SharedFrameObservation(
        125.0, np.zeros((10, 10, 3), dtype=np.uint8), valid,
        [Point() for _ in range(478)] if valid else None, {},
        np.eye(4) if valid else None,
    )


def test_gaze_preserves_unclipped_values_and_clips_display_only():
    tracker = Tracker()
    result = extract_gaze(observation(), tracker)
    assert tracker.calls == 1
    assert result.valid is True
    assert (result.unclipped_x, result.unclipped_y) == (-0.2, 1.3)
    assert (result.display_x, result.display_y) == (-0.2, 0.5)


def test_invalid_shared_observation_does_not_call_tracker():
    tracker = Tracker()
    result = extract_gaze(observation(False), tracker)
    assert tracker.calls == 0
    assert result.valid is False
    assert result.state == "face_unavailable"


def test_closed_eyes_are_unavailable_not_negative_performance():
    result = extract_gaze(observation(), Tracker(state="closed"))
    assert result.valid is False
    assert result.state == "eyes_closed"
    assert result.unclipped_x is None


def test_visual_alignment_is_explicitly_pending_calibration():
    result = visual_alignment_unavailable()
    assert result["visual_alignment_ratio"] is None
    assert result["reason"] == "gaze_calibration_pending"
