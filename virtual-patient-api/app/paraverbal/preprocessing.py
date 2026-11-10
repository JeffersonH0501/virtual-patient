"""Paraverbal derivation: raw acoustic signals -> processed features.

This module owns the paraverbal *derivation* stage of the multimodal pipeline
(Requirement 7). It consumes :class:`~app.multimodal.schemas.ParaverbalRawFeatures`
emitted by the OpenSMILE extractor and the methodology parameter
``min_pause_ms``, and produces
:class:`~app.multimodal.schemas.ParaverbalProcessedFeatures`.

Design boundaries preserved here:

* Pure, in-memory, and deterministic. No I/O, no OpenSMILE, no config-file
  reading. ``min_pause_ms`` is a technical derivation constant
  (:data:`MIN_PAUSE_MS`) that tunes how pauses are segmented; it is not a
  research threshold and defaults in-module.
* Derivation only. This module computes descriptive numeric features. It does
  NOT threshold, band, or emit any base or integrated labels — that is the
  threshold/label engines' responsibility.
* Descriptive-only. The outputs are behavioural/acoustic observations, never
  measures of empathy, attention, warmth, or any psychological state.
* Fundamental frequency is expressed in semitones only, never in Hertz
  (Requirement 7.6).
* Any feature that cannot be computed from the available signal (empty samples,
  zero or missing duration, missing baseline) is ``None`` — never a fabricated
  value (Requirement 24.3).

Formulas (Requirement 7):

* ``speech_rate_wpm``      = ``word_count / (turn_duration_ms / 60000)`` — words
  over the full turn duration (includes pause time).
* ``articulation_rate_wpm``= ``word_count / (voiced_duration_ms / 60000)`` —
  words over voiced/speaking time only (excludes pause/silence time). The
  denominator is ``voiced_duration_ms``: this preserves the established
  articulation-rate semantics of the pre-refactor extractor
  (``word_count / voiced_seconds * 60``) and matches the design's intent that
  articulation rate excludes pauses.
* Pauses: only ``pause_segments_ms`` entries ``>= min_pause_ms`` are counted.
  From those valid pauses derive ``pause_count``, ``total_pause_duration_ms``,
  and ``median_pause_duration_ms``.
* ``pause_frequency_per_min`` = ``pause_count / (turn_duration_ms / 60000)``.
* ``pause_time_ratio``        = ``total_pause_duration_ms / turn_duration_ms``.
* ``median_loudness``         = median(``loudness_samples``).
* ``f0_median_semitones``     = median(``f0_samples_semitones``).
* ``f0_p20_p80_range_semitones`` = P80 - P20 of ``f0_samples_semitones``.
* ``loudness_p20_p80_range``     = P80 - P20 of ``loudness_samples``.

Percentile method: linear interpolation between closest ranks on a sorted
sample, matching the NumPy default ("linear"/type-7) definition. For a fraction
``q`` in [0, 1] and ``n`` sorted values, the rank is ``q * (n - 1)``; the result
interpolates linearly between the two bracketing samples. A single sample
returns that sample for any percentile.
"""

from __future__ import annotations

from typing import Sequence

from app.multimodal.schemas import (
    ParaverbalProcessedFeatures,
    ParaverbalRawFeatures,
)

_MS_PER_MINUTE = 60_000.0
_P20 = 0.20
_P80 = 0.80
_ROUND_DIGITS = 3

# Technical derivation constant (not a research threshold): the minimum silence
# duration counted as a pause. This tunes how pauses are segmented from the
# acoustic signal, not a label band, so it lives here as a fixed engineering
# default rather than in the methodology config.
MIN_PAUSE_MS = 500.0


