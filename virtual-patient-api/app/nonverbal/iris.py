"""Eye-local iris coordinates with a participant-specific framing envelope."""
from __future__ import annotations

import numpy as np

from app.nonverbal.gaze import GazeObservation

IRIS_SOURCE = 'mediapipe_iris_v1'
IRIS_ALGORITHM = 'mediapipe_iris_affine_2x3_v1'
EYES = ((33, 133, (469, 470, 471, 472)), (362, 263, (474, 475, 476, 477)))


def _eye_pixels(shared):
    landmarks = getattr(shared, 'landmarks', None)
    width, height = getattr(shared, 'frame_width', None), getattr(shared, 'frame_height', None)
    if not shared.face_valid or landmarks is None or len(landmarks) < 478 or not width or not height:
        return None
    eyes = []
    for left, right, iris in EYES:
        points = np.asarray([[landmarks[i].x * width, landmarks[i].y * height]
                             for i in (left, right, *iris)], dtype=float)
        if not np.isfinite(points).all() or np.linalg.norm(points[1] - points[0]) <= 1e-6:
            return None
        eyes.append(points)
    return eyes


def iris_geometry(shared):
    """Describe head direction, face location and eye scale without guessing device optics."""
    eyes = _eye_pixels(shared)
    matrix = getattr(shared, 'facial_transformation_matrix', None)
    if eyes is None or matrix is None:
        return None
    matrix = np.asarray(matrix, dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        return None
    direction = matrix[:3, 2]
    norm = np.linalg.norm(direction)
    if norm <= 1e-9:
        return None
    direction = direction / norm
    center = np.mean([eye[:2].mean(axis=0) for eye in eyes], axis=0)
    scale = np.mean([np.linalg.norm(eye[1]-eye[0]) for eye in eyes]) / np.hypot(shared.frame_width, shared.frame_height)
    return np.asarray([*direction[:2], center[0]/shared.frame_width, center[1]/shared.frame_height, scale])


def iris_observation(shared, original, bounds=None):
    if not original.valid:
        return original
    eyes = _eye_pixels(shared)
    if eyes is None:
        return GazeObservation(shared.timestamp_ms, False, 'iris_unavailable')
    if bounds is not None:
        try:
            envelope = np.asarray(bounds, dtype=float)
        except (TypeError, ValueError):
            return GazeObservation(shared.timestamp_ms, False, 'outside_calibrated_geometry')
        geometry = iris_geometry(shared)
        if (envelope.shape != (2, 5) or not np.isfinite(envelope).all()
                or np.any(envelope[0] > envelope[1]) or geometry is None
                or np.any(geometry < envelope[0]-1e-9) or np.any(geometry > envelope[1]+1e-9)):
            return GazeObservation(shared.timestamp_ms, False, 'outside_calibrated_geometry')
    positions = []
    for eye in eyes:
        axis = eye[1]-eye[0]
        width_squared = axis @ axis
        delta = eye[2:].mean(axis=0)-eye[:2].mean(axis=0)
        positions.append([delta @ axis / width_squared,
                          delta @ np.asarray([-axis[1], axis[0]]) / width_squared])
    x, y = np.mean(positions, axis=0)
    return GazeObservation(shared.timestamp_ms, True, IRIS_SOURCE, float(x), float(y), float(x), float(y))


