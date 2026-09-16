"""Pure, in-memory single-frame Py-Feat debug extraction.

This module runs Py-Feat over a single decoded image and returns the raw
best-face detection values for live display in the calibration debug tool. It
never derives metrics, applies thresholds, assigns labels, aggregates frames, or
persists anything.

Detector API note (grounded against Py-Feat 2.1.1 / Detectorv2 docs; the package
was not importable in the development environment when this module was written,
so the detector call is written defensively): ``Detectorv2.detect`` is a single
method whose ``data_type`` argument selects the input mode. For a single image
it is called as ``detector.detect(inputs, data_type="image", ...)``. Landmark
columns are read dynamically via regex (``x_<n>`` / ``y_<n>``) so the exact
detector-native landmark naming is discovered at runtime instead of hard-coded.
"""

from __future__ import annotations

import math
import os
import re
import tempfile
import threading
import time
from typing import Any

from app.debug.schemas import ExtractorInfo, PyFeatFrameDebug
from app.nonverbal.pyfeat_extractor import (
    FACE_DETECTION_THRESHOLD,
    WEIGHTS_ROOT,
    _prepare_torch_device,
)


EXTRACTOR_NAME = "py-feat"
EXTRACTOR_VERSION = "2.1.1"
DETECTOR_NAME = "Detectorv2"

# Real Py-Feat best-face row columns (same set the production extractor reads).
FACE_SCORE_COLUMN = "FaceScore"
GAZE_YAW_COLUMN = "gaze_yaw"
GAZE_PITCH_COLUMN = "gaze_pitch"
AU12_COLUMN = "AU12"
HEAD_PITCH_COLUMN = "Pitch"
HEAD_YAW_COLUMN = "Yaw"
HEAD_ROLL_COLUMN = "Roll"

# Landmark columns are discovered dynamically to stay robust across Py-Feat
# builds (68-point classic landmarks are exposed as x_0..x_67 / y_0..y_67).
_LANDMARK_X_PATTERN = re.compile(r"^x_(\d+)$")
_LANDMARK_Y_PATTERN = re.compile(r"^y_(\d+)$")


class PyFeatDebugUnavailable(RuntimeError):
    """Raised when Py-Feat cannot be imported or the detector cannot be built.

    The router converts this into an HTTP 503 debug-unavailable response instead
    of letting the failure surface as a 500 stack trace.
    """


class PyFeatDebugBusy(PyFeatDebugUnavailable):
    """Raised when another live-debug frame is already using Detectorv2."""


_detector: Any | None = None
# Serialize both detector construction and detection. Detectorv2 is not
# guaranteed thread-safe, and a low-FPS debug tool is fine running serialized.
_detector_lock = threading.Lock()


def _get_detector() -> Any:
    """Lazily build and cache a single Detectorv2 instance.

    The resource path is patched exactly like the production extractor before
    the detector is constructed. Construction happens once and is reused across
    calls. Raises :class:`PyFeatDebugUnavailable` if Py-Feat is missing or the
    model cannot be created.
    """
    global _detector
    if _detector is not None:
        return _detector
    with _detector_lock:
        if _detector is not None:
            return _detector
        try:
            import feat.utils.io as feat_io
            import torch
            from feat import Detectorv2
        except Exception as error:  # noqa: BLE001 - report any import failure uniformly
            raise PyFeatDebugUnavailable(f"Py-Feat import failed: {error}") from error
        try:
            WEIGHTS_ROOT.mkdir(parents=True, exist_ok=True)
            feat_io.get_resource_path = lambda: str(WEIGHTS_ROOT)
            _detector = Detectorv2(device=_prepare_torch_device(torch))
        except Exception as error:  # noqa: BLE001 - construction may fail on missing weights
            raise PyFeatDebugUnavailable(
                f"Py-Feat detector construction failed: {error}"
            ) from error
    return _detector


