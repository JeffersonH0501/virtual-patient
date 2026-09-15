"""Pure, in-memory single-chunk OpenSMILE debug extraction.

This module decodes a short audio chunk, runs OpenSMILE (eGeMAPSv02, low-level
descriptors) over it, and returns a single representative frame-level value per
displayed signal for the calibration debug tool. These are recent per-frame LLD
values chosen only for live display; they are NOT turn-level aggregate features
and no derivation, thresholding, labeling, or persistence happens here.

A minimal ffmpeg decode helper is duplicated locally (mono / 16 kHz / 16-bit PCM
WAV) to match the production extractor's decode contract without importing or
modifying it.

eGeMAPSv02 LowLevelDescriptors column names (grounded on the audeering
opensmile-python docs; the package was not importable in the development
environment when this module was written, so columns are matched by fragment):
``F0semitoneFrom27.5Hz_sma3nz`` (F0), ``Loudness_sma3`` (loudness), and, for a
voicing-related signal, ``HNRdBACF_sma3nz`` preferred, else ``jitterLocal_sma3nz``,
else a boolean voiced flag derived from F0 > 0.
"""

from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable
import time

from app.debug.schemas import OpenSmileFeatureNames, OpenSmileFrameDebug


FEATURE_SET = "eGeMAPSv02"

F0_FRAGMENT = "F0semitoneFrom27.5Hz"
LOUDNESS_FRAGMENT = "loudness"
# Voicing-related fragments in preference order. eGeMAPSv02 LLDs expose no raw
# voicing-probability column, so we pick the closest genuinely available signal.
HNR_FRAGMENT = "HNRdBACF"
JITTER_FRAGMENT = "jitterLocal"


class OpenSmileDebugUnavailable(RuntimeError):
    """Raised when OpenSMILE (or its decode step) cannot run.

    The router converts this into an HTTP 503 debug-unavailable response instead
    of a 500 stack trace.
    """


def process_audio_chunk(
    audio_bytes: bytes,
    *,
    content_type: str | None,
    frame_timestamp_ms: float | None,
) -> OpenSmileFrameDebug:
    """Decode a short audio chunk and return representative frame-level values.

    The incoming bytes are written to a temporary file, decoded to mono 16 kHz
    16-bit PCM WAV via ffmpeg, and analyzed with OpenSMILE LLDs. All temporary
    files are deleted before returning; nothing is persisted. Missing signals
    are returned as ``None`` with a reason.
    """
    start = time.perf_counter()
    try:
        import opensmile
    except Exception as error:  # noqa: BLE001 - report any import failure uniformly
        raise OpenSmileDebugUnavailable(f"OpenSMILE import failed: {error}") from error

    with tempfile.TemporaryDirectory(prefix="virtual-patient-debug-audio-") as directory:
        temp_dir = Path(directory)
        source_path = temp_dir / f"chunk{_suffix_for(content_type)}"
        wav_path = temp_dir / "chunk.wav"
        source_path.write_bytes(audio_bytes)
        try:
            _decode_to_wav(source_path, wav_path)
        except (OSError, subprocess.SubprocessError) as error:
            raise OpenSmileDebugUnavailable(
                f"Audio decode failed: {error}"
            ) from error

        try:
            smile = opensmile.Smile(
                feature_set=opensmile.FeatureSet.eGeMAPSv02,
                feature_level=opensmile.FeatureLevel.LowLevelDescriptors,
            )
            frame = smile.process_file(str(wav_path))
        except Exception as error:  # noqa: BLE001 - any analysis failure is unavailable
            raise OpenSmileDebugUnavailable(
                f"OpenSMILE analysis failed: {error}"
            ) from error

    reasons: dict[str, str] = {}
    feature_names = OpenSmileFeatureNames()

    columns = list(getattr(frame, "columns", []))
    is_empty = bool(getattr(frame, "empty", True))

    f0_column = _find_column(columns, F0_FRAGMENT)
    loudness_column = _find_column(columns, LOUDNESS_FRAGMENT)
    feature_names.f0 = f0_column
    feature_names.loudness = loudness_column

    f0_value: float | None = None
    loudness_value: float | None = None
    if is_empty:
        reasons["f0_semitones"] = "no_audio_frames"
        reasons["loudness"] = "no_audio_frames"
    else:
        f0_value = _representative_value(frame, f0_column, reasons, "f0_semitones")
        loudness_value = _representative_value(
            frame, loudness_column, reasons, "loudness"
        )

    voicing_value, voicing_kind = _resolve_voicing(
        frame, columns, is_empty, feature_names, reasons
    )

    return OpenSmileFrameDebug(
        f0_semitones=f0_value,
        loudness=loudness_value,
        voicing=voicing_value,
        voicing_kind=voicing_kind,
        feature_names=feature_names,
        feature_set=FEATURE_SET,
        frame_timestamp_ms=frame_timestamp_ms,
        processing_ms=round((time.perf_counter() - start) * 1000, 3),
        reasons=reasons,
    )


