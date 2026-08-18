"""OpenSMILE-based, per-turn acoustic observations for student speech.

This module reports descriptive acoustic measures only. It does not infer
emotion, empathy, attention, or any other psychological construct.
"""

from __future__ import annotations

import math
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from app.core.config import settings


EXTRACTOR_NAME = "opensmile"
EXTRACTOR_VERSION = "2.6.0"
FEATURE_SET = "eGeMAPSv02"


@dataclass(frozen=True)
class StudentTurnAudio:
    """The persisted transcript turn and its interval on the common clock."""

    turn_id: str
    start_ms: int
    end_ms: int
    transcript: str


@dataclass(frozen=True)
class _TurnFeatures:
    observation: dict[str, Any]
    loudness_median: float | None


def analyze_student_turns(
    audio_path: Path,
    turns: Iterable[StudentTurnAudio],
) -> dict[str, dict[str, Any]]:
    """Extract one descriptive acoustic summary for each student turn.

    The input is the continuous, private student-audio recording. FFmpeg creates
    short temporary WAV segments which are deleted before this function returns.
    A turn that cannot be decoded or does not have enough voiced signal is
    represented as unavailable by omitting it from the result.
    """
    if not settings.paraverbal_analysis_enabled:
        return {}

    extracted: dict[str, _TurnFeatures] = {}
    with tempfile.TemporaryDirectory(prefix="virtual-patient-paraverbal-") as directory:
        temp_dir = Path(directory)
        for turn in turns:
            result = _analyze_turn(audio_path, turn, temp_dir)
            if result is not None:
                extracted[turn.turn_id] = result

    reference_values = [
        result.loudness_median
        for result in extracted.values()
        if result.loudness_median is not None
    ]
    session_loudness_reference = median(reference_values) if reference_values else None
    for result in extracted.values():
        raw_loudness = result.loudness_median
        result.observation["loudness_median_rel"] = (
            _round(raw_loudness - session_loudness_reference)
            if raw_loudness is not None and session_loudness_reference is not None
            else None
        )
    return {turn_id: result.observation for turn_id, result in extracted.items()}


def _analyze_turn(
    audio_path: Path,
    turn: StudentTurnAudio,
    temp_dir: Path,
) -> _TurnFeatures | None:
    duration_ms = turn.end_ms - turn.start_ms
    if duration_ms <= 0:
        return None
    wav_path = temp_dir / f"{turn.turn_id}.wav"
    try:
        _decode_segment(audio_path, wav_path, turn.start_ms, duration_ms)
        samples, sample_rate = _read_pcm_wav(wav_path)
        if not samples or sample_rate <= 0:
            return None
        return _summarize_wav(wav_path, samples, sample_rate, duration_ms, turn.transcript)
    except (OSError, subprocess.SubprocessError, wave.Error, ValueError):
        return None


def _decode_segment(audio_path: Path, wav_path: Path, start_ms: int, duration_ms: int) -> None:
    """Decode one clock-aligned segment into mono PCM WAV without shell parsing."""
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{start_ms / 1000:.3f}",
            "-t",
            f"{duration_ms / 1000:.3f}",
            "-i",
            str(audio_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(wav_path),
        ],
        check=True,
        capture_output=True,
        timeout=max(15, math.ceil(duration_ms / 1000) + 10),
    )


def _read_pcm_wav(path: Path) -> tuple[list[float], int]:
    with wave.open(str(path), "rb") as audio:
        if audio.getsampwidth() != 2 or audio.getnchannels() != 1:
            raise ValueError("Expected mono 16-bit PCM audio")
        frames = audio.readframes(audio.getnframes())
        values = [
            int.from_bytes(frames[index:index + 2], byteorder="little", signed=True) / 32768
            for index in range(0, len(frames), 2)
        ]
        return values, audio.getframerate()


