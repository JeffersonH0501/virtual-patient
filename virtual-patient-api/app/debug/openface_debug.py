"""Pure, in-memory single-frame OpenFace 3.0 debug extraction.

This module replaces the previous Py-Feat debug extractor. It runs OpenFace 3.0
over a single decoded image and returns the raw best-face detection values for
live display in the calibration debug tool. It never derives metrics, applies
thresholds, assigns labels, aggregates frames, or persists anything.

Unlike the per-turn extractor (``app/nonverbal/openface_extractor.py``), the
debug path also emits the STAR 68-point landmarks for the overlay, so it builds
the ``LandmarkDetector`` in addition to the RetinaFace ``FaceDetector`` and the
multitask AU/gaze head. The pure conversions and the weights-materialization /
non-writable-volume guard are reused from the turn extractor so both paths share
one Signal_Contract mapping and one CPU-only weights story.

OpenFace 3.0 API note (openface-test 0.1.26): ``FaceDetector.get_face(path)``
returns ``(crop, dets)`` where each ``dets`` row is
``[x1, y1, x2, y2, confidence, *retinaface_5pt]``; ``LandmarkDetector.detect_landmarks``
returns the 68 ``[x, y]`` points for a cropped face; and
``MultitaskPredictor.predict(crop)`` returns ``(emotion_logits, gaze, au)``. The
emotion logits are dropped at the model boundary (Descriptive_Contract, Req 4.8).
The detector decodes from a file path, so each frame is written to a short-lived
temporary image and removed immediately (nothing is persisted).
"""

from __future__ import annotations

import logging
import math
import os
import tempfile
import threading
import time
from typing import Any

from app.debug.schemas import ExtractorInfo, PyFeatFrameDebug
from app.nonverbal.openface_extractor import (
    AU12_INDEX,
    DEVICE,
    LANDMARK_WEIGHTS_FILENAME,
    MULTITASK_WEIGHTS_FILENAME,
    RETINAFACE_WEIGHTS_FILENAME,
    WEIGHTS_ROOT,
    OpenFaceExtractionError,
    _au12_activation,
    _gaze_pair,
    _materialize_weights,
    _redirect_star_logdir,
    _working_directory,
    adapt_face_observation,
    pair_star_landmarks,
)
from app.nonverbal.openface_extractor import (
    OpenFaceFaceObservation,
)


logger = logging.getLogger(__name__)

EXTRACTOR_NAME = "openface"
EXTRACTOR_VERSION = "3.0"
DETECTOR_NAME = "openface3-multitask"


class OpenFaceDebugUnavailable(RuntimeError):
    """Raised when OpenFace 3.0 cannot be imported or the models cannot be built.

    The router converts this into an HTTP 503 debug-unavailable response instead
    of letting the failure surface as a 500 stack trace.
    """


class OpenFaceDebugBusy(OpenFaceDebugUnavailable):
    """Raised when another live-debug frame is already using the models."""


_models: Any | None = None
# Serialize both model construction and detection. The OpenFace 3.0 models are
# not guaranteed thread-safe, and a low-FPS debug tool is fine running
# serialized.
_models_lock = threading.Lock()


class _DebugModels:
    """The OpenFace 3.0 components used by the single-frame debug path.

    Unlike the turn path, the debug path constructs the STAR
    ``LandmarkDetector`` so it can emit the 68-point overlay landmarks.
    """

    __slots__ = ("face_detector", "landmark_detector", "multitask_model")

    def __init__(self, face_detector: Any, landmark_detector: Any, multitask_model: Any) -> None:
        self.face_detector = face_detector
        self.landmark_detector = landmark_detector
        self.multitask_model = multitask_model


