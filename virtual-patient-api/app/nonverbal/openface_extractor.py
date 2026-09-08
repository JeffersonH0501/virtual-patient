"""OpenFace 3.0-based per-turn visual observations for student video.

This extractor reports low-level, descriptive evidence. It does not infer
attention, eye contact, empathy, emotion, or any psychological construct from
webcam imagery.
"""

from __future__ import annotations

import importlib.util
import math
import os
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from app.core.config import settings


EXTRACTOR_NAME = "openface-3.0"
PACKAGE_NAME = "openface-test"
PACKAGE_VERSION = "0.1.26"
REQUIRED_WEIGHT_FILES = (
    "Alignment_RetinaFace.pth",
    "MTL_backbone.pth",
)
_OPENFACE_WORKING_DIRECTORY_LOCK = threading.Lock()


@dataclass(frozen=True)
class StudentTurnVideo:
    """A conversation-turn window analyzed against the continuous student video."""

    turn_id: str
    start_ms: int
    end_ms: int
    conversation_speaker: str = "unknown"


@dataclass(frozen=True)
class _FrameObservation:
    timestamp_ms: int
    face_detected: bool
    gaze_yaw: float | None
    gaze_pitch: float | None
    action_units: list[float] | None


def analyze_student_turn_videos(
    video_path: Path,
    turns: Iterable[StudentTurnVideo],
) -> dict[str, dict[str, Any]]:
    """Summarize OpenFace 3.0 outputs for each conversation-turn interval.

    The original private video is never modified. A temporary, low-rate video is
    generated solely for post-interview analysis and removed on return.
    """
    turn_list = list(turns)
    if not settings.nonverbal_analysis_enabled or not turn_list:
        return {}
    _validate_runtime()
    with tempfile.TemporaryDirectory(prefix="virtual-patient-nonverbal-") as directory:
        temp_dir = Path(directory)
        frames_dir = temp_dir / "frames"
        _sample_video(video_path, frames_dir)
        frames = _extract_openface_frames(frames_dir)
    return {
        turn.turn_id: {
            **_summarize_turn(
                [
                    frame
                    for frame in frames
                    if turn.start_ms <= frame.timestamp_ms <= turn.end_ms
                ]
            ),
            "observationContext": {
                "observedParticipant": "student",
                "conversationSpeaker": turn.conversation_speaker,
            },
        }
        for turn in turn_list
    }


def _validate_runtime() -> None:
    if settings.openface_device not in {"cpu", "cuda"}:
        raise ValueError("OPENFACE_DEVICE must be either 'cpu' or 'cuda'")
    if settings.openface_sample_fps <= 0:
        raise ValueError("OPENFACE_SAMPLE_FPS must be greater than zero")
    if importlib.util.find_spec("openface") is None:
        raise RuntimeError("OpenFace Python package is not installed")
    missing_weights = [
        filename
        for filename in REQUIRED_WEIGHT_FILES
        if not (settings.openface_weights_root / filename).is_file()
    ]
    if missing_weights:
        raise RuntimeError(
            "OpenFace weights are unavailable: " + ", ".join(missing_weights)
        )


def _sample_video(source_path: Path, frames_dir: Path) -> None:
    frames_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(source_path), "-an", "-vf",
            f"fps={settings.openface_sample_fps}", "-q:v", "3", "-start_number",
            "0", "-y", str(frames_dir / "%08d.jpg"),
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )


def _extract_openface_frames(frames_dir: Path) -> list[_FrameObservation]:
    """Use the upstream OpenFace models once for image-path based inference.

    OpenFace 3.0's current video helper passes in-memory frames to a detector
    that expects image paths. Sampling to private temporary JPEG files avoids
    that upstream incompatibility while retaining the shared video timeline.
    """
    from openface.face_detection import FaceDetector
    from openface.multitask_model import MultitaskPredictor

    device = settings.openface_device
    # The upstream RetinaFace implementation loads one auxiliary weight through
    # a hard-coded ``./weights`` path. Limit the compatibility work-around to
    # model initialization and serialize it because the process working
    # directory is global.
    with _openface_weights_working_directory():
        detector = FaceDetector(
            model_path=str(settings.openface_weights_root / "Alignment_RetinaFace.pth"),
            device=device,
        )
    predictor = MultitaskPredictor(
        model_path=str(settings.openface_weights_root / "MTL_backbone.pth"),
        device=device,
    )
    frames: list[_FrameObservation] = []
    for frame_path in sorted(frames_dir.glob("*.jpg")):
        frame_index = int(frame_path.stem)
        face, detections = detector.get_face(str(frame_path))
        gaze_yaw = gaze_pitch = None
        action_units = None
        if face is not None and detections is not None:
            _, gaze, action_units_tensor = predictor.predict(face)
            gaze_yaw = float(gaze[0][0])
            gaze_pitch = float(gaze[0][1])
            action_units = [float(value) for value in action_units_tensor.flatten().tolist()]
        frames.append(
            _FrameObservation(
                timestamp_ms=round(frame_index / settings.openface_sample_fps * 1000),
                face_detected=face is not None and detections is not None,
                gaze_yaw=gaze_yaw,
                gaze_pitch=gaze_pitch,
                action_units=action_units,
            )
        )
    return frames