def _resolve_voicing(
    frame: Any,
    columns: list[str],
    is_empty: bool,
    feature_names: OpenSmileFeatureNames,
    reasons: dict[str, str],
) -> tuple[float | None, str | None]:
    """Pick the best available voicing-related signal for display.

    Preference: HNR (``HNRdBACF``) -> jitter (``jitterLocal``) -> a boolean
    voiced flag derived from F0 > 0. The real column used (or the derived kind)
    is recorded so the UI never implies a raw voicing probability exists.
    """
    if is_empty:
        reasons["voicing"] = "no_audio_frames"
        return None, None

    hnr_column = _find_column(columns, HNR_FRAGMENT)
    if hnr_column is not None:
        value = _representative_value(frame, hnr_column, reasons, "voicing")
        feature_names.voicing = hnr_column
        return value, "hnr_dbacf"

    jitter_column = _find_column(columns, JITTER_FRAGMENT)
    if jitter_column is not None:
        value = _representative_value(frame, jitter_column, reasons, "voicing")
        feature_names.voicing = jitter_column
        return value, "jitter_local"

    # Derive a voiced flag from F0 when no dedicated voicing LLD is present.
    f0_column = _find_column(columns, F0_FRAGMENT)
    if f0_column is not None:
        values = _finite_values(frame[f0_column].tolist())
        if values:
            voiced = 1.0 if any(value > 0 for value in values) else 0.0
            feature_names.voicing = None
            reasons["voicing"] = "f0_derived_voiced_flag"
            return voiced, "f0_derived"
    reasons["voicing"] = "no_voicing_signal"
    return None, None


def _representative_value(
    frame: Any,
    column: str | None,
    reasons: dict[str, str],
    field: str,
) -> float | None:
    """Return the median finite per-frame value for display, or ``None``.

    This is only a recent frame value for display, not a turn aggregate. The
    median is used to avoid a single spurious frame dominating the readout.
    """
    if column is None:
        reasons[field] = "column_missing"
        return None
    values = _finite_values(frame[column].tolist())
    if not values:
        reasons[field] = "no_finite_values"
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[middle], 4)
    return round((ordered[middle - 1] + ordered[middle]) / 2, 4)


def _decode_to_wav(source_path: Path, wav_path: Path) -> None:
    """Decode any container to mono 16 kHz 16-bit PCM WAV via ffmpeg.

    This mirrors the production extractor's decode contract (mono, 16 kHz,
    ``pcm_s16le``) without importing it, so the extractor stays untouched.
    """
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(source_path),
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
        timeout=30,
    )


def _suffix_for(content_type: str | None) -> str:
    mapping = {
        "audio/webm": ".webm",
        "video/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/mp4": ".m4a",
        "video/mp4": ".mp4",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/wave": ".wav",
    }
    return mapping.get((content_type or "").split(";")[0].strip().lower(), ".bin")


def _find_column(columns: Iterable[str], fragment: str) -> str | None:
    return next(
        (column for column in columns if fragment.lower() in str(column).lower()),
        None,
    )


def _finite_values(values: Iterable[object]) -> list[float]:
    return [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and math.isfinite(float(value))
    ]