# Writable directory (inside the weights volume) that replaces STAR's hardcoded
# ``/work/...`` training checkpoint/log path. Only its ``log``/``model`` subdirs
# are touched by the TensorBoard SummaryWriter opened during construction; the
# landmark inference itself does not depend on this location.
def _get_models() -> _DebugModels:
    """Lazily build and cache the OpenFace 3.0 debug models on CPU.

    Weights are materialized first (failing fast on a non-writable volume via the
    shared turn-extractor guard, surfaced here as :class:`OpenFaceDebugUnavailable`),
    then RetinaFace, STAR landmarks, and the multitask head are constructed with
    ``device="cpu"`` and cached. Any import/construction failure is reported as
    :class:`OpenFaceDebugUnavailable`.
    """
    global _models
    if _models is not None:
        return _models
    with _models_lock:
        if _models is not None:
            return _models
        try:
            weights_root = _materialize_weights()
        except OpenFaceExtractionError as error:
            # Reuse the turn extractor's non-writable-volume / materialization
            # guard, surfacing it as debug-unavailable (design Error Handling).
            raise OpenFaceDebugUnavailable(str(error)) from error
        try:
            from openface.face_detection import FaceDetector
            from openface.landmark_detection import LandmarkDetector
            from openface.multitask_model import MultitaskPredictor
        except Exception as error:  # noqa: BLE001 - report any import failure uniformly
            raise OpenFaceDebugUnavailable(
                f"OpenFace 3.0 import failed: {error}"
            ) from error
        # STAR's config hardcodes a training checkpoint path ('/work/...') and,
        # on construction, opens a TensorBoard SummaryWriter under it, which
        # fails with PermissionError in the container. Redirect STAR's log/work
        # directories into the writable weights volume before building the
        # landmark detector (inference does not need the training logs).
        _redirect_star_logdir()
        try:
            # RetinaFace's backbone loads a hardcoded relative pretrain path, so
            # construction runs with the working directory temporarily set to the
            # weights volume (see the turn extractor). Always restored.
            with _working_directory(WEIGHTS_ROOT.parent):
                _models = _DebugModels(
                    face_detector=FaceDetector(
                        model_path=str(weights_root / RETINAFACE_WEIGHTS_FILENAME),
                        device=DEVICE,
                    ),
                    landmark_detector=LandmarkDetector(
                        model_path=str(weights_root / LANDMARK_WEIGHTS_FILENAME),
                        device=DEVICE,
                    ),
                    multitask_model=MultitaskPredictor(
                        model_path=str(weights_root / MULTITASK_WEIGHTS_FILENAME),
                        device=DEVICE,
                    ),
                )
        except Exception as error:  # noqa: BLE001 - construction may fail on bad weights
            raise OpenFaceDebugUnavailable(
                f"OpenFace 3.0 model construction failed: {error}"
            ) from error
    return _models


def detect_frame(
    image_bytes: bytes,
    *,
    frame_timestamp_ms: float | None,
) -> PyFeatFrameDebug:
    """Run single-image OpenFace 3.0 detection and return raw frame values.

    The image is decoded in memory with OpenCV; nothing is written to disk beyond
    a short-lived temporary frame consumed by the detector, and nothing is
    persisted. On a successful detection with at least one face, the
    best-confidence detection is used to populate the raw fields. When no face is
    detected the numeric fields stay null with a ``face_not_detected`` reason.

    The response model class name (``PyFeatFrameDebug``) is kept stable as a
    wire-contract identifier; only the extractor-identity values it carries name
    OpenFace 3.0.
    """
    start = time.perf_counter()
    extractor = ExtractorInfo(
        name=EXTRACTOR_NAME, version=EXTRACTOR_VERSION, detector=DETECTOR_NAME
    )

    try:
        import cv2
        import numpy as np
    except Exception as error:  # noqa: BLE001
        raise OpenFaceDebugUnavailable(f"OpenCV/NumPy import failed: {error}") from error

    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return PyFeatFrameDebug(
            face_detected=False,
            frame_timestamp_ms=frame_timestamp_ms,
            processing_ms=_elapsed_ms(start),
            extractor=extractor,
            reasons={"image": "image_decode_failed"},
        )
    image_height, image_width = int(image.shape[0]), int(image.shape[1])

    models = _get_models()
    # Never queue live-debug frames behind a running CPU inference. Returning a
    # transient busy response keeps the most recent observation on screen and
    # prevents multiple tabs from building an unbounded backlog.
    if not _models_lock.acquire(blocking=False):
        raise OpenFaceDebugBusy("OpenFace 3.0 models are processing another debug frame")
    try:
        observation, landmarks = _observe_single_frame(models, image, cv2)
    finally:
        _models_lock.release()

    if observation is None:
        return PyFeatFrameDebug(
            face_detected=False,
            image_width=image_width,
            image_height=image_height,
            frame_timestamp_ms=frame_timestamp_ms,
            processing_ms=_elapsed_ms(start),
            extractor=extractor,
            reasons={
                "face_score": "face_not_detected",
                "gaze_yaw": "face_not_detected",
                "gaze_pitch": "face_not_detected",
                "head_yaw": "face_not_detected",
                "head_pitch": "face_not_detected",
                "head_roll": "face_not_detected",
                "au12": "face_not_detected",
                "landmarks": "face_not_detected",
            },
        )

    candidate = adapt_face_observation(observation)
    reasons: dict[str, str] = {}
    for field in ("face_score", "gaze_yaw", "gaze_pitch", "au12", "head_pitch", "head_yaw", "head_roll"):
        if candidate[field] is None:
            # Head pose is not produced by the OpenFace 3.0 multitask model, so
            # its axes are reported as unavailable rather than fabricated.
            reasons[field] = "value_unavailable"
    if landmarks is None:
        reasons["landmarks"] = "landmarks_unavailable"

    return PyFeatFrameDebug(
        face_detected=True,
        face_score=candidate["face_score"],
        gaze_yaw=candidate["gaze_yaw"],
        gaze_pitch=candidate["gaze_pitch"],
        head_yaw=candidate["head_yaw"],
        head_pitch=candidate["head_pitch"],
        head_roll=candidate["head_roll"],
        au12=candidate["au12"],
        landmarks=landmarks,
        image_width=image_width,
        image_height=image_height,
        frame_timestamp_ms=frame_timestamp_ms,
        processing_ms=_elapsed_ms(start),
        extractor=extractor,
        reasons=reasons,
    )


