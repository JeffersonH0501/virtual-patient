"""Py-Feat v2 descriptive visual observations for interview turns."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.core.config import settings


EXTRACTOR_NAME = "py-feat"
EXTRACTOR_VERSION = "2.1.1"


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
    """Produce Py-Feat v2 summaries over the common turn windows."""
    turn_list = list(turns)
    if not settings.pyfeat_analysis_enabled or not turn_list:
        return {}
    if settings.pyfeat_device not in {"cpu", "cuda", "mps", "auto"}:
        raise ValueError("PYFEAT_DEVICE must be cpu, cuda, mps, or auto")
    if settings.pyfeat_sample_fps <= 0:
        raise ValueError("PYFEAT_SAMPLE_FPS must be greater than zero")

    import cv2
    import feat.utils.io as feat_io
    from feat import Detectorv2

    settings.pyfeat_weights_root.mkdir(parents=True, exist_ok=True)
    feat_io.get_resource_path = lambda: str(settings.pyfeat_weights_root)

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
    gaze_yaw_values = [row["gaze_yaw"] for row in valid_rows if row["gaze_yaw"] is not None]
    gaze_pitch_values = [row["gaze_pitch"] for row in valid_rows if row["gaze_pitch"] is not None]
    gaze_rows = [
        row for row in valid_rows
        if row["gaze_yaw"] is not None and row["gaze_pitch"] is not None
    ]
    head_pitch_values = [row["head_pitch"] for row in valid_rows if row["head_pitch"] is not None]
    return {
        "extractor": {"name": EXTRACTOR_NAME, "version": EXTRACTOR_VERSION, "detector": "Detectorv2", "sample_fps": settings.pyfeat_sample_fps},
        "visual_alignment_ratio": (
            _round(len(aligned) / len(gaze_rows))
            if gaze_rows and settings.pyfeat_gaze_alignment_max_radians is not None
            else None
        ),
        "median_visual_alignment_dwell_ms": _median_alignment_dwell_ms(
            gaze_rows,
            aligned,
        ),
        "gaze_yaw_mean": _round(sum(gaze_yaw_values) / len(gaze_yaw_values)) if gaze_yaw_values else None,
        "gaze_pitch_mean": _round(sum(gaze_pitch_values) / len(gaze_pitch_values)) if gaze_pitch_values else None,
        "head_pitch_mean": _round(sum(head_pitch_values) / len(head_pitch_values)) if head_pitch_values else None,
        "nod_count": None,
        "nod_rate_min": None,
        "smile_activity_ratio": _round(len(active) / len(au12_values)) if au12_values and settings.pyfeat_au12_active_threshold is not None else None,
        "mean_smile_activation": _round(sum(au12_values) / len(au12_values)) if au12_values else None,
        "video_valid_ratio": _round(len(valid_rows) / len(rows)) if rows else None,
        "video_quality": {"sampled_frame_count": len(rows), "valid_frame_count": len(valid_rows), "issues": issues},
    }


def _aligned_rows(rows: list[dict[str, Any]], issues: list[str]) -> list[dict[str, Any]]:
    tolerance = settings.pyfeat_gaze_alignment_max_radians
    if tolerance is None:
        issues.append("visual_alignment_not_calibrated")
        return []
    gaze_rows = [
        row for row in rows
        if row["gaze_yaw"] is not None and row["gaze_pitch"] is not None
    ]
    if not gaze_rows:
        issues.append("gaze_unavailable")
        return []
    return [
        row for row in gaze_rows
        if math.hypot(row["gaze_yaw"], row["gaze_pitch"]) <= tolerance
    ]


def _median_alignment_dwell_ms(
    sampled_rows: list[dict[str, Any]],
    aligned_rows: list[dict[str, Any]],
) -> float | None:
    """Return the median duration of contiguous calibrated alignment runs."""
    if not sampled_rows or settings.pyfeat_gaze_alignment_max_radians is None:
        return None
    timestamps = sorted(row["timestamp_ms"] for row in sampled_rows)
    aligned_timestamps = {
        row["timestamp_ms"] for row in aligned_rows
    }
    if not aligned_timestamps:
        return 0.0
    intervals = [
        current - previous
        for previous, current in zip(timestamps, timestamps[1:])
        if current > previous
    ]
    sample_interval = sorted(intervals)[len(intervals) // 2] if intervals else 0
    runs: list[float] = []
    run_start: float | None = None
    run_end: float | None = None
    for timestamp in timestamps:
        if timestamp in aligned_timestamps:
            if run_start is None:
                run_start = timestamp
            run_end = timestamp
        elif run_start is not None and run_end is not None:
            runs.append(run_end - run_start + sample_interval)
            run_start = None
            run_end = None
    if run_start is not None and run_end is not None:
        runs.append(run_end - run_start + sample_interval)
    return _round(_median(runs)) if runs else 0.0


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _au12_values(rows: list[dict[str, Any]], issues: list[str]) -> list[float]:
    if settings.pyfeat_au12_active_threshold is None:
        issues.append("smile_au12_threshold_not_configured")
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
