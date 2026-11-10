"""Checks for eye-local geometry used by guided calibration."""
from types import SimpleNamespace

import numpy as np

from app.nonverbal.gaze import GazeObservation
from app.nonverbal.iris import iris_observation


def frame(width=1280, height=720):
    points = [SimpleNamespace(x=.5, y=.5) for _ in range(478)]
    for start, end, indexes in [(33, 133, range(469, 473)), (362, 263, range(474, 478))]:
        points[start] = SimpleNamespace(x=.3, y=.4)
        points[end] = SimpleNamespace(x=.5, y=.4)
        for index in indexes:
            points[index] = SimpleNamespace(x=.45, y=.42)
    return SimpleNamespace(face_valid=True, landmarks=points, frame_width=width,
                           frame_height=height, timestamp_ms=123)


def test_iris_coordinates_use_eye_local_pixel_axes_in_both_orientations():
    for width, height in [(1280, 720), (720, 1280)]:
        gaze = iris_observation(frame(width, height), GazeObservation(123, True, 'identity_calibration'))
        assert gaze.valid
        assert np.isclose(gaze.unclipped_x, .25)
        assert np.isclose(gaze.unclipped_y, .1 * height / width)


def test_iris_rejects_closed_eyes_missing_landmarks_and_degenerate_eye_width():
    shared = frame()
    assert not iris_observation(shared, GazeObservation(123, False, 'eyes_closed')).valid
    shared.landmarks = shared.landmarks[:468]
    assert not iris_observation(shared, GazeObservation(123, True, 'identity_calibration')).valid
    shared = frame()
    shared.landmarks[133] = shared.landmarks[33]
    assert not iris_observation(shared, GazeObservation(123, True, 'identity_calibration')).valid
