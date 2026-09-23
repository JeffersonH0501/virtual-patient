"""Backend-only BlazeGaze inference over shared MediaPipe observations.

The adapter follows WebEyeTrack commit 75fbd2f5f784f2eb3a39675a8dcbf1b01c697f1c
and deliberately calls ``step`` with existing landmarks and pose. It never calls
WebEyeTrack's ``process_frame`` and therefore never runs a second Face Landmarker.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from types import MethodType
from typing import Any
import sys

import numpy as np

from app.nonverbal.shared_observations import SharedFrameObservation

MODEL_PATH = Path(__file__).with_name("models") / "blazegaze_mpiifacegaze.keras"
CALIBRATION_STATE = "identity_calibration"
ALIGNMENT_UNAVAILABLE_REASON = "gaze_calibration_pending"
GAZE_BATCH_SIZE = 16


def create_batch_buffers(batch_size: int = GAZE_BATCH_SIZE) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Allocate one video-local set of float32 BlazeGaze input buffers."""
    return (
        np.empty((batch_size, 128, 512, 3), dtype=np.float32),
        np.empty((batch_size, 3), dtype=np.float32),
        np.empty((batch_size, 3), dtype=np.float32),
    )


def package_blazegaze_inputs(
    prepared: list[tuple[int, np.ndarray, np.ndarray, np.ndarray]],
    buffers: tuple[np.ndarray, np.ndarray, np.ndarray],
    timings: dict[str, list[float]] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fill reusable float32 buffers with tensors identical to the old route."""
    count = len(prepared)
    image_buffer, head_buffer, origin_buffer = buffers
    started = perf_counter()
    stacked_images = np.stack([item[1] for item in prepared])
    if timings is not None:
        timings.setdefault("blazegaze_packaging.image_stack", []).append(
            (perf_counter() - started) * 1000
        )
    started = perf_counter()
    np.divide(stacked_images, 255.0, out=image_buffer[:count], casting="unsafe")
    if timings is not None:
        timings.setdefault("blazegaze_packaging.image_normalize_float32", []).append(
            (perf_counter() - started) * 1000
        )
    started = perf_counter()
    head_buffer[:count] = np.stack([item[2] for item in prepared])
    if timings is not None:
        timings.setdefault("blazegaze_packaging.head_stack", []).append(
            (perf_counter() - started) * 1000
        )
    started = perf_counter()
    origin_buffer[:count] = np.stack([item[3] for item in prepared])
    if timings is not None:
        timings.setdefault("blazegaze_packaging.origin_stack", []).append(
            (perf_counter() - started) * 1000
        )
    return image_buffer[:count], head_buffer[:count], origin_buffer[:count]


def _ensure_upstream_import_compatibility() -> None:
    """Bridge WebEyeTrack's legacy import to the pinned MediaPipe package."""
    import mediapipe

    sys.modules.setdefault("mediapipe.python", mediapipe)


@dataclass(frozen=True)
class GazeObservation:
    timestamp_ms: float
    valid: bool
    state: str
    unclipped_x: float | None = None
    unclipped_y: float | None = None
    display_x: float | None = None
    display_y: float | None = None


def create_tracker(
    *,
    affine_matrix: Any | None = None,
    kalman_enabled: bool = True,
    timings: dict[str, list[float]] | None = None,
) -> Any:
    """Create WebEyeTrack without constructing its private Face Landmarker."""
    _ensure_upstream_import_compatibility()
    started = perf_counter()
    import tensorflow  # noqa: F401 - explicit import boundary for startup profiling
    if timings is not None:
        timings.setdefault("startup.tensorflow_import", []).append((perf_counter() - started) * 1000)
    started = perf_counter()
    from webeyetrack.blazegaze import BlazeGaze, BlazeGazeConfig
    from webeyetrack.filter import KalmanFilter2D
    from webeyetrack.webeyetrack import WebEyeTrack, WebEyeTrackConfig
    if timings is not None:
        timings.setdefault("startup.webeyetrack_imports", []).append((perf_counter() - started) * 1000)

    started = perf_counter()
    tracker = WebEyeTrack.__new__(WebEyeTrack)
    tracker.config = WebEyeTrackConfig(blazegaze_mlp_fp=MODEL_PATH)
    if timings is not None:
        timings.setdefault("startup.webeyetrack_configuration", []).append((perf_counter() - started) * 1000)
    started = perf_counter()
    tracker.blazegaze = BlazeGaze(BlazeGazeConfig(weights_fp=MODEL_PATH))
    if timings is not None:
        timings.setdefault("startup.blazegaze_construction_and_weights_load", []).append((perf_counter() - started) * 1000)
    started = perf_counter()
    reset_tracker(
        tracker,
        affine_matrix=affine_matrix,
        kalman_enabled=kalman_enabled,
        kalman_filter_class=KalmanFilter2D,
    )
    if timings is not None:
        timings.setdefault("startup.webeyetrack_remaining_construction", []).append((perf_counter() - started) * 1000)
    from app.nonverbal.webeyetrack_profiling import prepare_input as optimized_prepare_input

    tracker.prepare_input = MethodType(optimized_prepare_input, tracker)

    import tensorflow as tf

    @tf.function(
        input_signature=[
            tf.TensorSpec([None, 128, 512, 3], tf.float32),
            tf.TensorSpec([None, 3], tf.float32),
            tf.TensorSpec([None, 3], tf.float32),
        ]
    )
    def batched_infer_fn(image: Any, head_vector: Any, face_origin_3d: Any):
        return tracker.blazegaze.model(
            {
                "image": image,
                "head_vector": head_vector,
                "face_origin_3d": face_origin_3d,
            }
        )

    tracker.batched_infer_fn = batched_infer_fn
    return tracker


def reset_tracker(
    tracker: Any,
    *,
    affine_matrix: Any | None = None,
    kalman_enabled: bool = True,
    kalman_filter_class: Any | None = None,
) -> Any:
    """Reset video-local state while retaining the loaded BlazeGaze model."""
    if kalman_filter_class is None:
        _ensure_upstream_import_compatibility()
        from webeyetrack.filter import KalmanFilter2D

        kalman_filter_class = KalmanFilter2D
    tracker.kalman_filter = kalman_filter_class(
        dt=tracker.config.kalman_config.dt,
        process_noise=tracker.config.kalman_config.process_noise,
        measurement_noise=tracker.config.kalman_config.measurement_noise,
    )
    tracker.config.kalman_config.enabled = kalman_enabled
    tracker.face_width_cm = None
    tracker.intrinsics = None
    tracker._perspective_geometry_cache = None
    tracker._optimization_counters = None
    tracker.affine_matrix = (
        None if affine_matrix is None else np.asarray(affine_matrix, dtype=float)
    )
    if tracker.affine_matrix is not None and (
        tracker.affine_matrix.shape != (2, 3)
        or not np.isfinite(tracker.affine_matrix).all()
    ):
        raise ValueError("WebEyeTrack affine profile must be a finite 2x3 matrix")
    return tracker


def _landmarks_array(landmarks: Any) -> np.ndarray:
    return np.asarray(
        [[point.x, point.y, point.z, getattr(point, "visibility", 0.0) or 0.0,
          getattr(point, "presence", 0.0) or 0.0] for point in landmarks],
        dtype=np.float32,
    )


def extract_gaze(observation: SharedFrameObservation, tracker: Any, timings: dict[str, list[float]] | None = None) -> GazeObservation:
    if not observation.face_valid:
        return GazeObservation(observation.timestamp_ms, False, "face_unavailable")
    if observation.facial_transformation_matrix is None:
        return GazeObservation(observation.timestamp_ms, False, "pose_unavailable")

    _ensure_upstream_import_compatibility()
    from webeyetrack.data_protocols import TrackingStatus

    tracker_args = (
        observation.frame,
        _landmarks_array(observation.landmarks),
        np.asarray(observation.facial_transformation_matrix, dtype=np.float32),
    )
    upstream_durations: dict[str, float] = {}
    if timings is not None:
        from app.nonverbal.webeyetrack_profiling import (
            profile_inference_call,
            profile_tracker_prepare_input,
        )

        with profile_tracker_prepare_input(tracker, timings), profile_inference_call(
            tracker, timings
        ):
            status, result = tracker.step(*tracker_args, durations=upstream_durations)
    else:
        status, result = tracker.step(*tracker_args)
    if timings is not None:
        for name, seconds in upstream_durations.items():
            timings.setdefault(f"webeyetrack_{name.replace('&', 'and')}", []).append(float(seconds) * 1000)
        if upstream_durations.get("infer_pog") is not None:
            model_ms = timings.get("webeyetrack_model_call", [0.0])[-1]
            infer_ms = float(upstream_durations["infer_pog"]) * 1000.0
            timings.setdefault("webeyetrack_tensor_packaging_and_dispatch", []).append(
                max(0.0, infer_ms - model_ms)
            )
    if status != TrackingStatus.SUCCESS or result is None:
        return GazeObservation(observation.timestamp_ms, False, "inference_failed")
    if result.gaze_state != "open":
        return GazeObservation(observation.timestamp_ms, False, "eyes_closed")

    point = np.asarray(result.norm_pog, dtype=float).reshape(2)
    if not np.isfinite(point).all():
        return GazeObservation(observation.timestamp_ms, False, "non_finite_output")
    x, y = float(point[0]), float(point[1])
    return GazeObservation(
        observation.timestamp_ms, True, CALIBRATION_STATE, x, y,
        float(np.clip(x, -0.5, 0.5)), float(np.clip(y, -0.5, 0.5)),
    )


def extract_gaze_batch(
    observations: list[SharedFrameObservation],
    tracker: Any,
    timings: dict[str, list[float]] | None = None,
    batch_buffers: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
) -> list[GazeObservation]:
    """Batch only frame-independent BlazeGaze inference; postprocess in order."""
    import tensorflow as tf
    from webeyetrack.model_based import compute_ear

    from app.nonverbal.webeyetrack_profiling import prepare_input

    results: list[GazeObservation | None] = [None] * len(observations)
    prepared: list[tuple[int, np.ndarray, np.ndarray, np.ndarray]] = []
    for index, observation in enumerate(observations):
        if not observation.face_valid:
            results[index] = GazeObservation(
                observation.timestamp_ms, False, "face_unavailable"
            )
            continue
        if observation.facial_transformation_matrix is None:
            results[index] = GazeObservation(
                observation.timestamp_ms, False, "pose_unavailable"
            )
            continue
        landmarks = _landmarks_array(observation.landmarks)
        facial_rt = np.asarray(
            observation.facial_transformation_matrix, dtype=np.float32
        )
        started = perf_counter()
        try:
            if timings is None:
                eye_patch, head_vector, face_origin = tracker.prepare_input(
                    observation.frame, landmarks, facial_rt
                )
            else:
                eye_patch, head_vector, face_origin = prepare_input(
                    tracker, observation.frame, landmarks, facial_rt, timings
                )
                timings.setdefault("webeyetrack_prepare_input", []).append(
                    (perf_counter() - started) * 1000
                )
        except Exception:
            results[index] = GazeObservation(
                observation.timestamp_ms, False, "inference_failed"
            )
            continue
        face_landmarks_2d = landmarks[:, :2] * np.array(
            [observation.frame.shape[1], observation.frame.shape[0]]
        )
        if (
            compute_ear(face_landmarks_2d, side="left")
            < tracker.config.ear_threshold
            or compute_ear(face_landmarks_2d, side="right")
            < tracker.config.ear_threshold
        ):
            results[index] = GazeObservation(
                observation.timestamp_ms, False, "eyes_closed"
            )
            continue
        prepared.append((index, eye_patch, head_vector, face_origin))

    if prepared:
        packaging_started = perf_counter()
        image_numpy, head_numpy, origin_numpy = package_blazegaze_inputs(
            prepared, batch_buffers or create_batch_buffers(), timings
        )
        started = perf_counter()
        images = tf.convert_to_tensor(image_numpy, dtype=tf.float32)
        if timings is not None:
            timings.setdefault("blazegaze_packaging.image_tensor_conversion", []).append(
                (perf_counter() - started) * 1000
            )
        started = perf_counter()
        head_vectors = tf.convert_to_tensor(head_numpy, dtype=tf.float32)
        if timings is not None:
            timings.setdefault("blazegaze_packaging.head_tensor_conversion", []).append(
                (perf_counter() - started) * 1000
            )
        started = perf_counter()
        face_origins = tf.convert_to_tensor(origin_numpy, dtype=tf.float32)
        if timings is not None:
            timings.setdefault("blazegaze_packaging.origin_tensor_conversion", []).append(
                (perf_counter() - started) * 1000
            )
        packaging_ms = (perf_counter() - packaging_started) * 1000
        inference_started = perf_counter()
        prediction_tensor = tracker.batched_infer_fn(
            images, head_vectors, face_origins
        )
        model_dispatch_ms = (perf_counter() - inference_started) * 1000
        output_started = perf_counter()
        predictions = prediction_tensor.numpy()
        output_numpy_ms = (perf_counter() - output_started) * 1000
        inference_ms = (perf_counter() - inference_started) * 1000
        counters = tracker._optimization_counters
        counters.setdefault("blazegaze_batches", 0)
        counters.setdefault("blazegaze_samples", 0)
        counters.setdefault("blazegaze_max_batch_size", 0)
        counters["blazegaze_batches"] += 1
        counters["blazegaze_samples"] += len(prepared)
        counters["blazegaze_max_batch_size"] = max(
            counters["blazegaze_max_batch_size"], len(prepared)
        )
        counters["blazegaze_tf_traces"] = (
            tracker.batched_infer_fn.experimental_get_tracing_count()
        )
        if timings is not None:
            first_batch = len(timings.get("blazegaze_batch_inference", [])) == 0
            if first_batch:
                timings.setdefault(
                    "startup.tensorflow_first_trace_and_batch_inference", []
                ).append(inference_ms)
            timings.setdefault("blazegaze_batch_packaging", []).append(packaging_ms)
            timings.setdefault("blazegaze_batch_inference", []).append(inference_ms)
            timings.setdefault("blazegaze_model_dispatch", []).append(model_dispatch_ms)
            timings.setdefault("blazegaze_output_to_numpy", []).append(output_numpy_ms)
            timings.setdefault("blazegaze_inference_per_sample", []).extend(
                [inference_ms / len(prepared)] * len(prepared)
            )
            if not first_batch:
                timings.setdefault(
                    "blazegaze_inference_per_sample_steady", []
                ).extend([inference_ms / len(prepared)] * len(prepared))

        for (index, _, _, _), prediction in zip(prepared, predictions):
            postprocess_started = perf_counter()
            if tracker.affine_matrix is not None:
                point = tracker.affine_matrix @ np.append(prediction, 1.0)
            else:
                point = np.asarray(prediction)
            point = np.asarray([float(point[0]), float(point[1])])
            if tracker.config.kalman_config.enabled:
                point = tracker.kalman_filter.step(point).flatten()
            if timings is not None:
                timings.setdefault("webeyetrack_affine_and_kalman", []).append(
                    (perf_counter() - postprocess_started) * 1000
                )
            x, y = float(point[0]), float(point[1])
            observation = observations[index]
            results[index] = GazeObservation(
                observation.timestamp_ms,
                True,
                CALIBRATION_STATE,
                x,
                y,
                float(np.clip(x, -0.5, 0.5)),
                float(np.clip(y, -0.5, 0.5)),
            )

    return [
        result
        if result is not None
        else GazeObservation(observations[index].timestamp_ms, False, "inference_failed")
        for index, result in enumerate(results)
    ]


def visual_alignment_unavailable() -> dict[str, str | None]:
    """Keep alignment metrics unavailable until participant calibration exists."""
    return {
        "visual_alignment_ratio": None,
        "visual_alignment_mean": None,
        "reason": ALIGNMENT_UNAVAILABLE_REASON,
    }
