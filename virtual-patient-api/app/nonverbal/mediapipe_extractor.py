"""Single-pass server-side MediaPipe Face Landmarker extraction."""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from math import floor, isfinite
import hashlib
from time import perf_counter
from typing import Any, Iterator

from app.nonverbal.shared_observations import SharedFrameObservation


MODEL_PATH = Path(__file__).with_name("models") / "face_landmarker_v2_with_blendshapes.task"
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
EXTRACTOR_NAME = "mediapipe_face_landmarker"
EXTRACTOR_VERSION = "1.2.1_duplicate_pts"


def create_face_landmarker(
    model_path: Path = MODEL_PATH,
    timings: dict[str, list[float]] | None = None,
    *, image_mode: bool = False,
) -> Any:
    started = perf_counter()
    with model_path.open("rb") as artifact:
        if hashlib.file_digest(artifact, "sha256").hexdigest() != MODEL_SHA256:
            raise ValueError("MediaPipe model SHA-256 mismatch")
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    if timings is not None:
        timings.setdefault("startup.mediapipe_imports", []).append((perf_counter() - started) * 1000)

    options = vision.FaceLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.IMAGE if image_mode else vision.RunningMode.VIDEO,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
        num_faces=1,
    )
    started = perf_counter()
    landmarker = vision.FaceLandmarker.create_from_options(options)
    if timings is not None:
        timings.setdefault("startup.mediapipe_model_load_and_landmarker_creation", []).append((perf_counter() - started) * 1000)
    return landmarker


def observation_from_result(
    timestamp_ms: float,
    frame: Any,
    result: Any,
    timings: dict[str, list[float]] | None = None,
) -> SharedFrameObservation:
    started = perf_counter()
    height, width = frame.shape[:2] if frame is not None else (None, None)
    pixels = frame[::8, ::8] if frame is not None and frame.size else None
    brightness = float(pixels.mean()) if pixels is not None else None
    contrast = float(pixels.std()) if pixels is not None else None
    access_started = perf_counter()
    if not result.face_landmarks:
        if timings is not None:
            timings.setdefault("mediapipe.result_access", []).append(
                (perf_counter() - access_started) * 1000
            )
            timings.setdefault("mediapipe.shared_observation_construction", []).append(
                (perf_counter() - started) * 1000
            )
        return SharedFrameObservation(
            timestamp_ms, frame, False, reason="face_not_detected",
            frame_width=width, frame_height=height,
            frame_brightness_mean=brightness, frame_brightness_std=contrast,
        )
    landmarks = result.face_landmarks[0]
    categories = result.face_blendshapes[0] if result.face_blendshapes else []
    matrix = result.facial_transformation_matrixes[0] if result.facial_transformation_matrixes else None
    if timings is not None:
        timings.setdefault("mediapipe.result_access", []).append(
            (perf_counter() - access_started) * 1000
        )
    conversion_started = perf_counter()
    blendshapes = {item.category_name: float(item.score) for item in categories}
    if timings is not None:
        timings.setdefault("mediapipe.result_conversion", []).append(
            (perf_counter() - conversion_started) * 1000
        )
    observation = SharedFrameObservation(
        timestamp_ms, frame, True, landmarks, blendshapes, matrix,
        frame_width=width, frame_height=height,
        frame_brightness_mean=brightness, frame_brightness_std=contrast,
    )
    if timings is not None:
        timings.setdefault("mediapipe.shared_observation_construction", []).append(
            (perf_counter() - started) * 1000
        )
    return observation


def extract_video(video_path: Path, *, sample_fps: float = 10.0, landmarker: Any | None = None, timings: dict[str, list[float]] | None = None) -> Iterator[SharedFrameObservation]:
    """Decode once and invoke Face Landmarker exactly once per yielded frame."""
    import cv2
    import mediapipe as mp

    if not isfinite(sample_fps) or sample_fps <= 0:
        raise ValueError("Sampling frame rate must be finite and positive")
    detector = landmarker or create_face_landmarker()
    owns_detector = landmarker is None
    started = perf_counter()
    capture = None
    next_sample_ms = 0.0
    previous_frame_ms = None
    try:
        capture = cv2.VideoCapture(str(video_path))
        if timings is not None:
            timings.setdefault("startup.video_open", []).append((perf_counter() - started) * 1000)
        source_fps = capture.get(cv2.CAP_PROP_FPS)
        if not isfinite(source_fps) or source_fps <= 0:
            raise RuntimeError("Video has no usable frame rate")
        sample_interval_ms = 1000.0 / sample_fps
        frame_step_ms = 1000.0 / source_fps
        while True:
            started = perf_counter()
            ok, frame = capture.read()
            if timings is not None:
                timings.setdefault("video_decode", []).append((perf_counter() - started) * 1000)
            if not ok:
                break
            timestamp_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
            if not isfinite(timestamp_ms) or (previous_frame_ms is not None and timestamp_ms < previous_frame_ms):
                raise RuntimeError("Video frame timestamps must be finite and strictly increasing")
            # Browser recordings can contain duplicate PTS at pause/resume boundaries.
            if previous_frame_ms is not None and timestamp_ms == previous_frame_ms:
                continue
            if previous_frame_ms is not None:
                decoded_step_ms = timestamp_ms - previous_frame_ms
                # Quantization follows decoded PTS; a source gap longer than the
                # sampling interval must not teach the interpolator to bridge it.
                if decoded_step_ms <= max(sample_interval_ms, 1000.0 / source_fps):
                    frame_step_ms = max(frame_step_ms, decoded_step_ms)
            previous_frame_ms = timestamp_ms
            if timestamp_ms + 1e-6 < next_sample_ms:
                continue
            next_sample_ms = (floor((timestamp_ms + 1e-6) / sample_interval_ms) + 1) * sample_interval_ms
            started = perf_counter()
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            if timings is not None:
                timings.setdefault("frame_conversion.bgr_to_rgb", []).append(
                    (perf_counter() - started) * 1000
                )
                timings.setdefault("frame_conversion.rgb_contiguous", []).append(
                    float(rgb.flags.c_contiguous)
                )
            started = perf_counter()
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            if timings is not None:
                image_ms = (perf_counter() - started) * 1000
                timings.setdefault("frame_conversion.mp_image", []).append(image_ms)
                timings.setdefault("frame_conversion", []).append(
                    timings["frame_conversion.bgr_to_rgb"][-1] + image_ms
                )
            started = perf_counter()
            timestamp = int(round(timestamp_ms))
            if timings is not None:
                timings.setdefault("mediapipe.timestamp_preparation", []).append(
                    (perf_counter() - started) * 1000
                )
            started = perf_counter()
            result = detector.detect_for_video(image, timestamp)
            if timings is not None:
                timings.setdefault("mediapipe_face_landmarker", []).append((perf_counter() - started) * 1000)
            yield replace(observation_from_result(timestamp_ms, frame, result, timings),
                          sampling_max_gap_ms=min(200.0, sample_interval_ms + frame_step_ms),
                          source_fps=source_fps)
    finally:
        cleanup_started = perf_counter()
        try:
            if capture is not None:
                capture.release()
        finally:
            if owns_detector:
                detector.close()
        if timings is not None:
            timings.setdefault("video_cleanup", []).append(
                (perf_counter() - cleanup_started) * 1000
            )