def detect_frame(
    image_bytes: bytes,
    *,
    frame_timestamp_ms: float | None,
) -> PyFeatFrameDebug:
    """Run single-image Py-Feat detection and return raw frame values.

    The image is decoded in memory with OpenCV; nothing is written to disk and
    nothing is persisted. On a successful detection with at least one face, the
    best-``FaceScore`` row is used to populate the raw fields. When no face is
    detected the numeric fields stay null with a ``face_not_detected`` reason.
    """
    start = time.perf_counter()
    extractor = ExtractorInfo(
        name=EXTRACTOR_NAME, version=EXTRACTOR_VERSION, detector=DETECTOR_NAME
    )

    try:
        import cv2
        import numpy as np
    except Exception as error:  # noqa: BLE001
        raise PyFeatDebugUnavailable(f"OpenCV/NumPy import failed: {error}") from error

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

    detector = _get_detector()
    # Never queue live-debug frames behind a running CPU inference. Returning a
    # transient busy response keeps the most recent observation on screen and
    # prevents multiple tabs from building an unbounded detector backlog.
    if not _detector_lock.acquire(blocking=False):
        raise PyFeatDebugBusy("Py-Feat detector is processing another debug frame")
    try:
        fex = _detect_single_image(detector, image, cv2)
    finally:
        _detector_lock.release()

    best_row = _best_face_row(fex)
    if best_row is None:
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

    reasons: dict[str, str] = {}
    face_score = _cell(best_row, FACE_SCORE_COLUMN, reasons, "face_score")
    gaze_yaw = _cell(best_row, GAZE_YAW_COLUMN, reasons, "gaze_yaw")
    gaze_pitch = _cell(best_row, GAZE_PITCH_COLUMN, reasons, "gaze_pitch")
    head_yaw = _cell(best_row, HEAD_YAW_COLUMN, reasons, "head_yaw")
    head_pitch = _cell(best_row, HEAD_PITCH_COLUMN, reasons, "head_pitch")
    head_roll = _cell(best_row, HEAD_ROLL_COLUMN, reasons, "head_roll")
    au12 = _cell(best_row, AU12_COLUMN, reasons, "au12")
    landmarks = _extract_landmarks(best_row)
    if landmarks is None:
        reasons["landmarks"] = "landmarks_unavailable"

    return PyFeatFrameDebug(
        face_detected=True,
        face_score=face_score,
        gaze_yaw=gaze_yaw,
        gaze_pitch=gaze_pitch,
        head_yaw=head_yaw,
        head_pitch=head_pitch,
        head_roll=head_roll,
        au12=au12,
        landmarks=landmarks,
        image_width=image_width,
        image_height=image_height,
        frame_timestamp_ms=frame_timestamp_ms,
        processing_ms=_elapsed_ms(start),
        extractor=extractor,
        reasons=reasons,
    )


def _detect_single_image(detector: Any, image: Any, cv2: Any) -> Any:
    """Run single-image Py-Feat detection on one decoded frame.

    Py-Feat 2.1.1 ``Detectorv2.detect(..., data_type="image")`` reads its input
    from a file path (an in-memory ``ndarray`` is rejected with
    ``'numpy.ndarray' object has no attribute 'read'``). We therefore write the
    already-decoded frame to a short-lived temporary PNG, run detection on that
    path, and delete the file immediately afterwards — so nothing is persisted
    while still using the extractor's supported API.
    """
    tmp = tempfile.NamedTemporaryFile(
        prefix="virtual-patient-debug-frame-", suffix=".png", delete=False
    )
    tmp_path = tmp.name
    tmp.close()
    try:
        if not cv2.imwrite(tmp_path, image):
            raise PyFeatDebugUnavailable("Failed to buffer the debug frame for detection")
        try:
            return detector.detect(
                tmp_path,
                data_type="image",
                batch_size=1,
                face_detection_threshold=FACE_DETECTION_THRESHOLD,
                progress_bar=False,
            )
        except Exception as error:  # noqa: BLE001 - any model failure is debug-unavailable
            raise PyFeatDebugUnavailable(
                f"Py-Feat detection failed: {error}"
            ) from error
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _best_face_row(fex: Any) -> Any | None:
    """Return the highest-``FaceScore`` detection row, or ``None`` if empty."""
    try:
        if fex is None or len(fex.index) == 0:
            return None
    except (AttributeError, TypeError):
        return None
    if FACE_SCORE_COLUMN in getattr(fex, "columns", []):
        scores = [
            (index, _to_float(fex.at[index, FACE_SCORE_COLUMN]))
            for index in fex.index
        ]
        finite = [(index, score) for index, score in scores if score is not None]
        if finite:
            best_index = max(finite, key=lambda item: item[1])[0]
            return fex.loc[best_index]
    # No usable score: fall back to the first row so callers can still read cells.
    return fex.iloc[0]


def _extract_landmarks(row: Any) -> list[list[float]] | None:
    """Pair dynamically discovered ``x_<n>``/``y_<n>`` columns into [x, y] pixels."""
    index = getattr(row, "index", None)
    if index is None:
        return None
    x_by_point: dict[int, float] = {}
    y_by_point: dict[int, float] = {}
    for label in index:
        name = str(label)
        x_match = _LANDMARK_X_PATTERN.match(name)
        if x_match:
            value = _to_float(row[label])
            if value is not None:
                x_by_point[int(x_match.group(1))] = value
            continue
        y_match = _LANDMARK_Y_PATTERN.match(name)
        if y_match:
            value = _to_float(row[label])
            if value is not None:
                y_by_point[int(y_match.group(1))] = value
    shared = sorted(set(x_by_point) & set(y_by_point))
    if not shared:
        return None
    return [[x_by_point[point], y_by_point[point]] for point in shared]


def _cell(row: Any, column: str, reasons: dict[str, str], field: str) -> float | None:
    """Read one numeric cell, recording a reason when it is missing/non-finite."""
    try:
        if column not in row.index:
            reasons[field] = "column_missing"
            return None
    except (AttributeError, TypeError):
        reasons[field] = "column_missing"
        return None
    value = _to_float(row[column])
    if value is None:
        reasons[field] = "value_not_finite"
    return value


def _to_float(value: Any) -> float | None:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)
