"""Nonverbal derivation for interview turns (Requirement 9).

This module is the preprocessing/derivation stage for the nonverbal modality.
It consumes the raw per-frame series produced by the Py-Feat extractor
(:class:`app.multimodal.schemas.NonverbalRawFeatures`), an optional
:class:`app.multimodal.schemas.PersonalBaseline`, the methodology parameters read
elsewhere from ``processing.yaml`` (passed in here as plain values -- this module
never reads YAML), and the interaction context of the turn. It produces derived
:class:`app.multimodal.schemas.NonverbalProcessedFeatures`. It applies no
methodology thresholding and assigns no label; that is the threshold engine's and
label engine's job.

The derived values are descriptive-only. Gaze alignment and head nods are
behavioural and contextual observations, not measures of attention, engagement,
warmth, or any psychological state.

Availability contract
----------------------
Any feature that lacks a required input is returned as ``None`` and never
fabricated. The specific gaps are:

* ``visual_alignment_ratio`` / ``median_visual_alignment_dwell_ms`` require both a
  calibrated interaction center (baseline ``neutral_gaze_yaw`` and
  ``neutral_gaze_pitch``) and a configured ``alignment_tolerance_radians``. The
  interaction center is NEVER assumed to be ``(0, 0)``. If the center is missing
  the reason is ``missing_calibration``; if only the tolerance is missing the
  reason is ``feature_unavailable``. When there are no valid gaze frames the
  reason is ``insufficient_signal``.
* ``nod_count`` / ``nod_rate_min`` require the nod detector parameters
  (``min_amplitude_deg``, ``min_cycle_ms``, ``max_cycle_ms``); the provisional
  parameters are ``null`` today, so these features are ``feature_unavailable``
  until the parameters are set. With no head-pitch samples the reason is
  ``insufficient_signal``.
* ``smile_activity_ratio`` requires ``au12_active_threshold``; when it is ``null``
  the feature is ``feature_unavailable``.
* ``mean_smile_activation`` requires at least one valid AU12 sample.

Because the caller (the pipeline) is responsible for recording the reason on the
modality layer, this function reports each gap via the returned
:class:`NonverbalPreprocessingResult`, which pairs the processed features with a
per-feature reason map. The processed features themselves only ever hold real
derived numbers or ``None``.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from app.multimodal.schemas import (
    NonverbalProcessedFeatures,
    NonverbalRawFeatures,
    PersonalBaseline,
    UnavailableReason,
)


@dataclass(frozen=True)
class NodDetectionParams:
    """Deterministic nod-detector parameters read from ``processing.yaml``.

    All fields are ``None`` when the corresponding methodology value is undecided
    (``null`` in ``processing.yaml``). ``smoothing_window_ms`` is optional even
    once the detector is enabled; the three timing/amplitude fields are required
    for the detector to run.
    """

    min_amplitude_deg: float | None = None
    min_cycle_ms: float | None = None
    max_cycle_ms: float | None = None
    smoothing_window_ms: float | None = None

    @property
    def is_configured(self) -> bool:
        """True only when every required detector parameter is present."""
        return (
            self.min_amplitude_deg is not None
            and self.min_cycle_ms is not None
            and self.max_cycle_ms is not None
        )


@dataclass(frozen=True)
class NonverbalPreprocessingResult:
    """Derived nonverbal features plus a per-feature unavailability reason map.

    ``processed`` carries only real numbers or ``None`` (never a fabricated
    value). ``reasons`` maps a feature name to the reason it is unavailable, so
    the pipeline can attach an explanation to every null it persists
    (Requirement 24.3). A feature that was derived successfully has no entry in
    ``reasons``.
    """

    processed: NonverbalProcessedFeatures
    reasons: dict[str, UnavailableReason] = field(default_factory=dict)


def preprocess_nonverbal_turn(
    raw: NonverbalRawFeatures,
    context: str,
    *,
    baseline: PersonalBaseline | None,
    alignment_tolerance_radians: float | None,
    au12_active_threshold: float | None,
    nod_params: NodDetectionParams,
) -> NonverbalPreprocessingResult:
    """Derive :class:`NonverbalProcessedFeatures` for a single turn window.

    Parameters
    ----------
    raw:
        Raw per-frame series and quality emitted by the Py-Feat extractor.
    context:
        Interaction context for the turn: ``"speaking"`` for a student-speaking
        turn or ``"listening"`` for a patient turn (Requirement 9.5). Any other
        value is treated as unknown and stored as ``None``.
    baseline:
        Optional personal baseline. Its ``neutral_gaze_yaw`` / ``neutral_gaze_pitch``
        define the calibrated interaction center for visual alignment. The center
        is never assumed to be ``(0, 0)`` (Requirement 9.1).
    alignment_tolerance_radians:
        Angular tolerance for counting a frame as aligned. ``None`` means the
        methodology value is undecided and visual alignment is
        ``feature_unavailable`` (Requirement 4.7, 9.6).
    au12_active_threshold:
        AU12 activation level at or above which AU12 is considered active. ``None``
        means ``smile_activity_ratio`` is ``feature_unavailable`` (Requirement
        10.4, 9.6). This governs AU12 activity only and is intentionally distinct
        from the derived ``smile_activity_ratio`` feature.
    nod_params:
        Deterministic nod-detector parameters. When not fully configured,
        ``nod_count`` / ``nod_rate_min`` are ``feature_unavailable`` (Requirement
        9.3, 9.6). ``sample_fps`` on ``raw`` drives detector timing.
    """
    reasons: dict[str, UnavailableReason] = {}

    alignment_ratio, dwell_ms = _visual_alignment(
        raw=raw,
        baseline=baseline,
        alignment_tolerance_radians=alignment_tolerance_radians,
        reasons=reasons,
    )

    nod_count, nod_rate_min = _nod_detection(
        raw=raw,
        nod_params=nod_params,
        reasons=reasons,
    )

    smile_activity_ratio, mean_smile_activation = _smile(
        raw=raw,
        au12_active_threshold=au12_active_threshold,
        reasons=reasons,
    )

    processed = NonverbalProcessedFeatures(
        visual_alignment_ratio=alignment_ratio,
        median_visual_alignment_dwell_ms=dwell_ms,
        nod_count=nod_count,
        nod_rate_min=nod_rate_min,
        context=context if context in ("speaking", "listening") else None,
        smile_activity_ratio=smile_activity_ratio,
        mean_smile_activation=mean_smile_activation,
    )
    return NonverbalPreprocessingResult(processed=processed, reasons=reasons)


def _visual_alignment(
    *,
    raw: NonverbalRawFeatures,
    baseline: PersonalBaseline | None,
    alignment_tolerance_radians: float | None,
    reasons: dict[str, UnavailableReason],
) -> tuple[float | None, float | None]:
    """Compute ``visual_alignment_ratio`` and ``median_visual_alignment_dwell_ms``.

    Angular-distance definition: for each frame the deviation from the calibrated
    interaction center is the Euclidean distance in the (yaw, pitch) radian plane,
    ``hypot(gaze_yaw - center_yaw, gaze_pitch - center_pitch)``. This is the
    small-angle approximation of the angular distance between the observed gaze
    direction and the calibrated center, computed relative to that center and
    never relative to a fixed ``(0, 0)`` origin (Requirement 9.1). A frame is
    aligned when this deviation is at or below ``alignment_tolerance_radians``.

    ``visual_alignment_ratio`` is the fraction of valid (paired yaw/pitch) frames
    that are aligned. ``median_visual_alignment_dwell_ms`` segments runs of
    consecutive aligned frames into episodes, measures each episode's duration
    from its first to its last frame timestamp, and returns the median episode
    duration; with no aligned episodes it is ``None``.

    Returns ``(None, None)`` with a recorded reason when the calibrated center or
    the tolerance is unavailable, or when there are no valid gaze frames.
    """
    center = _calibrated_center(baseline)
    if center is None:
        # Missing calibrated center: never fall back to a (0, 0) assumption.
        reasons["visual_alignment_ratio"] = UnavailableReason.MISSING_CALIBRATION
        reasons["median_visual_alignment_dwell_ms"] = UnavailableReason.MISSING_CALIBRATION
        return None, None

    if alignment_tolerance_radians is None:
        reasons["visual_alignment_ratio"] = UnavailableReason.FEATURE_UNAVAILABLE
        reasons["median_visual_alignment_dwell_ms"] = UnavailableReason.FEATURE_UNAVAILABLE
        return None, None

    center_yaw, center_pitch = center
    # Pair yaw/pitch with their frame timestamps. Frames missing either angle or a
    # timestamp are not valid gaze frames and are excluded from the denominator.
    frames = [
        (yaw, pitch, ts)
        for yaw, pitch, ts in zip(
            raw.gaze_yaw_samples, raw.gaze_pitch_samples, raw.frame_timestamps_ms
        )
    ]
    if not frames:
        reasons["visual_alignment_ratio"] = UnavailableReason.INSUFFICIENT_SIGNAL
        reasons["median_visual_alignment_dwell_ms"] = UnavailableReason.INSUFFICIENT_SIGNAL
        return None, None

    aligned_flags = [
        math.hypot(yaw - center_yaw, pitch - center_pitch) <= alignment_tolerance_radians
        for yaw, pitch, _ in frames
    ]
    alignment_ratio = sum(aligned_flags) / len(aligned_flags)

    dwell_ms = _median_aligned_dwell_ms(
        timestamps=[ts for _, _, ts in frames],
        aligned_flags=aligned_flags,
    )
    if dwell_ms is None:
        # No aligned episodes: the ratio is a real 0.0 but there is no dwell to
        # report. This is an available-but-empty outcome, not a fabricated value.
        reasons["median_visual_alignment_dwell_ms"] = UnavailableReason.INSUFFICIENT_SIGNAL

    return alignment_ratio, dwell_ms


def _calibrated_center(
    baseline: PersonalBaseline | None,
) -> tuple[float, float] | None:
    """Return the calibrated ``(yaw, pitch)`` interaction center, or ``None``.

    The center is the required neutral gaze stored in a valid personal baseline.
    """
    if baseline is None:
        return None
    return baseline.neutral_gaze_yaw, baseline.neutral_gaze_pitch


def _median_aligned_dwell_ms(
    *,
    timestamps: list[float],
    aligned_flags: list[bool],
) -> float | None:
    """Median duration (ms) of runs of consecutive aligned frames.

    Each maximal run of aligned frames is one episode; its duration is the span
    from its first to its last frame timestamp. Returns ``None`` when there is no
    aligned episode. A single-frame episode has a duration of ``0.0`` ms because
    it spans no time between frames.
    """
    episodes: list[float] = []
    run_start_ts: float | None = None
    prev_ts: float | None = None

    for ts, aligned in zip(timestamps, aligned_flags):
        if aligned:
            if run_start_ts is None:
                run_start_ts = ts
            prev_ts = ts
        else:
            if run_start_ts is not None and prev_ts is not None:
                episodes.append(prev_ts - run_start_ts)
            run_start_ts = None
            prev_ts = None

    if run_start_ts is not None and prev_ts is not None:
        episodes.append(prev_ts - run_start_ts)

    if not episodes:
        return None
    return float(statistics.median(episodes))


def _nod_detection(
    *,
    raw: NonverbalRawFeatures,
    nod_params: NodDetectionParams,
    reasons: dict[str, UnavailableReason],
) -> tuple[int | None, float | None]:
    """Deterministic, configurable nod detection over the head-pitch series.

    A nod is a downward-then-upward head-pitch oscillation. The detector, once
    its parameters are configured, works as follows and is fully deterministic:

    1. Optionally smooth the head-pitch series with a moving average whose window
       is ``smoothing_window_ms`` converted to frames via ``sample_fps``.
    2. Find local minima (troughs) with :func:`scipy.signal.find_peaks` applied to
       the negated series, requiring a peak-to-trough prominence of at least
       ``min_amplitude_deg``.
    3. Keep only troughs whose spacing to the previous kept trough lies within
       ``[min_cycle_ms, max_cycle_ms]`` (converted to frames via ``sample_fps``),
       so timing is driven by the configured sampling rate.

    ``nod_rate_min`` is nods per minute over the turn duration:
    ``nod_count / (turn_duration_ms / 60000)``.

    Gating: because the provisional detector parameters are ``null`` today, the
    detector does not run and both features are ``feature_unavailable`` until the
    parameters are set. With no head-pitch samples the reason is
    ``insufficient_signal``. When the turn has zero duration ``nod_rate_min`` is
    ``None`` (cannot divide by zero) while ``nod_count`` may still be reported.
    """
    if not nod_params.is_configured:
        reasons["nod_count"] = UnavailableReason.FEATURE_UNAVAILABLE
        reasons["nod_rate_min"] = UnavailableReason.FEATURE_UNAVAILABLE
        return None, None

    series = raw.head_pitch_samples
    if not series:
        reasons["nod_count"] = UnavailableReason.INSUFFICIENT_SIGNAL
        reasons["nod_rate_min"] = UnavailableReason.INSUFFICIENT_SIGNAL
        return None, None

    nod_count = _count_nods(
        series=series,
        sample_fps=raw.sample_fps,
        min_amplitude_deg=nod_params.min_amplitude_deg,  # type: ignore[arg-type]
        min_cycle_ms=nod_params.min_cycle_ms,  # type: ignore[arg-type]
        max_cycle_ms=nod_params.max_cycle_ms,  # type: ignore[arg-type]
        smoothing_window_ms=nod_params.smoothing_window_ms,
    )

    if raw.turn_duration_ms <= 0:
        reasons["nod_rate_min"] = UnavailableReason.INSUFFICIENT_SIGNAL
        return nod_count, None

    nod_rate_min = nod_count / (raw.turn_duration_ms / 60000)
    return nod_count, nod_rate_min


def _count_nods(
    *,
    series: list[float],
    sample_fps: float,
    min_amplitude_deg: float,
    min_cycle_ms: float,
    max_cycle_ms: float,
    smoothing_window_ms: float | None,
) -> int:
    """Count nod cycles in a head-pitch series deterministically.

    Isolated from the availability logic so it is directly testable once
    parameters are configured. Uses :func:`scipy.signal.find_peaks`; the import is
    local so the rest of the module remains importable and testable even if the
    detector is never invoked (though scipy is a pinned dependency).
    """
    from scipy.signal import find_peaks

    if sample_fps <= 0:
        return 0

    working = _moving_average(series, _ms_to_frames(smoothing_window_ms, sample_fps))

    # Troughs of the head-pitch series are peaks of the negated series. The
    # prominence gate enforces a minimum peak-to-trough amplitude for a nod.
    negated = [-value for value in working]
    trough_indices, _ = find_peaks(negated, prominence=min_amplitude_deg)

    min_gap_frames = _ms_to_frames(min_cycle_ms, sample_fps)
    max_gap_frames = _ms_to_frames(max_cycle_ms, sample_fps)

    nod_count = 0
    last_kept: int | None = None
    for index in trough_indices:
        if last_kept is None:
            last_kept = int(index)
            nod_count += 1
            continue
        gap = int(index) - last_kept
        if min_gap_frames <= gap <= max_gap_frames:
            nod_count += 1
            last_kept = int(index)
    return nod_count


def _moving_average(series: list[float], window_frames: int) -> list[float]:
    """Centered moving average; a window of 0 or 1 returns the series unchanged."""
    if window_frames <= 1 or len(series) <= 1:
        return list(series)
    half = window_frames // 2
    smoothed: list[float] = []
    for i in range(len(series)):
        lo = max(0, i - half)
        hi = min(len(series), i + half + 1)
        window = series[lo:hi]
        smoothed.append(sum(window) / len(window))
    return smoothed


def _ms_to_frames(duration_ms: float | None, sample_fps: float) -> int:
    """Convert a millisecond duration to a whole number of frames.

    Timing is driven by ``sample_fps`` so the detector adapts to the benchmarked
    sampling rates (2, 5, 10, 15, 25 fps). Returns 0 when no duration is given.
    """
    if duration_ms is None or sample_fps <= 0:
        return 0
    return round(duration_ms * sample_fps / 1000)


def _smile(
    *,
    raw: NonverbalRawFeatures,
    au12_active_threshold: float | None,
    reasons: dict[str, UnavailableReason],
) -> tuple[float | None, float | None]:
    """Compute ``smile_activity_ratio`` and ``mean_smile_activation``.

    ``smile_activity_ratio`` is the fraction of valid frames whose AU12 activation
    is at or above ``au12_active_threshold``. When the threshold is ``null`` the
    ratio is ``feature_unavailable`` (Requirement 9.6, 10.4); it is distinct from
    ``mean_smile_activation``.

    ``mean_smile_activation`` is the mean AU12 activation over all valid frames
    (its denominator is the count of valid AU12 samples, preserving the prior
    extractor semantics), not only over frames considered smiling. It is
    available whenever there is at least one valid AU12 sample, independently of
    whether the threshold is defined.
    """
    au12_values = raw.au12_samples

    if not au12_values:
        reasons["smile_activity_ratio"] = UnavailableReason.INSUFFICIENT_SIGNAL
        reasons["mean_smile_activation"] = UnavailableReason.INSUFFICIENT_SIGNAL
        return None, None

    mean_smile_activation = sum(au12_values) / len(au12_values)

    if au12_active_threshold is None:
        reasons["smile_activity_ratio"] = UnavailableReason.FEATURE_UNAVAILABLE
        return None, mean_smile_activation

    active = [value for value in au12_values if value >= au12_active_threshold]
    smile_activity_ratio = len(active) / len(au12_values)
    return smile_activity_ratio, mean_smile_activation
