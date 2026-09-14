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

    extracted: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="virtual-patient-paraverbal-") as directory:
        temp_dir = Path(directory)
        for turn in turns:
            result = _analyze_turn(audio_path, turn, temp_dir)
            if result is not None:
                extracted[turn.turn_id] = result

    return extracted


def _analyze_turn(
    audio_path: Path,
    turn: StudentTurnAudio,
    temp_dir: Path,
) -> dict[str, Any] | None:
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
) -> dict[str, Any] | None:
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
        "speech_rate_wpm": _round(word_count / total_seconds * 60) if total_seconds else None,
        "articulation_rate_wpm": _round(word_count / voiced_seconds * 60) if voiced_seconds else None,
        "pause_count": len(pause_durations),
        "total_pause_duration_ms": round(sum(pause_durations)),
        "median_pause_duration_ms": _round(_median_or_none(pause_durations)),
        "pause_time_ratio": _round(sum(pause_durations) / turn_duration_ms) if turn_duration_ms else None,
        "f0_median_semitones": _round(_median_or_none(voiced_values)),
        "f0_p20_p80_range_semitones": _round(_percentile_range(voiced_values, 0.2, 0.8)),
        "median_loudness": _round(loudness_median),
        "loudness_p20_p80_range": _round(_percentile_range(loudness_values, 0.2, 0.8)),
        "audio_quality": {
            "valid_ratio": _round(len(voiced_values) / max(len(pitch_values), 1)),
            "issues": issues,
        },
    }
    observation["interpretability"] = _temporal_interpretability(
        observation,
        turn_duration_ms=turn_duration_ms,
    )
    return observation


def _temporal_interpretability(
    observation: dict[str, Any],
    *,
    turn_duration_ms: float | None = None,
) -> dict[str, Any]:
    """Build a traceable temporal interpretation using provisional thresholds."""
    raw_keys = (
        "speech_rate_wpm",
        "articulation_rate_wpm",
        "pause_count",
        "total_pause_duration_ms",
        "median_pause_duration_ms",
        "pause_time_ratio",
    )
    raw = {key: observation[key] for key in raw_keys if observation.get(key) is not None}
    speaking_rate = observation.get("speech_rate_wpm")
    articulation_rate = observation.get("articulation_rate_wpm")
    pause_count = observation.get("pause_count")
    pause_median = observation.get("median_pause_duration_ms")
    pause_ratio = observation.get("pause_time_ratio")
    derived: dict[str, float] = {}
    if speaking_rate is not None and articulation_rate is not None:
        derived["rate_gap_wpm"] = _round(articulation_rate - speaking_rate)
        if articulation_rate > 0:
            derived["speaking_to_articulation_ratio"] = _round(
                speaking_rate / articulation_rate
            )
    pause_frequency = None
    if pause_count is not None and turn_duration_ms and turn_duration_ms > 0:
        pause_frequency = _round(pause_count / (turn_duration_ms / 60_000))
        derived["pause_frequency_per_min"] = pause_frequency

    labels = {
        key: value
        for key, value in {
            "global_rate": _three_band_label(
                speaking_rate, 110, 170,
                "ritmo_global_bajo", "ritmo_global_tipico", "ritmo_global_alto",
            ),
            "articulation": _three_band_label(
                articulation_rate, 130, 190,
                "articulacion_baja", "articulacion_tipica", "articulacion_alta",
            ),
            "pause_load": _three_band_label(
                pause_ratio, 0.15, 0.30,
                "carga_pausas_baja", "carga_pausas_tipica", "carga_pausas_alta",
            ),
            "pause_duration": _three_band_label(
                pause_median, 500, 1000,
                "pausas_predominantemente_breves",
                "pausas_duracion_tipica",
                "pausas_predominantemente_largas",
            ),
            "pause_frequency": _three_band_label(
                pause_frequency, 6, 12,
                "frecuencia_pausas_baja",
                "frecuencia_pausas_tipica",
                "frecuencia_pausas_alta",
            ),
        }.items()
        if value is not None
    }
    labels["temporal_profile"] = _composite_temporal_label(labels)
    return {
        "acoustic_temporal": {
            "raw": raw,
            "derived": derived,
            "roles": {
                "speech_rate_wpm": "principal_global_rate",
                "articulation_rate_wpm": "principal_effective_production_rate",
                "pause_time_ratio": "principal_relative_silence_load",
                "median_pause_duration_ms": "principal_typical_pause_duration",
                "pause_count": "support_duration_dependent",
                "total_pause_duration_ms": "support_duration_dependent",
            },
            "labels": {
                "status": "provisional",
                "values": labels,
            },
            "calibration": {
                "status": "initial_thresholds",
                "strategy": "fixed_initial_reference_ranges",
                "version": "temporal_initial_v1",
                "thresholds": {
                    "speech_rate_wpm": {"low_below": 110, "high_above": 170},
                    "articulation_rate_wpm": {"low_below": 130, "high_above": 190},
                    "pause_time_ratio": {"low_below": 0.15, "high_above": 0.30},
                    "median_pause_duration_ms": {"low_below": 500, "high_above": 1000},
                    "pause_frequency_per_min": {"low_below": 6, "high_above": 12},
                },
                "limitations": [
                    "provisional_non_clinical_thresholds",
                    "pending_reference_corpus_validation",
                    "pause_frequency_is_normalized_by_turn_duration",
                ],
            },
            "scope": {
                "describes": "temporal_organization_of_speech",
                "does_not_infer": [
                    "empathy",
                    "attention",
                    "anxiety",
                    "professionalism",
                    "communication_quality",
                ],
            },
        }
    }


