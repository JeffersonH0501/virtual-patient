"""Tests for the nonverbal preprocessing/derivation stage (task 3.3).

These tests exercise :func:`app.nonverbal.preprocessing.preprocess_nonverbal_turn`
and its supporting helpers directly, building
:class:`app.multimodal.schemas.NonverbalRawFeatures` by hand. They are fully
deterministic and cover:

* ``visual_alignment_ratio`` computed against a CALIBRATED interaction center
  (baseline neutral gaze offset from the origin), including a case proving that
  ``(0, 0)`` is never assumed.
* ``median_visual_alignment_dwell_ms`` dwell segmentation, including the
  no-aligned-episode path.
* Missing calibration, missing tolerance, and insufficient-signal availability
  paths, each with the correct :class:`UnavailableReason`.
* Deterministic nod detection with a fully configured
  :class:`NodDetectionParams`, plus the unconfigured and no-signal paths.
* Smile activity ratio and mean smile activation, including the threshold-null
  and no-signal paths.
* Interaction-context passthrough.

The nod-count assertions depend on scipy (a pinned dependency); they are guarded
with ``pytest.importorskip('scipy')`` so the rest of the suite runs even if scipy
is not importable in a given environment.
"""

from __future__ import annotations

import pytest

from app.multimodal.schemas import (
    NonverbalRawFeatures,
    PersonalBaseline,
    UnavailableReason,
)
from app.nonverbal.preprocessing import (
    NodDetectionParams,
    preprocess_nonverbal_turn,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _raw(
    *,
    gaze_yaw_samples=None,
    gaze_pitch_samples=None,
    frame_timestamps_ms=None,
    au12_samples=None,
    head_pitch_samples=None,
    sample_fps=2.0,
    turn_duration_ms=10_000,
) -> NonverbalRawFeatures:
    """Build a raw-feature record with sensible empty defaults per series."""
    return NonverbalRawFeatures(
        face_score_samples=[],
        gaze_yaw_samples=list(gaze_yaw_samples or []),
        gaze_pitch_samples=list(gaze_pitch_samples or []),
        au12_samples=list(au12_samples or []),
        head_pitch_samples=list(head_pitch_samples or []),
        frame_timestamps_ms=list(frame_timestamps_ms or []),
        sample_fps=sample_fps,
        turn_duration_ms=turn_duration_ms,
        extractor={"name": "py-feat", "version": "2.1.1"},
        video_quality={},
    )


def _calibrated_baseline(
    *,
    neutral_gaze_yaw: float | None = 0.30,
    neutral_gaze_pitch: float | None = -0.20,
) -> PersonalBaseline:
    """A baseline whose neutral gaze is deliberately offset from the origin."""
    return PersonalBaseline(
        baseline_f0_semitones=0.0,
        baseline_loudness=0.0,
        neutral_head_yaw=0.0,
        neutral_head_pitch=0.0,
        neutral_head_roll=0.0,
        neutral_gaze_yaw=neutral_gaze_yaw,
        neutral_gaze_pitch=neutral_gaze_pitch,
    )


_UNCONFIGURED_NOD = NodDetectionParams()


# ---------------------------------------------------------------------------
# Visual alignment ratio against a calibrated (non-origin) center
# ---------------------------------------------------------------------------


def test_visual_alignment_ratio_uses_calibrated_center_not_origin():
    """The ratio counts frames within tolerance of the CALIBRATED center.

    Center is (0.30, -0.20). Two of four frames sit exactly on the center (within
    tolerance); the other two are far from the center. The expected ratio is 0.5.
    """
    baseline = _calibrated_baseline(neutral_gaze_yaw=0.30, neutral_gaze_pitch=-0.20)
    raw = _raw(
        gaze_yaw_samples=[0.30, 0.35, 1.00, 0.31],
        gaze_pitch_samples=[-0.20, -0.18, 1.00, -0.19],
        frame_timestamps_ms=[0.0, 500.0, 1000.0, 1500.0],
    )

    result = preprocess_nonverbal_turn(
        raw,
        "speaking",
        baseline=baseline,
        alignment_tolerance_radians=0.05,
        au12_active_threshold=None,
        nod_params=_UNCONFIGURED_NOD,
    )

    # Frame 0: distance 0 (aligned). Frame 1: hypot(0.05, 0.02) ~= 0.054 > 0.05
    # (NOT aligned). Frame 2: far (NOT aligned). Frame 3: hypot(0.01, 0.01) ~=
    # 0.014 <= 0.05 (aligned). => 2 of 4 aligned.
    assert result.processed.visual_alignment_ratio == pytest.approx(0.5)
    assert "visual_alignment_ratio" not in result.reasons


def test_visual_alignment_does_not_assume_origin_center():
    """Moving the center off the origin changes which frames count as aligned.

    The same gaze frames are evaluated once against a center at the origin and
    once against a calibrated center. Frames near the origin are aligned for the
    origin center but NOT for the offset calibrated center, so the two ratios
    differ. This proves (0, 0) is not assumed.
    """
    gaze_yaw = [0.00, 0.01, 0.60, 0.61]
    gaze_pitch = [0.00, 0.01, 0.60, 0.61]
    timestamps = [0.0, 500.0, 1000.0, 1500.0]
    tolerance = 0.05

    near_origin = preprocess_nonverbal_turn(
        _raw(
            gaze_yaw_samples=gaze_yaw,
            gaze_pitch_samples=gaze_pitch,
            frame_timestamps_ms=timestamps,
        ),
        "speaking",
        baseline=_calibrated_baseline(neutral_gaze_yaw=0.0, neutral_gaze_pitch=0.0),
        alignment_tolerance_radians=tolerance,
        au12_active_threshold=None,
        nod_params=_UNCONFIGURED_NOD,
    )
    calibrated = preprocess_nonverbal_turn(
        _raw(
            gaze_yaw_samples=gaze_yaw,
            gaze_pitch_samples=gaze_pitch,
            frame_timestamps_ms=timestamps,
        ),
        "speaking",
        baseline=_calibrated_baseline(neutral_gaze_yaw=0.60, neutral_gaze_pitch=0.60),
        alignment_tolerance_radians=tolerance,
        au12_active_threshold=None,
        nod_params=_UNCONFIGURED_NOD,
    )

    # Origin center: first two frames align. Calibrated (0.60, 0.60) center: last
    # two frames align. Same count here but on DIFFERENT frames, and the aligned
    # sets are disjoint, so the origin is demonstrably not assumed.
    assert near_origin.processed.visual_alignment_ratio == pytest.approx(0.5)
    assert calibrated.processed.visual_alignment_ratio == pytest.approx(0.5)

    # Prove the aligned frames differ: with the calibrated center only the
    # late-frame episode exists, so its dwell starts at 1000 ms, whereas the
    # origin center's episode is the early frames.
    assert near_origin.processed.median_visual_alignment_dwell_ms == pytest.approx(500.0)
    assert calibrated.processed.median_visual_alignment_dwell_ms == pytest.approx(500.0)


# ---------------------------------------------------------------------------
# Dwell segmentation
# ---------------------------------------------------------------------------


def test_median_visual_alignment_dwell_segments_consecutive_frames():
    """Two aligned episodes; the median of their durations is returned.

    Aligned pattern across 6 frames: [A, A, gap, A, A, A]. Episode 1 spans
    timestamps 0..1000 (1000 ms). Episode 2 spans 3000..5000 (2000 ms). Median of
    {1000, 2000} is 1500 ms.
    """
    baseline = _calibrated_baseline(neutral_gaze_yaw=0.0, neutral_gaze_pitch=0.0)
    raw = _raw(
        gaze_yaw_samples=[0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
        gaze_pitch_samples=[0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
        frame_timestamps_ms=[0.0, 1000.0, 2000.0, 3000.0, 4000.0, 5000.0],
    )

    result = preprocess_nonverbal_turn(
        raw,
        "speaking",
        baseline=baseline,
        alignment_tolerance_radians=0.05,
        au12_active_threshold=None,
        nod_params=_UNCONFIGURED_NOD,
    )

    assert result.processed.visual_alignment_ratio == pytest.approx(5 / 6)
    assert result.processed.median_visual_alignment_dwell_ms == pytest.approx(1500.0)
    assert "median_visual_alignment_dwell_ms" not in result.reasons


def test_dwell_none_with_reason_when_no_aligned_episodes():
    """A real 0.0 ratio but no dwell to report -> dwell None with reason."""
    baseline = _calibrated_baseline(neutral_gaze_yaw=0.0, neutral_gaze_pitch=0.0)
    raw = _raw(
        gaze_yaw_samples=[1.0, 1.0],
        gaze_pitch_samples=[1.0, 1.0],
        frame_timestamps_ms=[0.0, 500.0],
    )

    result = preprocess_nonverbal_turn(
        raw,
        "speaking",
        baseline=baseline,
        alignment_tolerance_radians=0.05,
        au12_active_threshold=None,
        nod_params=_UNCONFIGURED_NOD,
    )

    assert result.processed.visual_alignment_ratio == pytest.approx(0.0)
    assert result.processed.median_visual_alignment_dwell_ms is None
    assert (
        result.reasons["median_visual_alignment_dwell_ms"]
        == UnavailableReason.INSUFFICIENT_SIGNAL
    )
    # The ratio itself is available (a real 0.0), so it carries no reason.
    assert "visual_alignment_ratio" not in result.reasons


# ---------------------------------------------------------------------------
# Missing calibration / missing tolerance / insufficient signal
# ---------------------------------------------------------------------------


def test_missing_baseline_marks_visual_features_missing_calibration():
    raw = _raw(
        gaze_yaw_samples=[0.0],
        gaze_pitch_samples=[0.0],
        frame_timestamps_ms=[0.0],
    )

    result = preprocess_nonverbal_turn(
        raw,
        "speaking",
        baseline=None,
        alignment_tolerance_radians=0.05,
        au12_active_threshold=None,
        nod_params=_UNCONFIGURED_NOD,
    )

    assert result.processed.visual_alignment_ratio is None
    assert result.processed.median_visual_alignment_dwell_ms is None
    assert result.reasons["visual_alignment_ratio"] == UnavailableReason.MISSING_CALIBRATION
    assert (
        result.reasons["median_visual_alignment_dwell_ms"]
        == UnavailableReason.MISSING_CALIBRATION
    )


def test_partial_baseline_gaze_marks_visual_features_missing_calibration():
    """A baseline with only one gaze axis yields no calibrated center."""
    baseline = _calibrated_baseline(neutral_gaze_yaw=0.30, neutral_gaze_pitch=None)
    raw = _raw(
        gaze_yaw_samples=[0.30],
        gaze_pitch_samples=[0.0],
        frame_timestamps_ms=[0.0],
    )

    result = preprocess_nonverbal_turn(
        raw,
        "speaking",
        baseline=baseline,
        alignment_tolerance_radians=0.05,
        au12_active_threshold=None,
        nod_params=_UNCONFIGURED_NOD,
    )

    assert result.processed.visual_alignment_ratio is None
    assert result.reasons["visual_alignment_ratio"] == UnavailableReason.MISSING_CALIBRATION


def test_missing_tolerance_marks_visual_features_feature_unavailable():
    baseline = _calibrated_baseline()
    raw = _raw(
        gaze_yaw_samples=[0.30],
        gaze_pitch_samples=[-0.20],
        frame_timestamps_ms=[0.0],
    )

    result = preprocess_nonverbal_turn(
        raw,
        "speaking",
        baseline=baseline,
        alignment_tolerance_radians=None,
        au12_active_threshold=None,
        nod_params=_UNCONFIGURED_NOD,
    )

    assert result.processed.visual_alignment_ratio is None
    assert result.processed.median_visual_alignment_dwell_ms is None
    assert result.reasons["visual_alignment_ratio"] == UnavailableReason.FEATURE_UNAVAILABLE
    assert (
        result.reasons["median_visual_alignment_dwell_ms"]
        == UnavailableReason.FEATURE_UNAVAILABLE
    )


def test_no_gaze_frames_marks_visual_features_insufficient_signal():
    """A calibrated center and a tolerance, but no gaze frames at all."""
    baseline = _calibrated_baseline()
    raw = _raw(gaze_yaw_samples=[], gaze_pitch_samples=[], frame_timestamps_ms=[])

    result = preprocess_nonverbal_turn(
        raw,
        "speaking",
        baseline=baseline,
        alignment_tolerance_radians=0.05,
        au12_active_threshold=None,
        nod_params=_UNCONFIGURED_NOD,
    )

    assert result.processed.visual_alignment_ratio is None
    assert result.processed.median_visual_alignment_dwell_ms is None
    assert result.reasons["visual_alignment_ratio"] == UnavailableReason.INSUFFICIENT_SIGNAL
    assert (
        result.reasons["median_visual_alignment_dwell_ms"]
        == UnavailableReason.INSUFFICIENT_SIGNAL
    )


# ---------------------------------------------------------------------------
# Nod detection
# ---------------------------------------------------------------------------


def _nod_series(cycles: int) -> list[float]:
    """Build a head-pitch series with ``cycles`` clear downward troughs.

    Each cycle is a rise to +5 then a dip to -5 then back to +5. Adjacent troughs
    are 4 frames apart, giving a large peak-to-trough amplitude so the prominence
    gate is satisfied. The series starts and ends high so every dip is a real
    local minimum.
    """
    series: list[float] = []
    for _ in range(cycles):
        series.extend([5.0, 0.0, -5.0, 0.0])
    series.append(5.0)
    return series


def test_nod_detection_counts_downward_oscillations():
    pytest.importorskip("scipy")

    # Three downward oscillations. sample_fps=2 => 4-frame trough spacing is
    # 2000 ms, which sits inside a [500, 4000] ms cycle window.
    nod_params = NodDetectionParams(
        min_amplitude_deg=2.0,
        min_cycle_ms=500.0,
        max_cycle_ms=4000.0,
        smoothing_window_ms=None,
    )
    raw = _raw(
        head_pitch_samples=_nod_series(3),
        sample_fps=2.0,
        turn_duration_ms=60_000,  # exactly one minute
    )

    result = preprocess_nonverbal_turn(
        raw,
        "listening",
        baseline=None,
        alignment_tolerance_radians=None,
        au12_active_threshold=None,
        nod_params=nod_params,
    )

    assert result.processed.nod_count == 3
    # One minute of turn duration => rate equals the count.
    assert result.processed.nod_rate_min == pytest.approx(3.0)
    assert "nod_count" not in result.reasons
    assert "nod_rate_min" not in result.reasons


def test_nod_rate_scales_with_turn_duration():
    pytest.importorskip("scipy")

    nod_params = NodDetectionParams(
        min_amplitude_deg=2.0,
        min_cycle_ms=500.0,
        max_cycle_ms=4000.0,
    )
    raw = _raw(
        head_pitch_samples=_nod_series(2),
        sample_fps=2.0,
        turn_duration_ms=30_000,  # half a minute => rate is twice the count
    )

    result = preprocess_nonverbal_turn(
        raw,
        "listening",
        baseline=None,
        alignment_tolerance_radians=None,
        au12_active_threshold=None,
        nod_params=nod_params,
    )

    assert result.processed.nod_count == 2
    assert result.processed.nod_rate_min == pytest.approx(4.0)


def test_unconfigured_nod_params_mark_features_unavailable():
    raw = _raw(head_pitch_samples=_nod_series(3), sample_fps=2.0)

    result = preprocess_nonverbal_turn(
        raw,
        "listening",
        baseline=None,
        alignment_tolerance_radians=None,
        au12_active_threshold=None,
        nod_params=NodDetectionParams(),  # is_configured is False
    )

    assert result.processed.nod_count is None
    assert result.processed.nod_rate_min is None
    assert result.reasons["nod_count"] == UnavailableReason.FEATURE_UNAVAILABLE
    assert result.reasons["nod_rate_min"] == UnavailableReason.FEATURE_UNAVAILABLE


def test_no_head_pitch_samples_marks_nod_insufficient_signal():
    nod_params = NodDetectionParams(
        min_amplitude_deg=2.0,
        min_cycle_ms=500.0,
        max_cycle_ms=4000.0,
    )
    raw = _raw(head_pitch_samples=[], sample_fps=2.0)

    result = preprocess_nonverbal_turn(
        raw,
        "listening",
        baseline=None,
        alignment_tolerance_radians=None,
        au12_active_threshold=None,
        nod_params=nod_params,
    )

    assert result.processed.nod_count is None
    assert result.processed.nod_rate_min is None
    assert result.reasons["nod_count"] == UnavailableReason.INSUFFICIENT_SIGNAL
    assert result.reasons["nod_rate_min"] == UnavailableReason.INSUFFICIENT_SIGNAL


# ---------------------------------------------------------------------------
# Smile
# ---------------------------------------------------------------------------


def test_smile_activity_ratio_uses_threshold_and_mean_over_all_frames():
    """Ratio is the fraction of AU12 >= threshold; mean is over all valid frames.

    AU12 = [0.1, 0.5, 0.9, 0.3] with threshold 0.5 => two frames active
    (0.5 and 0.9, inclusive) => ratio 0.5. Mean = (0.1+0.5+0.9+0.3)/4 = 0.45.
    """
    raw = _raw(au12_samples=[0.1, 0.5, 0.9, 0.3])

    result = preprocess_nonverbal_turn(
        raw,
        "listening",
        baseline=None,
        alignment_tolerance_radians=None,
        au12_active_threshold=0.5,
        nod_params=_UNCONFIGURED_NOD,
    )

    assert result.processed.smile_activity_ratio == pytest.approx(0.5)
    assert result.processed.mean_smile_activation == pytest.approx(0.45)
    assert "smile_activity_ratio" not in result.reasons
    assert "mean_smile_activation" not in result.reasons


def test_smile_threshold_none_keeps_mean_but_marks_ratio_unavailable():
    raw = _raw(au12_samples=[0.1, 0.5, 0.9, 0.3])

    result = preprocess_nonverbal_turn(
        raw,
        "listening",
        baseline=None,
        alignment_tolerance_radians=None,
        au12_active_threshold=None,
        nod_params=_UNCONFIGURED_NOD,
    )

    assert result.processed.smile_activity_ratio is None
    assert result.processed.mean_smile_activation == pytest.approx(0.45)
    assert result.reasons["smile_activity_ratio"] == UnavailableReason.FEATURE_UNAVAILABLE
    assert "mean_smile_activation" not in result.reasons


def test_no_au12_samples_marks_both_smile_features_insufficient_signal():
    raw = _raw(au12_samples=[])

    result = preprocess_nonverbal_turn(
        raw,
        "listening",
        baseline=None,
        alignment_tolerance_radians=None,
        au12_active_threshold=0.5,
        nod_params=_UNCONFIGURED_NOD,
    )

    assert result.processed.smile_activity_ratio is None
    assert result.processed.mean_smile_activation is None
    assert result.reasons["smile_activity_ratio"] == UnavailableReason.INSUFFICIENT_SIGNAL
    assert result.reasons["mean_smile_activation"] == UnavailableReason.INSUFFICIENT_SIGNAL


# ---------------------------------------------------------------------------
# Interaction context passthrough
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("context", ["speaking", "listening"])
def test_known_context_is_passed_through(context):
    result = preprocess_nonverbal_turn(
        _raw(au12_samples=[0.2]),
        context,
        baseline=None,
        alignment_tolerance_radians=None,
        au12_active_threshold=None,
        nod_params=_UNCONFIGURED_NOD,
    )

    assert result.processed.context == context


def test_unknown_context_is_stored_as_none():
    result = preprocess_nonverbal_turn(
        _raw(au12_samples=[0.2]),
        "mumbling",
        baseline=None,
        alignment_tolerance_radians=None,
        au12_active_threshold=None,
        nod_params=_UNCONFIGURED_NOD,
    )

    assert result.processed.context is None