def _observe_single_frame(
    models: _DebugModels,
    image: Any,
    cv2: Any,
) -> tuple[OpenFaceFaceObservation | None, list[list[float]] | None]:
    """Detect the best face and return its observation plus 68-point landmarks.

    Returns ``(None, None)`` when no face is detected. The detector decodes from
    a file path, so the already-decoded frame is written to a short-lived
    temporary image and removed immediately. Only detection confidence, gaze,
    AU12, and landmarks are read; the emotion logits from the multitask model are
    dropped at this boundary and never assigned, tracked, derived from, or logged
    (Req 4.8).
    """
    detections = _detect_faces(models.face_detector, image, cv2)
    if detections is None or len(detections) == 0:
        return None, None

    best_det = max(detections, key=lambda det: _to_float(det[4]) or -math.inf)
    confidence = _to_float(best_det[4])
    if confidence is None:
        return None, None

    crop = _crop_face(image, best_det)
    if crop is None or crop.size == 0:
        return None, None

    try:
        # (emotion_logits, gaze_output, au_output); emotion is dropped here.
        _, gaze_output, au_output = models.multitask_model.predict(crop)
    except Exception as error:  # noqa: BLE001 - a per-frame inference fault omits the frame
        logger.warning(
            "openface_debug_inference_failed error=%s",
            str(error).splitlines()[0] if str(error) else type(error).__name__,
        )
        return None, None

    landmarks = _detect_landmarks(models.landmark_detector, image, best_det)

    observation = OpenFaceFaceObservation(
        detection_confidence=confidence,
        gaze=_gaze_pair(gaze_output),
        # Head pose is not produced by the multitask model; reported unavailable.
        head_pose=None,
        au12_activation=_au12_activation(au_output),
        landmarks_xy=landmarks,
    )
    return observation, landmarks


def _detect_faces(face_detector: Any, image: Any, cv2: Any) -> Any:
    """Return the RetinaFace detections for one decoded frame as an ``ndarray``.

    ``FaceDetector`` decodes its input from a file path, so the frame is written
    to a short-lived temporary image, detected, and removed immediately. Returns
    ``None`` when detection is unavailable for the frame.
    """
    tmp = tempfile.NamedTemporaryFile(
        prefix="virtual-patient-openface-debug-", suffix=".png", delete=False
    )
    tmp_path = tmp.name
    tmp.close()
    try:
        if not cv2.imwrite(tmp_path, image):
            raise OpenFaceDebugUnavailable("Failed to buffer the debug frame for detection")
        _, detections = face_detector.get_face(tmp_path)
        return detections
    except OpenFaceDebugUnavailable:
        raise
    except Exception as error:  # noqa: BLE001 - any detection fault is debug-unavailable
        raise OpenFaceDebugUnavailable(
            f"OpenFace 3.0 detection failed: {error}"
        ) from error
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _detect_landmarks(landmark_detector: Any, image: Any, det: Any) -> list[list[float]] | None:
    """Run STAR landmark detection for the best face, returning ``[x, y]`` points.

    OpenFace 3.0's ``LandmarkDetector.detect_landmarks(image, dets)`` takes the
    **full frame** plus the detection rows and returns one landmark set per
    detection **already in full-image pixel coordinates** (the STAR model emits
    the 98-point WFLW set). We pass only the best detection row so a single set is
    returned, pair it via the shared :func:`pair_star_landmarks` helper, and
    return it without any offset (coordinates are already frame-relative). No
    coordinate reinterpretation is applied, so the overlay renders in the original
    image space (Req 2.2, 8.4). Returns ``None`` when landmarks are unavailable
    (never fabricated).
    """
    import numpy as np

    try:
        raw = landmark_detector.detect_landmarks(image, np.asarray([det]))
    except Exception as error:  # noqa: BLE001 - landmark failure -> unavailable, not fatal
        logger.warning(
            "openface_debug_landmarks_failed error=%s",
            str(error).splitlines()[0] if str(error) else type(error).__name__,
        )
        return None
    # detect_landmarks returns one landmark set per detection; we passed one.
    try:
        first = raw[0]
    except (TypeError, IndexError):
        return None
    return pair_star_landmarks(first)


def _crop_face(image: Any, det: Any) -> Any:
    """Crop the face box ``det[:4]`` from ``image``, clamped to frame bounds."""
    height = image.shape[0]
    width = image.shape[1]
    x1 = max(int(det[0]), 0)
    y1 = max(int(det[1]), 0)
    x2 = min(int(det[2]), width)
    y2 = min(int(det[3]), height)
    if x2 <= x1 or y2 <= y1:
        return None
    return image[y1:y2, x1:x2]


def _to_float(value: Any) -> float | None:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)
