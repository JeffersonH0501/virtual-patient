"""Profiled, vectorized adapter for pinned WebEyeTrack preprocessing.

The behavior is derived from WebEyeTrack commit
75fbd2f5f784f2eb3a39675a8dcbf1b01c697f1c. It preserves the upstream formulas,
iteration limit, convergence rule, and outputs while batching independent
per-landmark operations. The installed upstream functions remain the reference
implementation used by equivalence tests. Timing collection is optional.
"""

from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Any, Iterator

import cv2
import numpy as np


def _record(
    timings: dict[str, list[float]] | None, name: str, started: float
) -> None:
    if timings is not None:
        timings.setdefault(name, []).append((perf_counter() - started) * 1000.0)


@contextmanager
def profile_tracker_prepare_input(
    tracker: Any, timings: dict[str, list[float]]
) -> Iterator[None]:
    """Temporarily replace only ``prepare_input`` with an equivalent profiler."""
    original = tracker.prepare_input

    def profiled(image: np.ndarray, facial_landmarks: np.ndarray, facial_rt: np.ndarray):
        return prepare_input(tracker, image, facial_landmarks, facial_rt, timings)

    tracker.prepare_input = profiled
    try:
        yield
    finally:
        tracker.prepare_input = original


@contextmanager
def profile_inference_call(tracker: Any, timings: dict[str, list[float]]) -> Iterator[None]:
    """Measure the model call inside upstream's broader ``infer_pog`` interval."""
    original = tracker.infer_fn

    def profiled(*args: Any, **kwargs: Any):
        started = perf_counter()
        result = original(*args, **kwargs)
        elapsed_ms = (perf_counter() - started) * 1000.0
        timings.setdefault("webeyetrack_model_call", []).append(elapsed_ms)
        if len(timings["webeyetrack_model_call"]) == 1:
            timings.setdefault("startup.tensorflow_first_trace_and_inference", []).append(elapsed_ms)
        else:
            timings.setdefault("webeyetrack_model_call_steady_state", []).append(elapsed_ms)
        return result

    tracker.infer_fn = profiled
    try:
        yield
    finally:
        tracker.infer_fn = original


def prepare_input(
    tracker: Any,
    image: np.ndarray,
    facial_landmarks: np.ndarray,
    facial_rt: np.ndarray,
    timings: dict[str, list[float]] | None = None,
):
    started = perf_counter()
    conversion_started = perf_counter()
    face_landmarks_2d = facial_landmarks[:, :2]
    face_landmarks_2d = face_landmarks_2d * np.array([image.shape[1], image.shape[0]])
    _record(timings, "prepare_input.landmarks_to_pixels", conversion_started)

    eye_patch = obtain_eyepatch(image, face_landmarks_2d, timings)
    face_origin_3d = compute_face_origin_3d(
        tracker, image, facial_landmarks, facial_rt, timings
    )
    head_vector = get_head_vector(facial_rt, timings)

    packaging_started = perf_counter()
    result = [eye_patch, head_vector, face_origin_3d]
    _record(timings, "prepare_input.python_output_packaging", packaging_started)
    _record(timings, "prepare_input.profiled_total", started)
    return result


def obtain_eyepatch(
    frame: np.ndarray,
    face_landmarks: np.ndarray,
    timings: dict[str, list[float]] | None = None,
    face_padding_coefs=(0.4, 0.2),
    face_crop_size: int = 512,
    dst_img_size=(512, 128),
):
    total_started = perf_counter()
    started = perf_counter()
    lefttop = face_landmarks[103]
    leftbottom = face_landmarks[150]
    righttop = face_landmarks[332]
    rightbottom = face_landmarks[379]
    center = face_landmarks[4]
    src_pts = np.array([lefttop, leftbottom, rightbottom, righttop], dtype=np.float32)
    src_direction = src_pts - center
    src_pts = src_pts + np.array(face_padding_coefs) * src_direction
    dst_pts = np.array(
        [[0, 0], [0, face_crop_size], [face_crop_size, face_crop_size], [face_crop_size, 0]],
        dtype=np.float32,
    )
    _record(timings, "prepare_input.eyepatch.landmark_selection_and_arrays", started)

    started = perf_counter()
    matrix, _ = cv2.findHomography(src_pts, dst_pts)
    _record(timings, "prepare_input.eyepatch.homography", started)

    started = perf_counter()
    warped_face_crop = cv2.warpPerspective(
        frame, matrix, (face_crop_size, face_crop_size)
    )
    _record(timings, "prepare_input.eyepatch.warp_perspective", started)

    started = perf_counter()
    warped_facial_landmarks = np.dot(
        matrix,
        np.vstack((face_landmarks.T, np.ones((1, face_landmarks.shape[0])))),
    )
    warped_facial_landmarks = (
        warped_facial_landmarks[:2, :] / warped_facial_landmarks[2, :]
    ).T.astype(np.int32)
    _record(timings, "prepare_input.eyepatch.landmark_geometry_transform", started)

    started = perf_counter()
    top_eyes_patch = warped_facial_landmarks[151]
    bottom_eyes_patch = warped_facial_landmarks[195]
    eyes_patch = warped_face_crop[top_eyes_patch[1] : bottom_eyes_patch[1], :]
    _record(timings, "prepare_input.eyepatch.roi_extraction", started)

    started = perf_counter()
    eyes_patch = cv2.resize(eyes_patch, dst_img_size)
    _record(timings, "prepare_input.eyepatch.resize", started)
    _record(timings, "prepare_input.eyepatch.total", total_started)
    return eyes_patch