def _three_band_label(
    value: float | int | None,
    lower: float,
    upper: float,
    low_label: str,
    typical_label: str,
    high_label: str,
) -> str | None:
    if value is None:
        return None
    if value < lower:
        return low_label
    if value > upper:
        return high_label
    return typical_label


def _composite_temporal_label(labels: dict[str, str]) -> str:
    """Apply the documented ordered taxonomy for one descriptive profile."""
    global_rate = labels.get("global_rate")
    articulation = labels.get("articulation")
    pause_load = labels.get("pause_load")
    pause_duration = labels.get("pause_duration")
    pause_frequency = labels.get("pause_frequency")
    low_or_typical_load = pause_load in {
        "carga_pausas_baja",
        "carga_pausas_tipica",
    }

    if (
        global_rate == "ritmo_global_tipico"
        and articulation == "articulacion_tipica"
        and pause_load == "carga_pausas_tipica"
    ):
        return "patron_temporal_tipico"
    if articulation == "articulacion_baja" and low_or_typical_load:
        return "ritmo_lento_continuo"
    if (
        articulation == "articulacion_alta"
        and global_rate == "ritmo_global_alto"
        and low_or_typical_load
    ):
        return "ritmo_rapido_continuo"
    if (
        global_rate == "ritmo_global_bajo"
        and articulation in {"articulacion_tipica", "articulacion_alta"}
        and pause_load == "carga_pausas_alta"
    ):
        return "ritmo_reducido_por_pausas"
    if (
        articulation == "articulacion_alta"
        and global_rate in {"ritmo_global_tipico", "ritmo_global_bajo"}
        and pause_load == "carga_pausas_alta"
    ):
        return "rafagas_rapidas_con_pausas"
    if (
        pause_frequency == "frecuencia_pausas_alta"
        and pause_duration == "pausas_predominantemente_breves"
        and pause_load in {"carga_pausas_tipica", "carga_pausas_alta"}
    ):
        return "fragmentado_por_pausas_breves"
    if (
        pause_frequency in {
            "frecuencia_pausas_baja",
            "frecuencia_pausas_tipica",
        }
        and pause_duration == "pausas_predominantemente_largas"
        and pause_load == "carga_pausas_alta"
    ):
        return "intermitente_por_pausas_largas"
    if pause_load == "carga_pausas_alta":
        return "alta_carga_de_pausas"
    return "patron_mixto_no_clasificado"


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


def _percentile_range(
    values: Iterable[float],
    lower_quantile: float,
    upper_quantile: float,
) -> float | None:
    sequence = sorted(values)
    if len(sequence) < 2:
        return None
    return _percentile(sequence, upper_quantile) - _percentile(sequence, lower_quantile)


def _percentile(sequence: list[float], quantile: float) -> float:
    position = (len(sequence) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return sequence[lower_index]
    fraction = position - lower_index
    return sequence[lower_index] + (
        sequence[upper_index] - sequence[lower_index]
    ) * fraction


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None and math.isfinite(value) else None
