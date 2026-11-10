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
import hashlib
import logging
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from time import perf_counter

from app.multimodal.schemas import ParaverbalRawFeatures
from app.utils.runtime_metrics import current_rss_mb, process_id


logger = logging.getLogger(__name__)


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
    message_id: int | None = None


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
    except ImportError as error:
        raise RuntimeError("OpenSMILE runtime dependencies are unavailable") from error

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
    started_at = perf_counter()
    duration_ms = turn.end_ms - turn.start_ms
    if duration_ms <= 0:
        return None
    wav_path = temp_dir / f"{turn.turn_id}.wav"
    try:
        _decode_segment(audio_path, wav_path, turn.start_ms, duration_ms)
        samples, sample_rate = _read_pcm_wav(wav_path)
        if not samples or sample_rate <= 0:
            return None
        result = _extract_raw_features(
            wav_path,
            samples,
            duration_ms,
            turn.transcript,
            smile=smile,
            min_voiced_duration_ms=min_voiced_duration_ms,
            turn_start_ms=turn.start_ms,
        )
        if result is not None:
            result.transcript_ref = {"turn_id": turn.turn_id, "message_id": turn.message_id,
                                     "sha256": hashlib.sha256(turn.transcript.encode('utf-8')).hexdigest()}
        logger.info(
            "performance_event component=paraverbal operation=turn_extraction phase=complete "
            "turn_id=%s segment_duration_ms=%s duration_ms=%.3f voiced_duration_ms=%s "
            "vad_speech_ms=%s issues=%s worker_pid=%s worker_rss_mb=%s",
            turn.turn_id, duration_ms, (perf_counter() - started_at) * 1000,
            result.voiced_duration_ms if result else None,
            result.audio_quality.get("vad_speech_duration_ms") if result else None,
            result.audio_quality.get("issues") if result else ["features_unavailable"],
            process_id(), current_rss_mb(),
        )
        return result
    except (OSError, subprocess.SubprocessError, wave.Error, ValueError) as error:
        logger.exception(
            "performance_event component=paraverbal operation=turn_extraction phase=failed "
            "turn_id=%s segment_duration_ms=%s duration_ms=%.3f error_type=%s "
            "worker_pid=%s worker_rss_mb=%s",
            turn.turn_id, duration_ms, (perf_counter() - started_at) * 1000,
            type(error).__name__, process_id(), current_rss_mb(),
        )
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
    turn_start_ms: int = 0,
) -> ParaverbalRawFeatures | None:
    """Run OpenSMILE once and assemble raw signals plus a quality summary.

    Emit timestamped F0 and loudness samples inside Silero speech intervals.
    """
    try:
        frame = smile.process_file(str(wav_path))
    except Exception:  # noqa: BLE001 - VAD remains independently usable.
        logger.exception("OpenSMILE extraction failed")
        frame = None
    pitch_column = _find_column(frame.columns, "F0semitoneFrom27.5Hz") if frame is not None else None
    loudness_column = _find_column(frame.columns, "loudness") if frame is not None else None

    from app.paraverbal.silero_vad import detect_speech, MODEL_VERSION, MODEL_SHA256, THRESHOLD, MIN_GAP_MS
    intervals, probabilities = detect_speech(samples[:round(turn_duration_ms * 16)])
    # Use decoded signal length, not the requested window, which can exceed
    # the available bytes when media is truncated.
    with wave.open(str(wav_path), "rb") as decoded:
        decoded_duration_ms = decoded.getnframes() * 1000 / decoded.getframerate()
    voiced_duration_ms = round(sum(end - start for start, end in intervals))
    timestamps = ([(start.total_seconds() + end.total_seconds()) * 500
                  for start, end in zip(frame.index.get_level_values('start'), frame.index.get_level_values('end'))]
                  if frame is not None and not frame.empty else [])
    speech_rows = [index for index, timestamp in enumerate(timestamps)
                   if any(start <= timestamp < end for start, end in intervals)]
    pitch_pairs = [(timestamps[index], float(frame[pitch_column].iloc[index])) for index in speech_rows
                   if pitch_column is not None and math.isfinite(float(frame[pitch_column].iloc[index])) and float(frame[pitch_column].iloc[index]) > 0]
    loudness_pairs = [(timestamps[index], float(frame[loudness_column].iloc[index])) for index in speech_rows
                      if loudness_column is not None and math.isfinite(float(frame[loudness_column].iloc[index]))]

    issues: list[str] = []
    if pitch_column is None:
        issues.append("f0_unavailable")
    if loudness_column is None:
        issues.append("loudness_unavailable")
    if abs(decoded_duration_ms - turn_duration_ms) > 500:
        issues.append("truncated_audio")
    if voiced_duration_ms < min_voiced_duration_ms:
        issues.append("insufficient_voiced_duration")
    clipped_samples = sum(abs(sample) >= 0.999 for sample in samples)
    if clipped_samples:
        issues.append("clipping_detected")
    if samples and clipped_samples == len(samples):
        issues.append("clipping_unusable")

    pause_segments_ms = [right[0] - left[1] for left, right in zip(intervals, intervals[1:])]
    words = [word for word in transcript.split() if word.strip(".,;:!?¿¡()[]{}\"'")]
    word_count = len(words) if words else None

    return ParaverbalRawFeatures(
        word_count=word_count,
        voiced_duration_ms=voiced_duration_ms,
        f0_samples_semitones=[value for _, value in pitch_pairs],
        loudness_samples=[value for _, value in loudness_pairs],
        pause_segments_ms=pause_segments_ms,
        turn_duration_ms=turn_duration_ms,
        vad_speech_intervals_ms=intervals,
        vad_probabilities=probabilities,
        vad_model={'version': MODEL_VERSION, 'sha256': MODEL_SHA256, 'threshold': THRESHOLD, 'min_gap_ms': MIN_GAP_MS, 'padding_ms': 0},
        audio_start_ms=turn_start_ms,
        f0_timestamps_ms=[time + turn_start_ms for time, _ in pitch_pairs],
        loudness_timestamps_ms=[time + turn_start_ms for time, _ in loudness_pairs],
        extractor={
            "name": EXTRACTOR_NAME,
            "version": EXTRACTOR_VERSION,
            "feature_set": FEATURE_SET,
        },
        audio_quality={
            "decoded_duration_ms": round(decoded_duration_ms),
            "requested_duration_ms": turn_duration_ms,
            "vad_speech_duration_ms": voiced_duration_ms,
            "clipped_samples": clipped_samples,
            "clipped_ratio": clipped_samples / len(samples) if samples else None,
            "issues": issues,
        },
    )


def _find_column(columns: Iterable[str], fragment: str) -> str | None:
    return next((column for column in columns if fragment.lower() in column.lower()), None)