def compute_face_origin_3d(
    tracker: Any,
    image: np.ndarray,
    facial_landmarks: np.ndarray,
    facial_rt: np.ndarray,
    timings: dict[str, list[float]] | None = None,
):
    from webeyetrack.model_based import (
        create_perspective_matrix,
        estimate_camera_intrinsics,
        estimate_face_width,
        estimate_gaze_origins,
    )

    total_started = perf_counter()
    height, width, _ = image.shape
    counters = getattr(tracker, "_optimization_counters", None)
    if counters is None:
        counters = {
            "uvz_matrix_inversions": 0,
            "uvz_python_landmark_iterations": 0,
            "depth_python_landmark_iterations": 0,
            "depth_vectorized_landmark_rows": 0,
            "depth_outer_iterations": 0,
        }
        tracker._optimization_counters = counters

    started = perf_counter()
    if tracker.face_width_cm is None:
        tracker.face_width_cm = estimate_face_width(facial_landmarks[:, :2], facial_rt)
    _record(timings, "prepare_input.face_origin.estimate_face_width", started)

    started = perf_counter()
    if tracker.intrinsics is None:
        tracker.intrinsics = estimate_camera_intrinsics(np.zeros((height, width, 3)))
    facial_landmarks_px = facial_landmarks[:, :2] * np.array([width, height])
    geometry_key = (width, height)
    geometry_cache = getattr(tracker, "_perspective_geometry_cache", None)
    if geometry_cache is None or geometry_cache[0] != geometry_key:
        perspective_matrix = create_perspective_matrix(aspect_ratio=width / height)
        inverse_perspective_matrix = np.linalg.inv(perspective_matrix)
        counters["uvz_matrix_inversions"] += 1
        geometry_cache = (geometry_key, perspective_matrix, inverse_perspective_matrix)
        tracker._perspective_geometry_cache = geometry_cache
    _, perspective_matrix, inverse_perspective_matrix = geometry_cache
    _record(timings, "prepare_input.face_origin.camera_and_perspective_preparation", started)

    metric_transform, metric_face = face_reconstruction(
        perspective_matrix,
        inverse_perspective_matrix,
        facial_landmarks[:, :3],
        tracker.face_width_cm,
        facial_rt,
        tracker.intrinsics,
        width,
        height,
        image,
        timings,
        counters=counters,
    )
    del metric_transform

    started = perf_counter()
    gaze_origins = estimate_gaze_origins(metric_face, facial_landmarks_px)
    _record(timings, "prepare_input.face_origin.estimate_gaze_origins", started)
    _record(timings, "prepare_input.face_origin.total", total_started)
    return gaze_origins["face_origin_3d"]


