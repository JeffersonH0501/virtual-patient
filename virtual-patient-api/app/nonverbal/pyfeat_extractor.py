"""Py-Feat v2 raw visual feature extraction for interview turns.

This module is extraction-and-quality only (Requirements 1.2, 1.4, 9.1): it runs
Py-Feat over the student video, selects the best-``FaceScore`` row per frame, and
emits raw per-frame series plus frame-level quality for each turn window. It does
NOT derive metrics, apply methodology thresholds, or assign any label. All
derivation (visual alignment against a calibrated center, dwell segmentation, nod
detection, smile activity) lives in ``app/nonverbal/preprocessing.py``.

The extractor emits head pose on all three axes as raw series
(``head_pitch_samples``, ``head_yaw_samples``, ``head_roll_samples``). Pitch is
consumed by nod detection in preprocessing (task 3.2); yaw and roll are emitted
so calibration can derive the neutral head pose on all three axes
(``app/multimodal/calibration.py``, Requirement 15.1). Yaw/roll are raw-only and
are not otherwise interpreted here.

The raw output maps cleanly to ``app.multimodal.schemas.NonverbalRawFeatures`` and
is descriptive-only: it represents behavioural and contextual observations, not
empathy, attention, warmth, or any psychological state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.multimodal.schemas import NonverbalRawFeatures


EXTRACTOR_NAME = "py-feat"
EXTRACTOR_VERSION = "2.1.1"
DEVICE = "cpu"
WEIGHTS_ROOT = Path("/app/pyfeat/weights")
SAMPLE_FPS = 10.0
BATCH_SIZE = 8
FACE_DETECTION_THRESHOLD = 0.5

# Real Py-Feat 2.1.1 columns consumed downstream. Verified against the current
# best-face row extraction; the extractor emits these as raw series only.
FACE_SCORE_COLUMN = "FaceScore"
GAZE_YAW_COLUMN = "gaze_yaw"
GAZE_PITCH_COLUMN = "gaze_pitch"
AU12_COLUMN = "AU12"
HEAD_PITCH_COLUMN = "Pitch"
# Head yaw/roll pose columns (canonical Fex facepose schema, +up convention
# since Py-Feat 2.1). These are emitted as raw series only, alongside the
# already-used Pitch column, so that calibration can derive a neutral head pose
# on all three axes (Requirement 15.1). They are not interpreted here.
HEAD_YAW_COLUMN = "Yaw"
HEAD_ROLL_COLUMN = "Roll"
FRAME_COLUMN = "frame"


@dataclass(frozen=True)
class StudentTurnVideo:
    """A conversation-turn window analyzed against the student video."""

    turn_id: str
    start_ms: int
    end_ms: int
    conversation_speaker: str = "unknown"


def analyze_pyfeat_student_turn_videos(
    video_path: Path,
    turns: Iterable[StudentTurnVideo],
) -> dict[str, dict[str, Any]]:
    """Produce raw Py-Feat per-frame series over the common turn windows.

    Returns a mapping ``turn_id -> raw features dict`` where each value serializes
    a :class:`NonverbalRawFeatures` (via ``model_dump``) with an added
    ``observationContext`` block. No derived metrics or labels are produced.

    Signature note for later tasks: the per-turn value shape changed from the
    previous summarized/derived block to the raw ``NonverbalRawFeatures`` shape.
    The router in ``app/routers/interview_recordings.py`` and any script that
    reads the per-turn payload must be updated to consume raw series and to run
    ``app/nonverbal/preprocessing.py`` for derivation (task 3.2).
    """
    turn_list = list(turns)
    if not turn_list:
        return {}

    import cv2
    import feat.utils.io as feat_io
    from feat import Detectorv2

    WEIGHTS_ROOT.mkdir(parents=True, exist_ok=True)
    feat_io.get_resource_path = lambda: str(WEIGHTS_ROOT)

    capture = cv2.VideoCapture(str(video_path))
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    capture.release()
    if not source_fps or not math.isfinite(source_fps) or source_fps <= 0:
        raise RuntimeError("Unable to determine video frame rate for Py-Feat")
    skip_frames = max(round(source_fps / SAMPLE_FPS), 1)
    detector = Detectorv2(device=DEVICE)
    fex = detector.detect(
        str(video_path),
        data_type="video",
        skip_frames=skip_frames,
        batch_size=BATCH_SIZE,
        face_detection_threshold=FACE_DETECTION_THRESHOLD,
        progress_bar=False,
    )
    rows = _best_face_rows(fex, source_fps)
    return {
        turn.turn_id: {
            **_raw_features_for_turn(
                [row for row in rows if turn.start_ms <= row["timestamp_ms"] <= turn.end_ms],
                turn,
            ).model_dump(),
            "observationContext": {
                "observedParticipant": "student",
                "conversationSpeaker": turn.conversation_speaker,
            },
        }
        for turn in turn_list
    }


def _best_face_rows(fex: Any, source_fps: float) -> list[dict[str, Any]]:
    """Keep the highest-``FaceScore`` detected face per sampled frame."""
    frames: dict[int, dict[str, Any]] = {}
    for _, row in fex.iterrows():
        frame = _as_int(row.get(FRAME_COLUMN))
        if frame is None:
            continue
        candidate = {
            "timestamp_ms": round(frame * 1000 / source_fps),
            "face_score": _as_float(row.get(FACE_SCORE_COLUMN)),
            "gaze_yaw": _as_float(row.get(GAZE_YAW_COLUMN)),
            "gaze_pitch": _as_float(row.get(GAZE_PITCH_COLUMN)),
            "au12": _as_float(row.get(AU12_COLUMN)),
            "head_pitch": _as_float(row.get(HEAD_PITCH_COLUMN)),
            "head_yaw": _as_float(row.get(HEAD_YAW_COLUMN)),
            "head_roll": _as_float(row.get(HEAD_ROLL_COLUMN)),
        }
        existing = frames.get(frame)
        if existing is None or (candidate["face_score"] or -1) > (existing["face_score"] or -1):
            frames[frame] = candidate
    return list(frames.values())


def _raw_features_for_turn(
    rows: list[dict[str, Any]],
    turn: StudentTurnVideo,
) -> NonverbalRawFeatures:
    """Assemble raw per-frame series and frame-level quality for one turn.

    No thresholds are applied and no metric is derived. Frames whose face was not
    detected (``face_score is None``) are excluded from the per-signal series but
    still counted in ``sampled_frame_count`` for quality. Missing per-signal
    values are dropped from their series so that absent evidence is represented as
    a shorter series, never as a fabricated number.
    """
    ordered = sorted(rows, key=lambda row: row["timestamp_ms"])
    valid_rows = [row for row in ordered if row["face_score"] is not None]

    issues: list[str] = []
    if not ordered:
        issues.append("no_sampled_frames_in_turn")
    if not valid_rows:
        issues.append("face_not_detected")

    return NonverbalRawFeatures(
        face_score_samples=[row["face_score"] for row in valid_rows],
        gaze_yaw_samples=[row["gaze_yaw"] for row in valid_rows if row["gaze_yaw"] is not None],
        gaze_pitch_samples=[row["gaze_pitch"] for row in valid_rows if row["gaze_pitch"] is not None],
        au12_samples=[row["au12"] for row in valid_rows if row["au12"] is not None],
        head_pitch_samples=[row["head_pitch"] for row in valid_rows if row["head_pitch"] is not None],
        head_yaw_samples=[row["head_yaw"] for row in valid_rows if row["head_yaw"] is not None],
        head_roll_samples=[row["head_roll"] for row in valid_rows if row["head_roll"] is not None],
        frame_timestamps_ms=[float(row["timestamp_ms"]) for row in valid_rows],
        sample_fps=SAMPLE_FPS,
        turn_duration_ms=max(turn.end_ms - turn.start_ms, 0),
        extractor={
            "name": EXTRACTOR_NAME,
            "version": EXTRACTOR_VERSION,
            "detector": "Detectorv2",
            "sample_fps": SAMPLE_FPS,
            "batch_size": BATCH_SIZE,
            "face_detection_threshold": FACE_DETECTION_THRESHOLD,
        },
        video_quality={
            "sampled_frame_count": len(ordered),
            "valid_frame_count": len(valid_rows),
            "issues": issues,
        },
    )


def _as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
