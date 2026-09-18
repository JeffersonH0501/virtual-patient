"""Single-pass server-side MediaPipe Face Landmarker extraction."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, Iterator

from app.nonverbal.shared_observations import SharedFrameObservation


MODEL_PATH = Path(__file__).with_name("models") / "face_landmarker_v2_with_blendshapes.task"
EXTRACTOR_NAME = "mediapipe_face_landmarker"
EXTRACTOR_VERSION = "1.0.1"


def create_face_landmarker(
    model_path: Path = MODEL_PATH,
    timings: dict[str, list[float]] | None = None,
) -> Any:
    started = perf_counter()
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    if timings is not None:
        timings.setdefault("startup.mediapipe_imports", []).append((perf_counter() - started) * 1000)

    options = vision.FaceLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.VIDEO,
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

    detector = landmarker or create_face_landmarker()
    owns_detector = landmarker is None
    started = perf_counter()
    capture = cv2.VideoCapture(str(video_path))
    if timings is not None:
        timings.setdefault("startup.video_open", []).append((perf_counter() - started) * 1000)
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    if source_fps <= 0:
        raise RuntimeError("Video has no usable frame rate")
    next_sample_ms = 0.0
    try:
        while True:
            started = perf_counter()
            ok, frame = capture.read()
            if timings is not None:
                timings.setdefault("video_decode", []).append((perf_counter() - started) * 1000)
            if not ok:
                break
            timestamp_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
            if timestamp_ms + 1e-6 < next_sample_ms:
                continue
            next_sample_ms = timestamp_ms + 1000.0 / sample_fps
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
            yield observation_from_result(timestamp_ms, frame, result, timings)
    finally:
        cleanup_started = perf_counter()
        capture.release()
        if owns_detector:
            detector.close()
        if timings is not None:
            timings.setdefault("video_cleanup", []).append(
                (perf_counter() - cleanup_started) * 1000
            )