@contextmanager
def _openface_weights_working_directory() -> Iterator[None]:
    with _OPENFACE_WORKING_DIRECTORY_LOCK:
        previous_directory = Path.cwd()
        os.chdir(settings.openface_weights_root.parent)
        try:
            yield
        finally:
            os.chdir(previous_directory)


def _summarize_turn(frames: list[_FrameObservation]) -> dict[str, Any]:
    total_frames = len(frames)
    valid_frames = [frame for frame in frames if frame.face_detected]
    issues: list[str] = []
    if not total_frames:
        issues.append("no_sampled_frames_in_turn")
    if not valid_frames:
        issues.append("face_not_detected")

    aligned = _aligned_frames(valid_frames, issues)
    smile_values = _smile_values(valid_frames, issues)
    sample_duration_ms = 1000 / settings.openface_sample_fps
    active_smiles = (
        [value for value in smile_values if value >= settings.openface_au12_active_threshold]
        if settings.openface_au12_active_threshold is not None
        else []
    )
    gaze_yaw_values = [frame.gaze_yaw for frame in valid_frames if frame.gaze_yaw is not None]
    gaze_pitch_values = [frame.gaze_pitch for frame in valid_frames if frame.gaze_pitch is not None]

    return {
        "extractor": {
            "name": EXTRACTOR_NAME,
            "package": PACKAGE_NAME,
            "version": PACKAGE_VERSION,
            "sample_fps": settings.openface_sample_fps,
        },
        "visual_alignment_ratio": _round(len(aligned) / len(valid_frames)) if aligned else (0.0 if valid_frames and settings.openface_gaze_alignment_max_radians is not None else None),
        "visual_alignment_dwell_ms": _longest_run_ms(valid_frames, aligned, sample_duration_ms) if settings.openface_gaze_alignment_max_radians is not None else None,
        "gaze_yaw_mean": _round(sum(gaze_yaw_values) / len(gaze_yaw_values)) if gaze_yaw_values else None,
        "gaze_pitch_mean": _round(sum(gaze_pitch_values) / len(gaze_pitch_values)) if gaze_pitch_values else None,
        "nod_count": None,
        "nod_rate_min": None,
        "smile_activity_ratio": _round(len(active_smiles) / len(valid_frames)) if smile_values and settings.openface_au12_active_threshold is not None else None,
        "smile_intensity_mean": _round(sum(smile_values) / len(smile_values)) if smile_values else None,
        "video_valid_ratio": _round(len(valid_frames) / total_frames) if total_frames else None,
        "video_quality": {
            "sampled_frame_count": total_frames,
            "valid_frame_count": len(valid_frames),
            "issues": issues,
        },
    }


def _aligned_frames(
    frames: list[_FrameObservation], issues: list[str],
) -> list[int]:
    tolerance = settings.openface_gaze_alignment_max_radians
    if tolerance is None:
        issues.append("visual_alignment_not_calibrated")
        return []
    return [
        index for index, frame in enumerate(frames)
        if frame.gaze_yaw is not None and frame.gaze_pitch is not None
        and math.hypot(frame.gaze_yaw, frame.gaze_pitch) <= tolerance
    ]


def _smile_values(frames: list[_FrameObservation], issues: list[str]) -> list[float]:
    au12_index = settings.openface_au12_index
    threshold = settings.openface_au12_active_threshold
    if au12_index is None or threshold is None:
        issues.append("smile_au12_mapping_not_configured")
        return []
    values = [
        frame.action_units[au12_index]
        for frame in frames
        if frame.action_units is not None and len(frame.action_units) > au12_index
    ]
    if not values:
        issues.append("smile_au12_unavailable")
    return values


def _longest_run_ms(
    frames: list[_FrameObservation], aligned_indices: list[int], sample_duration_ms: float,
) -> int:
    aligned = set(aligned_indices)
    longest = current = 0
    for index in range(len(frames)):
        if index in aligned:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return round(longest * sample_duration_ms)


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None and math.isfinite(value) else None