def face_reconstruction(
    perspective_matrix: np.ndarray,
    inverse_perspective_matrix: np.ndarray,
    face_landmarks: np.ndarray,
    face_width_cm: float,
    face_rt: np.ndarray,
    intrinsic_matrix: np.ndarray,
    frame_width: int,
    frame_height: int,
    frame: np.ndarray,
    timings: dict[str, list[float]] | None = None,
    initial_z_guess: float = 60,
    counters: dict[str, int] | None = None,
):
    from webeyetrack.model_based import (
        LEFTMOST_LANDMARK,
        RIGHTMOST_LANDMARK,
        euler_angles_to_rotation_matrix,
        image_shift_to_3d,
        partial_procrustes_translation_2d,
        rotation_matrix_to_euler_angles,
        transform_3d_to_2d,
        transform_3d_to_3d,
    )

    del frame
    total_started = perf_counter()
    started = perf_counter()
    ndc_points = np.column_stack(
        (
            2 * face_landmarks[:, 0] - 1,
            1 - 2 * face_landmarks[:, 1],
            np.full(len(face_landmarks), -1.0),
            np.ones(len(face_landmarks)),
        )
    )
    world_points = ndc_points @ inverse_perspective_matrix.T
    relative_face_mesh = np.column_stack(
        (
            -(world_points[:, 0] / world_points[:, 3]),
            world_points[:, 1] / world_points[:, 3],
            face_landmarks[:, 2],
        )
    )
    _record(timings, "prepare_input.face_origin.reconstruction.uvz_to_xyz", started)

    started = perf_counter()
    nose = relative_face_mesh[4]
    relative_face_mesh = relative_face_mesh - nose
    relative_face_mesh *= np.array([-1, -1, 1])
    euclidean_distance = np.linalg.norm(
        relative_face_mesh[LEFTMOST_LANDMARK] - relative_face_mesh[RIGHTMOST_LANDMARK]
    )
    relative_face_mesh[:, :] /= euclidean_distance
    canonical_pts_3d = relative_face_mesh * face_width_cm
    _record(timings, "prepare_input.face_origin.reconstruction.canonical_mesh", started)

    started = perf_counter()
    face_r = face_rt[:3, :3].copy()
    pitch, yaw, roll = rotation_matrix_to_euler_angles(np.linalg.inv(face_r))
    pitch, yaw, roll = -yaw, pitch, roll
    face_r = euler_angles_to_rotation_matrix(pitch, yaw, roll)
    canonical_pts_3d = canonical_pts_3d @ np.linalg.inv(face_r).T
    scales = np.linalg.norm(face_r, axis=0)
    face_s = scales.mean()
    face_r /= face_s
    _record(timings, "prepare_input.face_origin.reconstruction.pose_inverses_and_derotation", started)

    started = perf_counter()
    init_transform = np.eye(4, dtype=np.float32)
    init_transform[:3, :3] = face_r
    init_transform[:3, 3] = np.array([0, 0, initial_z_guess], dtype=np.float32)
    camera_pts_3d = transform_3d_to_3d(canonical_pts_3d, init_transform)
    canonical_proj_2d = transform_3d_to_2d(camera_pts_3d, intrinsic_matrix).astype(np.float32)
    detected_2d = face_landmarks[:, :2] * np.array([frame_width, frame_height])
    _record(timings, "prepare_input.face_origin.reconstruction.initial_projection", started)

    started = perf_counter()
    shift_2d = partial_procrustes_translation_2d(canonical_proj_2d, detected_2d)
    shift_3d = image_shift_to_3d(shift_2d, depth_z=initial_z_guess, K=intrinsic_matrix)
    final_transform = init_transform.copy()
    final_transform[:3, 3] += shift_3d
    first_final_transform = final_transform.copy()
    _record(timings, "prepare_input.face_origin.reconstruction.translation_estimation", started)

    started = perf_counter()
    for _ in range(10):
        camera_pts_3d = transform_3d_to_3d(canonical_pts_3d, final_transform)
        final_projected_pts = transform_3d_to_2d(camera_pts_3d, intrinsic_matrix)
        new_z = refine_depth_by_radial_magnitude_vectorized(
            final_projected_pts,
            detected_2d,
            old_z=final_transform[2, 3],
            alpha=0.5,
        )
        if counters is not None:
            counters["depth_outer_iterations"] += 1
            counters["depth_vectorized_landmark_rows"] += len(final_projected_pts)
        diff_z = new_z - final_transform[2, 3]
        if np.abs(diff_z) < 0.25:
            break
        prior_x = first_final_transform[0, 3]
        prior_y = first_final_transform[1, 3]
        final_transform[0, 3] = prior_x * (new_z / initial_z_guess)
        final_transform[1, 3] = prior_y * (new_z / initial_z_guess)
        final_transform[2, 3] = new_z
    _record(timings, "prepare_input.face_origin.reconstruction.depth_refinement_loop", started)

    started = perf_counter()
    final_face_pts = transform_3d_to_3d(canonical_pts_3d, final_transform)
    _record(timings, "prepare_input.face_origin.reconstruction.final_transform", started)
    _record(timings, "prepare_input.face_origin.reconstruction.total", total_started)
    return final_transform, final_face_pts


def refine_depth_by_radial_magnitude_vectorized(
    final_projected_pts: np.ndarray,
    detected_2d: np.ndarray,
    old_z: float,
    alpha: float = 0.5,
) -> float:
    """Vectorized equivalent of the pinned upstream radial-depth refinement."""
    from webeyetrack.model_based import MAX_STEP_CM

    del alpha
    detected_center = detected_2d.mean(axis=0)
    vectors = detected_2d - final_projected_pts
    vector_norms = np.linalg.norm(vectors, axis=1)
    center_vectors = detected_center - final_projected_pts
    dot_products = np.einsum("ij,ij->i", vectors, center_vectors)
    signed_distances = np.where(dot_products < 0, -vector_norms, vector_norms)
    distance_per_point = np.sum(signed_distances) / len(final_projected_pts)
    delta = 1e-1 * distance_per_point
    safe_delta = max(-MAX_STEP_CM, min(MAX_STEP_CM, delta))
    return old_z + safe_delta


def get_head_vector(
    facial_rt: np.ndarray, timings: dict[str, list[float]] | None = None
):
    from webeyetrack.model_based import (
        pitch_yaw_roll_to_gaze_vector,
        rotation_matrix_to_euler_angles,
    )

    total_started = perf_counter()
    started = perf_counter()
    pitch, yaw, roll = rotation_matrix_to_euler_angles(facial_rt[:3, :3])
    _record(timings, "prepare_input.head_vector.matrix_conversion", started)
    started = perf_counter()
    head_vector = pitch_yaw_roll_to_gaze_vector(-yaw, pitch, roll)
    _record(timings, "prepare_input.head_vector.vector_calculation_and_normalization", started)
    _record(timings, "prepare_input.head_vector.total", total_started)
    return head_vector
