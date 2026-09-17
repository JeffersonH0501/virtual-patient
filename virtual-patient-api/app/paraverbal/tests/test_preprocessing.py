"""Unit tests for paraverbal derivation (``app/paraverbal/preprocessing.py``).

These tests exercise :func:`preprocess_paraverbal` directly against
hand-built :class:`ParaverbalRawFeatures` instances. They verify each
derivation formula (Requirement 7.2-7.6), the ``min_pause_ms`` inclusive pause
filter, the NumPy-default linear-interpolation percentile method, semitone-only
F0 handling, personal-baseline pitch shift, and the null/unavailable paths where
a feature cannot be derived (Requirement 24.3, 28.2).

All expected numbers are computed by hand so the tests stay deterministic and
do not depend on the implementation to define its own truth. Percentiles use the
documented linear interpolation between closest ranks: for ``n`` sorted values
the target rank for fraction ``q`` is ``q * (n - 1)``, interpolating linearly
between the two bracketing samples. Outputs are rounded to 3 decimals by the
module, so ``pytest.approx`` is used for float comparisons.
"""

from __future__ import annotations

import pytest

from app.multimodal.schemas import ParaverbalRawFeatures, PersonalBaseline
from app.paraverbal.preprocessing import preprocess_paraverbal


# ---------------------------------------------------------------------------
# Test fixtures / builders
# ---------------------------------------------------------------------------


def _raw(
    *,
    word_count: int = 0,
    voiced_duration_ms: int = 0,
    f0_samples_semitones: list[float] | None = None,
    loudness_samples: list[float] | None = None,
    pause_segments_ms: list[float] | None = None,
    turn_duration_ms: int = 0,
) -> ParaverbalRawFeatures:
    """Build a raw-features instance with neutral defaults for unused fields.

    ``extractor`` and ``audio_quality`` are irrelevant to derivation, so they
    are filled with minimal placeholder dicts.
    """
    return ParaverbalRawFeatures(
        word_count=word_count,
        voiced_duration_ms=voiced_duration_ms,
        f0_samples_semitones=f0_samples_semitones or [],
        loudness_samples=loudness_samples or [],
        pause_segments_ms=pause_segments_ms or [],
        turn_duration_ms=turn_duration_ms,
        extractor={},
        audio_quality={},
    )


# ---------------------------------------------------------------------------
# Speech rate (Requirement 7.2)
# ---------------------------------------------------------------------------


def test_speech_rate_wpm_uses_full_turn_duration():
    # 45 words over a 30_000 ms (0.5 min) turn -> 45 / 0.5 = 90 wpm.
    raw = _raw(word_count=45, turn_duration_ms=30_000)

    result = preprocess_paraverbal(raw, min_pause_ms=250)

    assert result.speech_rate_wpm == pytest.approx(90.0)


def test_speech_rate_wpm_none_when_turn_duration_zero():
    raw = _raw(word_count=45, turn_duration_ms=0)

    result = preprocess_paraverbal(raw, min_pause_ms=250)

    assert result.speech_rate_wpm is None


# ---------------------------------------------------------------------------
# Articulation rate uses the voiced-duration denominator (Requirement 7.2)
# ---------------------------------------------------------------------------


def test_articulation_rate_wpm_uses_voiced_duration_denominator():
    # 30 words over 20_000 ms voiced time (~0.3333 min) -> 30 / (20000/60000) = 90.
    raw = _raw(word_count=30, voiced_duration_ms=20_000, turn_duration_ms=40_000)

    result = preprocess_paraverbal(raw, min_pause_ms=250)

    assert result.articulation_rate_wpm == pytest.approx(90.0)
    # Global speech rate uses the longer full turn duration, so it is lower.
    assert result.speech_rate_wpm == pytest.approx(45.0)
    assert result.articulation_rate_wpm > result.speech_rate_wpm


def test_articulation_rate_wpm_none_when_voiced_duration_zero():
    raw = _raw(word_count=30, voiced_duration_ms=0, turn_duration_ms=40_000)

    result = preprocess_paraverbal(raw, min_pause_ms=250)

    assert result.articulation_rate_wpm is None


# ---------------------------------------------------------------------------
# Pause filtering with an inclusive >= min_pause_ms boundary (Requirement 7.5)
# ---------------------------------------------------------------------------