def preprocess_paraverbal(
    raw: ParaverbalRawFeatures,
    *,
    min_pause_ms: float = MIN_PAUSE_MS,
) -> ParaverbalProcessedFeatures:
    """Derive processed paraverbal features from raw signals.

    Args:
        raw: Signal-level features from the OpenSMILE extractor.
        min_pause_ms: Technical derivation constant (defaults to
            :data:`MIN_PAUSE_MS`). Only contiguous silence segments of at least
            this duration are counted as pauses.

    Returns:
        A :class:`ParaverbalProcessedFeatures` with every non-derivable feature
        set to ``None`` (never a fabricated value).
    """
    intervals = raw.vad_speech_intervals_ms
    if intervals:
        if any(start < 0 or end <= start or end > raw.turn_duration_ms for start, end in intervals) or any(
            left[1] > right[0] for left, right in zip(intervals, intervals[1:])
        ):
            raise ValueError('VAD intervals must be ordered and inside the turn')
        turn_duration_ms = intervals[-1][1] - intervals[0][0]
        voiced_duration_ms = sum(end - start for start, end in intervals)
        pause_segments = [right[0] - left[1] for left, right in zip(intervals, intervals[1:])]
    else:
        turn_duration_ms = None
        voiced_duration_ms = None
        pause_segments = None
    turn_minutes = _to_minutes(turn_duration_ms)

    # Global speech rate: words over the full turn duration (includes pauses).
    speech_rate_wpm = _rate_per_minute(raw.word_count, turn_minutes)

    # Articulation rate: words over voiced/speaking time only (excludes pauses).
    # Denominator is voiced_duration_ms, preserving the pre-refactor semantics.
    articulation_rate_wpm = _rate_per_minute(
        raw.word_count, _to_minutes(voiced_duration_ms)
    )

    # Pause statistics from valid pauses (>= min_pause_ms). When the methodology
    # threshold is undecided (None), pause-derived features are unavailable.
    (
        pause_count,
        total_pause_duration_ms,
        median_pause_duration_ms,
    ) = _pause_statistics(pause_segments, min_pause_ms)

    pause_frequency_per_min = (
        _rate_per_minute(pause_count, turn_minutes)
        if pause_count is not None
        else None
    )
    pause_time_ratio = (
        _round(total_pause_duration_ms / turn_duration_ms)
        if total_pause_duration_ms is not None
        and turn_duration_ms is not None
        and turn_duration_ms > 0
        else None
    )

    median_loudness = _round(_median_or_none(raw.loudness_samples))
    f0_median_semitones = _round(_median_or_none(raw.f0_samples_semitones))
    f0_p20_p80_range_semitones = _round(
        _percentile_range(raw.f0_samples_semitones, _P20, _P80)
    )
    loudness_p20_p80_range = _round(
        _percentile_range(raw.loudness_samples, _P20, _P80)
    )

    return ParaverbalProcessedFeatures(
        speech_rate_wpm=speech_rate_wpm,
        articulation_rate_wpm=articulation_rate_wpm,
        speech_window_duration_ms=turn_duration_ms,
        speech_active_duration_ms=voiced_duration_ms,
        pause_count=pause_count,
        total_pause_duration_ms=total_pause_duration_ms,
        median_pause_duration_ms=median_pause_duration_ms,
        pause_frequency_per_min=pause_frequency_per_min,
        pause_time_ratio=pause_time_ratio,
        median_loudness=median_loudness,
        f0_median_semitones=f0_median_semitones,
        f0_p20_p80_range_semitones=f0_p20_p80_range_semitones,
        loudness_p20_p80_range=loudness_p20_p80_range,
    )


# ---------------------------------------------------------------------------
# Derivation helpers (pure, deterministic)
# ---------------------------------------------------------------------------


def _pause_statistics(
    pause_segments_ms: Sequence[float] | None,
    min_pause_ms: float | None,
) -> tuple[int | None, float | None, float | None]:
    """Return (pause_count, total_pause_duration_ms, median_pause_duration_ms).

    Only segments with duration ``>= min_pause_ms`` are counted (Requirement
    7.5). When ``min_pause_ms`` is ``None`` the methodology is undecided, so all
    three statistics are ``None`` (feature_unavailable) rather than computed
    against an invented threshold.
    """
    if min_pause_ms is None or pause_segments_ms is None:
        return None, None, None

    valid_pauses = [
        float(duration)
        for duration in pause_segments_ms
        if duration is not None and float(duration) >= min_pause_ms
    ]
    pause_count = len(valid_pauses)
    total_pause_duration_ms = _round(sum(valid_pauses))
    median_pause_duration_ms = _round(_median_or_none(valid_pauses))
    return pause_count, total_pause_duration_ms, median_pause_duration_ms


def _to_minutes(duration_ms: float | None) -> float | None:
    """Convert a duration in milliseconds to minutes, or ``None`` if unusable."""
    if duration_ms is None or duration_ms <= 0:
        return None
    return duration_ms / _MS_PER_MINUTE


def _rate_per_minute(count: int | None, minutes: float | None) -> float | None:
    """Return ``count / minutes`` rounded, or ``None`` for a zero/absent span."""
    if count is None or minutes is None or minutes <= 0:
        return None
    return _round(count / minutes)


def _median_or_none(values: Sequence[float]) -> float | None:
    """Median of ``values`` using linear interpolation, or ``None`` if empty."""
    return _percentile(values, 0.5)


def _percentile_range(
    values: Sequence[float], low_fraction: float, high_fraction: float
) -> float | None:
    """Return ``P(high) - P(low)``, or ``None`` when the range is undefined.

    Requires at least two samples; a single sample has a zero-width, ambiguous
    spread that is reported as unavailable rather than a fabricated ``0``.
    """
    if len(values) < 2:
        return None
    low = _percentile(values, low_fraction)
    high = _percentile(values, high_fraction)
    if low is None or high is None:
        return None
    return high - low


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    """Percentile via linear interpolation between closest ranks (NumPy default).

    ``fraction`` is in [0, 1]. For ``n`` sorted values the target rank is
    ``fraction * (n - 1)``; the result interpolates linearly between the two
    bracketing samples. Returns ``None`` for an empty input and the sole value
    for a single-element input. Deterministic and dependency-free.
    """
    ordered = sorted(float(value) for value in values)
    count = len(ordered)
    if count == 0:
        return None
    if count == 1:
        return ordered[0]

    rank = fraction * (count - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, count - 1)
    interpolation_weight = rank - lower_index
    return (
        ordered[lower_index]
        + (ordered[upper_index] - ordered[lower_index]) * interpolation_weight
    )


def _round(value: float | None) -> float | None:
    """Round to a stable precision, passing ``None`` through unchanged."""
    if value is None:
        return None
    return round(value, _ROUND_DIGITS)
