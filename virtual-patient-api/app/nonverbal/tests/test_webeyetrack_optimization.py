"""Numerical equivalence tests against pinned WebEyeTrack upstream behavior."""

import sys

import mediapipe
import numpy as np

sys.modules.setdefault("mediapipe.python", mediapipe)

from webeyetrack import model_based as reference

from app.nonverbal.webeyetrack_profiling import (
    face_reconstruction,
    refine_depth_by_radial_magnitude_vectorized,
)


def test_vectorized_radial_refinement_matches_reference_exactly():
    rng = np.random.default_rng(20260918)
    projected = rng.integers(100, 900, size=(478, 2), dtype=np.int32)
    detected = projected.astype(np.float64) + rng.normal(0, 12, size=(478, 2))

    expected = reference.refine_depth_by_radial_magnitude(
        projected, detected, old_z=60.0, alpha=0.5
    )
    actual = refine_depth_by_radial_magnitude_vectorized(
        projected, detected, old_z=60.0, alpha=0.5
    )

    assert actual == expected


def test_vectorized_reconstruction_matches_reference_and_removes_python_loops():
    rng = np.random.default_rng(75)
    landmarks = np.empty((478, 3), dtype=np.float32)
    landmarks[:, :2] = rng.uniform(0.2, 0.8, size=(478, 2))
    landmarks[:, 2] = rng.uniform(-0.15, 0.15, size=478)
    landmarks[234, :2] = (0.2, 0.5)
    landmarks[454, :2] = (0.8, 0.5)
    perspective = reference.create_perspective_matrix(16 / 9)
    inverse_perspective = np.linalg.inv(perspective)
    intrinsics = reference.estimate_camera_intrinsics(np.zeros((720, 1280, 3)))
    pose = np.eye(4, dtype=np.float32)

    expected_transform, expected_mesh = reference.face_reconstruction(
        perspective, landmarks, 14.0, pose, intrinsics, 1280, 720
    )
    counters = {
        "uvz_matrix_inversions": 1,
        "uvz_python_landmark_iterations": 0,
        "depth_python_landmark_iterations": 0,
        "depth_vectorized_landmark_rows": 0,
        "depth_outer_iterations": 0,
    }
    actual_transform, actual_mesh = face_reconstruction(
        perspective,
        inverse_perspective,
        landmarks,
        14.0,
        pose,
        intrinsics,
        1280,
        720,
        None,
        counters=counters,
    )

    np.testing.assert_array_equal(actual_transform, expected_transform)
    # Vectorized reduction changes only floating-point accumulation order. The
    # observed synthetic worst case is 5.18e-7 absolute / 8.77e-8 relative;
    # real calibration frames compared exactly. Keep acceptance just above it.
    np.testing.assert_allclose(actual_mesh, expected_mesh, atol=1e-6, rtol=1e-7)
    assert counters["uvz_matrix_inversions"] == 1
    assert counters["uvz_python_landmark_iterations"] == 0
    assert counters["depth_python_landmark_iterations"] == 0
    assert counters["depth_outer_iterations"] <= 10
    assert counters["depth_vectorized_landmark_rows"] == (
        counters["depth_outer_iterations"] * 478
    )