def test_pause_filter_is_inclusive_at_exactly_min_pause_ms():
    # Segments below / exactly at / above the 250 ms threshold. Only the two
    # segments >= 250 (250 exactly and 400) count; 100 and 249 are dropped.
    raw = _raw(
        pause_segments_ms=[100.0, 249.0, 250.0, 400.0],
        turn_duration_ms=60_000,
    )

    result = preprocess_paraverbal(raw, min_pause_ms=250)

    assert result.pause_count == 2
    assert result.total_pause_duration_ms == pytest.approx(650.0)  # 250 + 400
    # Median of [250, 400] with linear interpolation -> 325.
    assert result.median_pause_duration_ms == pytest.approx(325.0)


def test_pause_median_single_valid_pause():
    raw = _raw(pause_segments_ms=[120.0, 300.0], turn_duration_ms=60_000)

    result = preprocess_paraverbal(raw, min_pause_ms=250)

    assert result.pause_count == 1
    assert result.total_pause_duration_ms == pytest.approx(300.0)
    assert result.median_pause_duration_ms == pytest.approx(300.0)


def test_pause_count_zero_when_no_segment_meets_threshold():
    raw = _raw(pause_segments_ms=[100.0, 200.0, 249.0], turn_duration_ms=60_000)

    result = preprocess_paraverbal(raw, min_pause_ms=250)

    assert result.pause_count == 0
    assert result.total_pause_duration_ms == pytest.approx(0.0)
    # Median of an empty set of valid pauses is unavailable.
    assert result.median_pause_duration_ms is None


# ---------------------------------------------------------------------------
# Pause frequency and pause time ratio (Requirement 7.3, 7.4)
# ---------------------------------------------------------------------------


def test_pause_frequency_per_min_and_pause_time_ratio():
    # Three valid pauses (300 + 500 + 700 = 1500 ms) over a 60_000 ms (1 min) turn.
    raw = _raw(
        pause_segments_ms=[300.0, 500.0, 700.0],
        turn_duration_ms=60_000,
    )

    result = preprocess_paraverbal(raw, min_pause_ms=250)

    assert result.pause_count == 3
    # pause_frequency_per_min = pause_count / (turn_duration_ms / 60000) = 3 / 1.
    assert result.pause_frequency_per_min == pytest.approx(3.0)
    # pause_time_ratio = total_pause_duration_ms / turn_duration_ms = 1500 / 60000.
    assert result.pause_time_ratio == pytest.approx(0.025)


# ---------------------------------------------------------------------------
# Loudness / F0 medians and percentile ranges via linear interpolation
# (Requirement 7.6 - F0 stays in semitones; no Hz conversion)
# ---------------------------------------------------------------------------


def test_median_loudness_and_loudness_percentile_range():
    # loudness = [0.1, 0.3, 0.5] (n=3):
    #   median  -> rank 1.0 -> 0.3
    #   P20     -> rank 0.4 -> 0.1 + 0.4*(0.3-0.1) = 0.18
    #   P80     -> rank 1.6 -> 0.3 + 0.6*(0.5-0.3) = 0.42
    #   range   -> 0.42 - 0.18 = 0.24
    raw = _raw(loudness_samples=[0.1, 0.3, 0.5], turn_duration_ms=60_000)

    result = preprocess_paraverbal(raw, min_pause_ms=250)

    assert result.median_loudness == pytest.approx(0.3)
    assert result.loudness_p20_p80_range == pytest.approx(0.24)


def test_f0_median_and_percentile_range_in_semitones():
    # f0 (semitones) = [10, 20, 30, 40, 50] (n=5):
    #   median -> rank 2.0 -> 30
    #   P20    -> rank 0.8 -> 10 + 0.8*(20-10) = 18
    #   P80    -> rank 3.2 -> 40 + 0.2*(50-40) = 42
    #   range  -> 42 - 18 = 24
    raw = _raw(
        f0_samples_semitones=[10.0, 20.0, 30.0, 40.0, 50.0],
        turn_duration_ms=60_000,
    )

    result = preprocess_paraverbal(raw, min_pause_ms=250)

    assert result.f0_median_semitones == pytest.approx(30.0)
    assert result.f0_p20_p80_range_semitones == pytest.approx(24.0)