def _summarize_wav(
    wav_path: Path,
    samples: list[float],
    sample_rate: int,
    turn_duration_ms: int,
    transcript: str,
) -> _TurnFeatures | None:
    try:
        import opensmile
    except ImportError:
        return None

    smile = opensmile.Smile(
        feature_set=opensmile.FeatureSet.eGeMAPSv02,
        feature_level=opensmile.FeatureLevel.LowLevelDescriptors,
    )
    frame = smile.process_file(str(wav_path))
    pitch_column = _find_column(frame.columns, "F0semitoneFrom27.5Hz")
    loudness_column = _find_column(frame.columns, "loudness")
    if pitch_column is None or loudness_column is None or frame.empty:
        return None

    pitch_values = _finite_values(frame[pitch_column].tolist())
    loudness_values = _finite_values(frame[loudness_column].tolist())
    voiced_values = [value for value in pitch_values if value > 0]
    frame_duration_ms = turn_duration_ms / max(len(frame.index), 1)
    voiced_duration_ms = round(len(voiced_values) * frame_duration_ms)
    issues: list[str] = []
    if voiced_duration_ms < settings.paraverbal_min_voiced_duration_ms:
        issues.append("insufficient_voiced_duration")
    if max((abs(sample) for sample in samples), default=0) >= 0.999:
        issues.append("clipping_detected")
    pause_durations = _pause_durations_ms(pitch_values, frame_duration_ms)
    word_count = len([word for word in transcript.split() if word.strip(".,;:!?¿¡()[]{}\"'")])
    voiced_seconds = voiced_duration_ms / 1000
    total_seconds = turn_duration_ms / 1000
    loudness_median = _median_or_none(loudness_values)
    observation: dict[str, Any] = {
        "extractor": {"name": EXTRACTOR_NAME, "version": EXTRACTOR_VERSION, "feature_set": FEATURE_SET},
        "word_count": word_count,
        "voiced_duration_ms": voiced_duration_ms,
        "speaking_rate_wpm": _round(word_count / total_seconds * 60) if total_seconds else None,
        "articulation_rate_wpm": _round(word_count / voiced_seconds * 60) if voiced_seconds else None,
        "pause_count": len(pause_durations),
        "pause_total_ms": round(sum(pause_durations)),
        "pause_median_ms": _round(_median_or_none(pause_durations)),
        "pause_ratio": _round(sum(pause_durations) / turn_duration_ms) if turn_duration_ms else None,
        "f0_median_hz": _round(_semitone_to_hz(_median_or_none(voiced_values))),
        "f0_iqr_st": _round(_iqr(voiced_values)),
        "loudness_median_rel": None,
        "loudness_iqr": _round(_iqr(loudness_values)),
        "audio_quality": {
            "valid_ratio": _round(len(voiced_values) / max(len(pitch_values), 1)),
            "issues": issues,
        },
    }
    return _TurnFeatures(observation=observation, loudness_median=loudness_median)


def _find_column(columns: Iterable[str], fragment: str) -> str | None:
    return next((column for column in columns if fragment.lower() in column.lower()), None)


def _finite_values(values: Iterable[object]) -> list[float]:
    return [float(value) for value in values if isinstance(value, (int, float)) and math.isfinite(float(value))]


def _pause_durations_ms(pitch_values: list[float], frame_duration_ms: float) -> list[float]:
    pauses: list[float] = []
    current_frames = 0
    for value in pitch_values:
        if value <= 0:
            current_frames += 1
            continue
        if current_frames:
            duration = current_frames * frame_duration_ms
            if duration >= settings.paraverbal_min_pause_ms:
                pauses.append(duration)
            current_frames = 0
    if current_frames:
        duration = current_frames * frame_duration_ms
        if duration >= settings.paraverbal_min_pause_ms:
            pauses.append(duration)
    return pauses


def _median_or_none(values: Iterable[float]) -> float | None:
    sequence = list(values)
    return median(sequence) if sequence else None


def _iqr(values: Iterable[float]) -> float | None:
    sequence = sorted(values)
    if len(sequence) < 2:
        return None
    lower_index = round((len(sequence) - 1) * 0.25)
    upper_index = round((len(sequence) - 1) * 0.75)
    return sequence[upper_index] - sequence[lower_index]


def _semitone_to_hz(value: float | None) -> float | None:
    return 27.5 * (2 ** (value / 12)) if value is not None else None


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None and math.isfinite(value) else None
