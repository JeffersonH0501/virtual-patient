"""OpenSMILE-based, per-turn acoustic extraction for student speech.

This module performs extraction and quality assessment only. It decodes each
student turn into a temporary WAV segment, runs OpenSMILE (eGeMAPSv02) once per
segment, and emits raw signal arrays plus a quality summary as
:class:`~app.multimodal.schemas.ParaverbalRawFeatures`.

It does NOT derive processed metrics (speech rate, pause statistics, medians,
percentile ranges) and it does NOT decide any base or integrated labels. That
methodology lives downstream in ``app/paraverbal/preprocessing.py`` (derivation)
and in the multimodal threshold/label engines (interpretation). The extractor
also reports descriptive acoustic measures only: it does not infer emotion,
empathy, attention, or any other psychological construct.

Methodology parameters (``min_voiced_duration_ms``) are passed in by the caller
rather than read from ``settings`` here, so that changing methodology never
requires editing extractor code. Pause filtering by ``min_pause_ms`` is a
derivation step and is applied downstream in preprocessing, not here: this
extractor emits every contiguous unvoiced segment as a raw pause duration.
"""

from __future__ import annotations

import math
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.multimodal.schemas import ParaverbalRawFeatures


EXTRACTOR_NAME = "opensmile"
EXTRACTOR_VERSION = "2.6.0"
FEATURE_SET = "eGeMAPSv02"

# Provisional default used only for the quality issue flag when the caller does
# not supply a methodology value. It does not filter or alter the emitted raw
# signals; it only annotates ``audio_quality.issues``.
MIN_VOICED_DURATION_MS = 300


@dataclass(frozen=True)
class StudentTurnAudio:
    """The persisted transcript turn and its interval on the common clock."""

    turn_id: str
    start_ms: int
    end_ms: int
    transcript: str


def analyze_student_turns(
    audio_path: Path,
    turns: Iterable[StudentTurnAudio],
    *,
    min_voiced_duration_ms: int = MIN_VOICED_DURATION_MS,
) -> dict[str, ParaverbalRawFeatures]:
    """Extract one raw acoustic feature set for each student turn.

    The input is the continuous, private student-audio recording. FFmpeg creates
    short temporary WAV segments which are deleted before this function returns.
    A turn that cannot be decoded or does not have enough voiced signal is
    represented as unavailable by omitting it from the result.

    ``min_voiced_duration_ms`` is a passed-in methodology input used only to flag
    an ``insufficient_voiced_duration`` quality issue; it never filters the
    emitted raw signals.
    """
    try:
        import opensmile
    except ImportError:
        return {}

    # Constructing the eGeMAPS processing graph has a measurable fixed cost.
    # One instance can process every sequential turn in this analysis call while
    # preserving the exact feature set and frame-level output.
    smile = opensmile.Smile(
        feature_set=opensmile.FeatureSet.eGeMAPSv02,
        feature_level=opensmile.FeatureLevel.LowLevelDescriptors,
    )

    extracted: dict[str, ParaverbalRawFeatures] = {}
    with tempfile.TemporaryDirectory(prefix="virtual-patient-paraverbal-") as directory:
        temp_dir = Path(directory)
        for turn in turns:
            result = _analyze_turn(
                audio_path,
                turn,
                temp_dir,
                smile=smile,
                min_voiced_duration_ms=min_voiced_duration_ms,
            )
            if result is not None:
                extracted[turn.turn_id] = result

    return extracted


def _analyze_turn(
    audio_path: Path,
    turn: StudentTurnAudio,
    temp_dir: Path,
    *,
    smile: object,
    min_voiced_duration_ms: int,
) -> ParaverbalRawFeatures | None:
    duration_ms = turn.end_ms - turn.start_ms
    if duration_ms <= 0:
        return None
    wav_path = temp_dir / f"{turn.turn_id}.wav"
    try:
        _decode_segment(audio_path, wav_path, turn.start_ms, duration_ms)
        samples, sample_rate = _read_pcm_wav(wav_path)
        if not samples or sample_rate <= 0:
            return None
        return _extract_raw_features(
            wav_path,
            samples,
            duration_ms,
            turn.transcript,
            smile=smile,
            min_voiced_duration_ms=min_voiced_duration_ms,
        )
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


def _extract_raw_features(
    wav_path: Path,
    samples: list[float],
    turn_duration_ms: int,
    transcript: str,
    *,
    smile: object,
    min_voiced_duration_ms: int,
) -> ParaverbalRawFeatures | None:
    """Run OpenSMILE once and assemble raw signals plus a quality summary.

    Emits raw F0 samples (voiced frames, in semitones), loudness samples, and
    every contiguous unvoiced segment as a raw pause duration. No derivation and
    no labels are produced here.
    """
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
    if voiced_duration_ms < min_voiced_duration_ms:
        issues.append("insufficient_voiced_duration")
    if max((abs(sample) for sample in samples), default=0) >= 0.999:
        issues.append("clipping_detected")

    pause_segments_ms = _raw_pause_segments_ms(pitch_values, frame_duration_ms)
    word_count = len([word for word in transcript.split() if word.strip(".,;:!?¿¡()[]{}\"'")])

    return ParaverbalRawFeatures(
        word_count=word_count,
        voiced_duration_ms=voiced_duration_ms,
        f0_samples_semitones=voiced_values,
        loudness_samples=loudness_values,
        pause_segments_ms=pause_segments_ms,
        turn_duration_ms=turn_duration_ms,
        extractor={
            "name": EXTRACTOR_NAME,
            "version": EXTRACTOR_VERSION,
            "feature_set": FEATURE_SET,
        },
        audio_quality={
            "valid_ratio": _round(len(voiced_values) / max(len(pitch_values), 1)),
            "issues": issues,
        },
    )


def _find_column(columns: Iterable[str], fragment: str) -> str | None:
    return next((column for column in columns if fragment.lower() in column.lower()), None)


def _finite_values(values: Iterable[object]) -> list[float]:
    return [float(value) for value in values if isinstance(value, (int, float)) and math.isfinite(float(value))]


def _raw_pause_segments_ms(pitch_values: list[float], frame_duration_ms: float) -> list[float]:
    """Return every contiguous unvoiced segment duration, unfiltered.

    Pause filtering by ``min_pause_ms`` is a derivation step and is applied
    downstream in preprocessing, not here.
    """
    segments: list[float] = []
    current_frames = 0
    for value in pitch_values:
        if value <= 0:
            current_frames += 1
            continue
        if current_frames:
            segments.append(current_frames * frame_duration_ms)
            current_frames = 0
    if current_frames:
        segments.append(current_frames * frame_duration_ms)
    return segments


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None and math.isfinite(value) else None