def test_f0_values_are_treated_as_semitones_not_hz():
    # Semitone inputs are used verbatim; if the module converted from Hz the
    # median of these small semitone values would not equal the raw median.
    raw = _raw(f0_samples_semitones=[-2.0, 0.0, 2.0], turn_duration_ms=60_000)

    result = preprocess_paraverbal(raw, min_pause_ms=250)

    # median of [-2, 0, 2] -> 0.0, only meaningful if treated as semitones.
    assert result.f0_median_semitones == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Relative pitch shift vs personal baseline (Requirement 7.6)
# ---------------------------------------------------------------------------


def _baseline(f0_semitones: float) -> PersonalBaseline:
    return PersonalBaseline(
        baseline_f0_semitones=f0_semitones,
        baseline_loudness=0.0,
        neutral_head_yaw=0.0,
        neutral_head_pitch=0.0,
        neutral_head_roll=0.0,
        neutral_gaze_yaw=0.0,
        neutral_gaze_pitch=0.0,
    )


def test_relative_pitch_shift_uses_baseline_when_present():
    # f0 median = 30 semitones; baseline = 24 semitones -> shift = +6.
    raw = _raw(
        f0_samples_semitones=[10.0, 20.0, 30.0, 40.0, 50.0],
        turn_duration_ms=60_000,
    )

    result = preprocess_paraverbal(
        raw, min_pause_ms=250, baseline=_baseline(24.0)
    )

    assert result.f0_median_semitones == pytest.approx(30.0)
    assert result.relative_pitch_shift_st == pytest.approx(6.0)


def test_relative_pitch_shift_none_when_baseline_missing():
    raw = _raw(
        f0_samples_semitones=[10.0, 20.0, 30.0, 40.0, 50.0],
        turn_duration_ms=60_000,
    )

    result = preprocess_paraverbal(raw, min_pause_ms=250, baseline=None)

    assert result.relative_pitch_shift_st is None


def test_relative_pitch_shift_none_when_f0_unavailable_even_with_baseline():
    # No F0 samples -> f0_median is None -> shift is None despite a baseline.
    raw = _raw(f0_samples_semitones=[], turn_duration_ms=60_000)

    result = preprocess_paraverbal(
        raw, min_pause_ms=250, baseline=_baseline(24.0)
    )

    assert result.f0_median_semitones is None
    assert result.relative_pitch_shift_st is None


# ---------------------------------------------------------------------------
# Null / unavailable paths (Requirement 24.3)
# ---------------------------------------------------------------------------


def test_min_pause_ms_none_makes_all_pause_features_unavailable():
    raw = _raw(
        pause_segments_ms=[300.0, 500.0, 700.0],
        turn_duration_ms=60_000,
    )

    result = preprocess_paraverbal(raw, min_pause_ms=None)

    assert result.pause_count is None
    assert result.total_pause_duration_ms is None
    assert result.median_pause_duration_ms is None
    assert result.pause_frequency_per_min is None
    assert result.pause_time_ratio is None


def test_empty_samples_make_dependent_features_unavailable():
    raw = _raw(
        f0_samples_semitones=[],
        loudness_samples=[],
        turn_duration_ms=60_000,
    )

    result = preprocess_paraverbal(raw, min_pause_ms=250)

    assert result.median_loudness is None
    assert result.f0_median_semitones is None
    assert result.f0_p20_p80_range_semitones is None
    assert result.loudness_p20_p80_range is None


def test_zero_turn_duration_makes_rate_features_unavailable():
    raw = _raw(
        word_count=40,
        voiced_duration_ms=0,
        pause_segments_ms=[300.0],
        turn_duration_ms=0,
    )

    result = preprocess_paraverbal(raw, min_pause_ms=250)

    assert result.speech_rate_wpm is None
    assert result.articulation_rate_wpm is None
    assert result.pause_frequency_per_min is None
    assert result.pause_time_ratio is None


def test_single_sample_percentile_range_is_unavailable():
    # A single sample has an ambiguous, zero-width spread reported as None,
    # while the median is still defined for that sole value.
    raw = _raw(
        f0_samples_semitones=[42.0],
        loudness_samples=[0.7],
        turn_duration_ms=60_000,
    )

    result = preprocess_paraverbal(raw, min_pause_ms=250)

    assert result.f0_median_semitones == pytest.approx(42.0)
    assert result.median_loudness == pytest.approx(0.7)
    assert result.f0_p20_p80_range_semitones is None
    assert result.loudness_p20_p80_range is None
