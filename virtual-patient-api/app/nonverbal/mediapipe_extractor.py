"""Single-pass server-side MediaPipe Face Landmarker extraction."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, Iterator

from app.nonverbal.shared_observations import SharedFrameObservation


MODEL_PATH = Path(__file__).with_name("models") / "face_landmarker_v2_with_blendshapes.task"
EXTRACTOR_NAME = "mediapipe_face_landmarker"
EXTRACTOR_VERSION = "1.0.1"


def create_face_landmarker(model_path: Path = MODEL_PATH) -> Any:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    options = vision.FaceLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.VIDEO,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
        num_faces=1,
    )
    return vision.FaceLandmarker.create_from_options(options)


def observation_from_result(timestamp_ms: float, frame: Any, result: Any) -> SharedFrameObservation:
    if not result.face_landmarks:
        return SharedFrameObservation(timestamp_ms, frame, False, reason="face_not_detected")
    landmarks = result.face_landmarks[0]
    categories = result.face_blendshapes[0] if result.face_blendshapes else []
    blendshapes = {item.category_name: float(item.score) for item in categories}
    matrix = result.facial_transformation_matrixes[0] if result.facial_transformation_matrixes else None
    return SharedFrameObservation(timestamp_ms, frame, True, landmarks, blendshapes, matrix)


def extract_video(video_path: Path, *, sample_fps: float = 10.0, landmarker: Any | None = None, timings: dict[str, list[float]] | None = None) -> Iterator[SharedFrameObservation]:
    """Decode once and invoke Face Landmarker exactly once per yielded frame."""
    import cv2
    import mediapipe as mp

    detector = landmarker or create_face_landmarker()
    owns_detector = landmarker is None
    capture = cv2.VideoCapture(str(video_path))
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
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            if timings is not None:
                timings.setdefault("frame_conversion", []).append((perf_counter() - started) * 1000)
            started = perf_counter()
            result = detector.detect_for_video(image, int(round(timestamp_ms)))
            if timings is not None:
                timings.setdefault("mediapipe_face_landmarker", []).append((perf_counter() - started) * 1000)
            yield observation_from_result(timestamp_ms, frame, result)
    finally:
        capture.release()
        if owns_detector:
            detector.close()
