from dataclasses import dataclass

import numpy as np
import pytest

from types import SimpleNamespace
from unittest.mock import patch

import tensorflow as tf

from app.nonverbal.gaze import (
    create_batch_buffers,
    extract_gaze,
    extract_gaze_batch,
    package_blazegaze_inputs,
    reset_tracker,
    visual_alignment_unavailable,
)
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


@pytest.mark.parametrize("batch_size", [1, 7, 16])
def test_preallocated_batch_packaging_is_exactly_equal_to_reference_route(batch_size):
    rng = np.random.default_rng(42)
    prepared = [
        (
            index,
            rng.integers(0, 256, size=(128, 512, 3), dtype=np.uint8),
            rng.normal(size=3),
            rng.normal(size=3),
        )
        for index in range(batch_size)
    ]
    images, heads, origins = package_blazegaze_inputs(
        prepared, create_batch_buffers()
    )
    reference_images = tf.convert_to_tensor(
        np.stack([item[1] for item in prepared]) / 255.0, dtype=tf.float32
    ).numpy()
    reference_heads = tf.convert_to_tensor(
        np.stack([item[2] for item in prepared]), dtype=tf.float32
    ).numpy()
    reference_origins = tf.convert_to_tensor(
        np.stack([item[3] for item in prepared]), dtype=tf.float32
    ).numpy()

    assert np.array_equal(images, reference_images)
    assert np.array_equal(heads, reference_heads)
    assert np.array_equal(origins, reference_origins)


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


def test_reset_tracker_preserves_model_and_clears_video_local_state():
    class FakeKalman:
        def __init__(self, **kwargs):
            self.options = kwargs

    model = object()
    tracker = SimpleNamespace(
        blazegaze=model,
        config=SimpleNamespace(
            kalman_config=SimpleNamespace(
                enabled=False,
                dt=1.0,
                process_noise=2.0,
                measurement_noise=3.0,
            )
        ),
        face_width_cm=14.0,
        intrinsics=object(),
        _perspective_geometry_cache=object(),
        _optimization_counters={"samples": 10},
        affine_matrix=None,
    )

    result = reset_tracker(
        tracker,
        affine_matrix=[[1, 0, 0.1], [0, 1, -0.2]],
        kalman_enabled=True,
        kalman_filter_class=FakeKalman,
    )

    assert result is tracker
    assert tracker.blazegaze is model
    assert tracker.config.kalman_config.enabled is True
    assert tracker.face_width_cm is None
    assert tracker.intrinsics is None
    assert tracker._perspective_geometry_cache is None
    assert tracker._optimization_counters is None
    assert np.array_equal(
        tracker.affine_matrix,
        np.asarray([[1, 0, 0.1], [0, 1, -0.2]]),
    )


def test_batched_model_keeps_affine_and_kalman_postprocessing_sequential():
    class OrderedKalman:
        def __init__(self):
            self.inputs = []

        def step(self, point):
            self.inputs.append(np.asarray(point).copy())
            return np.asarray(point).reshape(2, 1)

    class BatchTracker:
        def __init__(self):
            self.config = SimpleNamespace(
                ear_threshold=0.2,
                kalman_config=SimpleNamespace(enabled=True),
            )
            self.affine_matrix = np.asarray([[2, 0, 1], [0, 3, -1]], dtype=float)
            self.kalman_filter = OrderedKalman()
            self._optimization_counters = {}
            self.calls = 0
            self.batched_infer_fn = BatchInference(self)

        def prepare_input(self, frame, landmarks, facial_rt):
            marker = facial_rt[0, 3]
            return (
                np.full((128, 512, 3), marker, dtype=np.uint8),
                np.asarray([marker, 0, 0], dtype=float),
                np.asarray([0, marker, 0], dtype=float),
            )

    class BatchInference:
        def __init__(self, tracker):
            self.tracker = tracker

        def __call__(self, images, heads, origins):
            self.tracker.calls += 1
            return tf.stack((heads[:, 0], origins[:, 1]), axis=1)

        def experimental_get_tracing_count(self):
            return 1

    tracker = BatchTracker()
    observations = []
    for index in range(3):
        matrix = np.eye(4, dtype=np.float32)
        matrix[0, 3] = index + 1
        observations.append(
            SharedFrameObservation(
                index * 100,
                np.zeros((720, 1280, 3), dtype=np.uint8),
                True,
                [Point() for _ in range(478)],
                {},
                matrix,
            )
        )

    with patch("webeyetrack.model_based.compute_ear", return_value=1.0):
        results = extract_gaze_batch(observations, tracker)

    expected = [np.asarray([3, 2]), np.asarray([5, 5]), np.asarray([7, 8])]
    assert tracker.calls == 1
    assert all(result.valid for result in results)
    assert all(np.array_equal(actual, wanted) for actual, wanted in zip(tracker.kalman_filter.inputs, expected))
    assert [(item.unclipped_x, item.unclipped_y) for item in results] == [
        (3.0, 2.0),
        (5.0, 5.0),
        (7.0, 8.0),
    ]
