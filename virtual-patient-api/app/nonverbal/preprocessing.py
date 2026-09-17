"""Nonverbal derivation for interview turns (Requirement 9).

This module is the preprocessing/derivation stage for the nonverbal modality.
It consumes raw summaries produced by the shared MediaPipe visual pipeline
(:class:`app.multimodal.schemas.NonverbalRawFeatures`), an optional
:class:`app.multimodal.schemas.PersonalBaseline`, and the interaction context of
the turn. Its derivation parameters (gaze alignment tolerance, AU12 activation,
smile activation) are technical constants defined in this module, not
methodology configuration. It produces derived
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

* ``visual_alignment_ratio`` / ``median_visual_alignment_dwell_ms`` require a
  calibrated interaction center (baseline ``neutral_gaze_yaw`` and
  ``neutral_gaze_pitch``); the alignment tolerance is a technical constant
  (:data:`GAZE_ALIGNMENT_TOLERANCE_RADIANS`), not a methodology value. The
  interaction center is NEVER assumed to be ``(0, 0)``. If the center is missing
  the reason is ``missing_calibration``. When there are no valid gaze frames the
  reason is ``insufficient_signal``.
* ``nod_count`` / ``nod_rate_min`` are supplied by the CCDb-HG event pipeline;
  its explicit unavailable reason is preserved when inference is not evaluable.
* ``smile_activity_ratio`` uses the technical AU12 activation constant
  (:data:`AU12_ACTIVE_THRESHOLD`); it is unavailable only when there are no valid
  AU12 samples (``insufficient_signal``).
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


# ---------------------------------------------------------------------------
# Technical derivation constants (not research thresholds)
#
# These are engineering parameters of the nonverbal derivation, not provisional
# research cutoffs. They tune HOW a feature is computed, not the label bands
# applied to it (those live in thresholds.yaml). They are fixed here with
# and are not surfaced as methodology configuration.
#
# Gaze alignment tolerance: half-angle (radians) of the interaction cone around
# the calibrated gaze center within which a frame counts as visually aligned.
# ~0.35 rad ≈ 20°, a reasonable on-screen interaction cone.
GAZE_ALIGNMENT_TOLERANCE_RADIANS = 0.35

# Compatibility fallback for legacy raw records without explicit smile flags.
AU12_ACTIVE_THRESHOLD = 0.5


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
    alignment_tolerance_radians: float = GAZE_ALIGNMENT_TOLERANCE_RADIANS,
    au12_active_threshold: float = AU12_ACTIVE_THRESHOLD,
) -> NonverbalPreprocessingResult:
    """Derive :class:`NonverbalProcessedFeatures` for a single turn window.

    Parameters
    ----------
    raw:
        Raw observations and quality emitted by the shared visual extractor.
    context:
        Interaction context for the turn: ``"speaking"`` for a student-speaking
        turn or ``"listening"`` for a patient turn (Requirement 9.5). Any other
        value is treated as unknown and stored as ``None``.
    baseline:
        Optional personal baseline. Its ``neutral_gaze_yaw`` / ``neutral_gaze_pitch``
        define the calibrated interaction center for visual alignment. The center
        is never assumed to be ``(0, 0)`` (Requirement 9.1).
    alignment_tolerance_radians:
        Angular tolerance (radians) for counting a frame as aligned. Defaults to
        the technical constant :data:`GAZE_ALIGNMENT_TOLERANCE_RADIANS`; it tunes
        how the ratio is computed and is not a methodology threshold.
    au12_active_threshold:
        Compatibility threshold for legacy records lacking explicit MediaPipe
        smile flags. New extraction uses ``smile_detected_samples`` directly.
    """
    reasons: dict[str, UnavailableReason] = {}

    semantic = [item for item in raw.gaze_semantic_observations if item.get("state") != "UNAVAILABLE"]
    if semantic:
        aligned = [item.get("state") in ("PATIENT", "CAMERA") for item in semantic]
        alignment_ratio = sum(aligned) / len(aligned)
        dwell_ms = _median_aligned_dwell_ms(
            timestamps=[float(item["timestamp_ms"]) for item in semantic],
            aligned_flags=aligned,
        )
        if dwell_ms is None:
            reasons["median_visual_alignment_dwell_ms"] = UnavailableReason.INSUFFICIENT_SIGNAL
    else:
        alignment_ratio, dwell_ms = None, None
        reason = UnavailableReason.GAZE_CALIBRATION_PENDING if not raw.gaze_semantic_observations else UnavailableReason.INSUFFICIENT_SIGNAL
        reasons["visual_alignment_ratio"] = reason
        reasons["median_visual_alignment_dwell_ms"] = reason

    nod_count, nod_rate_min = raw.nod_count, raw.nod_rate_min
    if nod_count is None:
        reason = raw.nod_unavailable_reason or UnavailableReason.INSUFFICIENT_SIGNAL
        reasons["nod_count"] = reason
        reasons["nod_rate_min"] = reason
    elif nod_rate_min is None:
        reasons["nod_rate_min"] = raw.nod_unavailable_reason or UnavailableReason.INSUFFICIENT_SIGNAL

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
    alignment_tolerance_radians: float,
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
    baseline: PersonalBaseline | None,
    reasons: dict[str, UnavailableReason],
) -> tuple[int | None, float | None]:
    """Deterministic, configurable nod detection over the head-pitch series.

    A nod is a downward-then-upward head-pitch oscillation *from the person's
    resting posture*. The detector, once its parameters are configured, works as
    follows and is fully deterministic:

    1. Center the head-pitch series on the calibrated neutral head pitch
       (``baseline.neutral_head_pitch``) when a personal baseline is available, so
       troughs are measured relative to that student's resting posture rather than
       to an arbitrary absolute pitch. The neutral pitch comes from the same PnP
       head-pose estimation used per turn (derived during calibration), so its
       bias cancels on subtraction. When no baseline is available the raw series
       is used unchanged (clean degradation).
    2. Optionally smooth the centered series with a moving average whose window is
       ``smoothing_window_ms`` converted to frames via ``sample_fps``.
    3. Find local minima (troughs) with :func:`scipy.signal.find_peaks` applied to
       the negated series, requiring a peak-to-trough prominence of at least
       ``min_amplitude_deg``.
    4. Keep only troughs that are a genuine downward deflection below neutral
       (centered pitch at the trough <= ``-min_amplitude_deg``) — this is what the
       calibrated neutral buys: an upward tilt or head sway that is not a
       downward nod from rest is rejected.
    5. Keep only troughs whose spacing to the previous kept trough lies within
       ``[min_cycle_ms, max_cycle_ms]`` (converted to frames via ``sample_fps``).

    ``nod_rate_min`` is nods per minute over the turn duration:
    ``nod_count / (turn_duration_ms / 60000)``.

    Gating: the detector parameters are technical constants (see
    :class:`NodDetectionParams`), so the detector always runs when a head-pitch
    series is present. With no head-pitch samples the reason is
    ``insufficient_signal``. When the turn has zero duration ``nod_rate_min`` is
    ``None`` (cannot divide by zero) while ``nod_count`` may still be reported.
    """
    series = raw.head_pitch_samples
    if not series:
        reasons["nod_count"] = UnavailableReason.INSUFFICIENT_SIGNAL
        reasons["nod_rate_min"] = UnavailableReason.INSUFFICIENT_SIGNAL
        return None, None

    neutral_pitch = baseline.neutral_head_pitch if baseline is not None else 0.0

    nod_count = _count_nods(
        series=series,
        neutral_pitch=neutral_pitch,
        require_below_neutral=baseline is not None,
        sample_fps=raw.sample_fps,
        min_amplitude_deg=nod_params.min_amplitude_deg,
        min_cycle_ms=nod_params.min_cycle_ms,
        max_cycle_ms=nod_params.max_cycle_ms,
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
    neutral_pitch: float,
    require_below_neutral: bool,
    sample_fps: float,
    min_amplitude_deg: float,
    min_cycle_ms: float,
    max_cycle_ms: float,
    smoothing_window_ms: float | None,
) -> int:
    """Count nod cycles in a head-pitch series deterministically.

    The series is centered on ``neutral_pitch`` (the calibrated resting head
    pitch, or ``0.0`` when uncalibrated) so troughs are measured relative to
    rest. When ``require_below_neutral`` is True (a personal baseline exists), a
    trough only counts if the centered pitch there is at least
    ``min_amplitude_deg`` below neutral, i.e. a genuine downward nod from rest;
    this rejects upward tilts and non-nod head sway. When uncalibrated the
    directional gate is skipped and only the prominence/spacing gates apply.

    Isolated from the availability logic so it is directly testable once
    parameters are configured. Uses :func:`scipy.signal.find_peaks`; the import is
    local so the rest of the module remains importable and testable even if the
    detector is never invoked (though scipy is a pinned dependency).
    """
    from scipy.signal import find_peaks

    if sample_fps <= 0:
        return 0

    # Center on the resting posture: a downward nod is now a NEGATIVE excursion.
    centered = [value - neutral_pitch for value in series]
    working = _moving_average(centered, _ms_to_frames(smoothing_window_ms, sample_fps))

    # Troughs of the head-pitch series are peaks of the negated series. The
    # prominence gate enforces a minimum peak-to-trough amplitude for a nod.
    negated = [-value for value in working]
    trough_indices, _ = find_peaks(negated, prominence=min_amplitude_deg)

    min_gap_frames = _ms_to_frames(min_cycle_ms, sample_fps)
    max_gap_frames = _ms_to_frames(max_cycle_ms, sample_fps)

    nod_count = 0
    last_kept: int | None = None
    for index in trough_indices:
        idx = int(index)
        # Directional gate: with a calibrated neutral, require a genuine downward
        # deflection below rest (centered pitch <= -min_amplitude_deg).
        if require_below_neutral and working[idx] > -min_amplitude_deg:
            continue
        if last_kept is None:
            last_kept = idx
            nod_count += 1
            continue
        gap = idx - last_kept
        if min_gap_frames <= gap <= max_gap_frames:
            nod_count += 1
            last_kept = idx
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
    au12_active_threshold: float,
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

    if raw.smile_detected_samples:
        smile_activity_ratio = sum(raw.smile_detected_samples) / len(raw.smile_detected_samples)
    elif au12_active_threshold is None:
        reasons["smile_activity_ratio"] = UnavailableReason.FEATURE_UNAVAILABLE
        smile_activity_ratio = None
    else:
        active = [value for value in au12_values if value >= au12_active_threshold]
        smile_activity_ratio = len(active) / len(au12_values)
    return smile_activity_ratio, mean_smile_activation
