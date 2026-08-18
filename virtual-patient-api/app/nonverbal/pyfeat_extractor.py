"""Py-Feat v2 secondary visual extractor for benchmark-only observations."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable

from app.core.config import settings
from app.nonverbal.openface_extractor import StudentTurnVideo


EXTRACTOR_NAME = "py-feat"
EXTRACTOR_VERSION = "2.1.1"


def analyze_pyfeat_student_turn_videos(
    video_path: Path,
    turns: Iterable[StudentTurnVideo],
) -> dict[str, dict[str, Any]]:
    """Produce independent Py-Feat v2 summaries over the common turn windows."""
    turn_list = list(turns)
    if not settings.pyfeat_analysis_enabled or not turn_list:
        return {}
    if settings.pyfeat_device not in {"cpu", "cuda", "mps", "auto"}:
        raise ValueError("PYFEAT_DEVICE must be cpu, cuda, mps, or auto")
    if settings.pyfeat_sample_fps <= 0:
        raise ValueError("PYFEAT_SAMPLE_FPS must be greater than zero")

    import cv2
    from feat import Detectorv2

    capture = cv2.VideoCapture(str(video_path))
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    capture.release()
    if not source_fps or not math.isfinite(source_fps) or source_fps <= 0:
        raise RuntimeError("Unable to determine video frame rate for Py-Feat")
    skip_frames = max(round(source_fps / settings.pyfeat_sample_fps), 1)
    detector = Detectorv2(device=settings.pyfeat_device)
    fex = detector.detect(
        str(video_path),
        data_type="video",
        skip_frames=skip_frames,
        batch_size=1,
        face_detection_threshold=0.5,
        progress_bar=False,
    )
    rows = _best_face_rows(fex, source_fps)
    return {
        turn.turn_id: {
            **_summarize_turn(
                [row for row in rows if turn.start_ms <= row["timestamp_ms"] <= turn.end_ms]
            ),
            "observationContext": {
                "observedParticipant": "student",
                "conversationSpeaker": turn.conversation_speaker,
            },
        }
        for turn in turn_list
    }


def _best_face_rows(fex: Any, source_fps: float) -> list[dict[str, Any]]:
    frames: dict[int, dict[str, Any]] = {}
    for _, row in fex.iterrows():
        frame = _as_int(row.get("frame"))
        if frame is None:
            continue
        candidate = {
            "timestamp_ms": round(frame * 1000 / source_fps),
            "face_score": _as_float(row.get("FaceScore")),
            "gaze_yaw": _as_float(row.get("gaze_yaw")),
            "gaze_pitch": _as_float(row.get("gaze_pitch")),
            "au12": _as_float(row.get("AU12")),
            "head_pitch": _as_float(row.get("Pitch")),
        }
        existing = frames.get(frame)
        if existing is None or (candidate["face_score"] or -1) > (existing["face_score"] or -1):
            frames[frame] = candidate
    return list(frames.values())


def _summarize_turn(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid_rows = [row for row in rows if row["face_score"] is not None]
    issues: list[str] = []
    if not rows:
        issues.append("no_sampled_frames_in_turn")
    if not valid_rows:
        issues.append("face_not_detected")
    aligned = _aligned_rows(valid_rows, issues)
    au12_values = _au12_values(valid_rows, issues)
    active = [
        value for value in au12_values
        if settings.pyfeat_au12_active_threshold is not None
        and value >= settings.pyfeat_au12_active_threshold
    ]
    return {
        "extractor": {"name": EXTRACTOR_NAME, "version": EXTRACTOR_VERSION, "detector": "Detectorv2", "sample_fps": settings.pyfeat_sample_fps},
        "visual_alignment_ratio": _round(len(aligned) / len(valid_rows)) if aligned else (0.0 if valid_rows and settings.pyfeat_gaze_alignment_max_radians is not None else None),
        "visual_alignment_dwell_ms": None,
        "nod_count": None,
        "nod_rate_min": None,
        "smile_activity_ratio": _round(len(active) / len(valid_rows)) if au12_values and settings.pyfeat_au12_active_threshold is not None else None,
        "smile_intensity_mean": _round(sum(au12_values) / len(au12_values)) if au12_values else None,
        "video_valid_ratio": _round(len(valid_rows) / len(rows)) if rows else None,
        "video_quality": {"sampled_frame_count": len(rows), "valid_frame_count": len(valid_rows), "issues": issues},
    }


def _aligned_rows(rows: list[dict[str, Any]], issues: list[str]) -> list[dict[str, Any]]:
    tolerance = settings.pyfeat_gaze_alignment_max_radians
    if tolerance is None:
        issues.append("visual_alignment_not_calibrated")
        return []
    return [row for row in rows if row["gaze_yaw"] is not None and row["gaze_pitch"] is not None and math.hypot(row["gaze_yaw"], row["gaze_pitch"]) <= tolerance]


def _au12_values(rows: list[dict[str, Any]], issues: list[str]) -> list[float]:
    if settings.pyfeat_au12_active_threshold is None:
        issues.append("smile_au12_threshold_not_configured")
        return []
    values = [row["au12"] for row in rows if row["au12"] is not None]
    if not values:
        issues.append("smile_au12_unavailable")
    return values


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


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None and math.isfinite(value) else None
