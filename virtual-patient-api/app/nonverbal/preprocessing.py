"""Derive turn features from semantic gaze, CCDb-HG events and smile samples.

Unavailable observations remain None with an explicit per-feature reason.
The baseline argument remains accepted for caller compatibility;
semantic gaze observations determine alignment, without an angular fallback.
Thresholding and label integration belong to the shared multimodal result policy.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from app.multimodal.schemas import (
    NonverbalProcessedFeatures,
    NonverbalRawFeatures,
    PersonalBaseline,
    UnavailableReason,
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


def time_weighted_states(samples, *, end_ms, max_support_ms=100):
    totals = {'INSIDE': 0., 'OUTSIDE': 0.}
    durations = []
    episode = 0.
    for index, item in enumerate(samples):
        time = float(item['timestamp_ms'])
        next_time = float(samples[index + 1]['timestamp_ms']) if index + 1 < len(samples) else end_ms
        gap = next_time - time
        support = max(0., min(gap, max_support_ms, end_ms - time))
        state = item.get('state')
        if state in totals:
            totals[state] += support
        if state == 'INSIDE':
            episode += support
        if state != 'INSIDE' or gap > 200 or gap <= 0 or index == len(samples) - 1:
            if episode:
                durations.append(episode)
            episode = 0.
    return totals, durations


def preprocess_nonverbal_turn(
    raw: NonverbalRawFeatures,
    context: str,
    *,
    baseline: PersonalBaseline | None,
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
        Accepted for compatibility; semantic gaze is already calibrated upstream.
    """
    reasons: dict[str, UnavailableReason] = {}

    semantic = [item for item in raw.gaze_semantic_observations if item.get("state") != "UNAVAILABLE"]
    interaction_totals = None
    interaction_dwell = None
    if any(item.get('state') in {'INSIDE', 'OUTSIDE'} for item in semantic):
        end_ms = raw.extractor.get('window_end_ms', raw.gaze_semantic_observations[-1]['timestamp_ms'])
        interaction_totals, episodes = time_weighted_states(raw.gaze_semantic_observations, end_ms=end_ms,
            max_support_ms=min(200., 1000. / raw.sample_fps))
        interaction_dwell = statistics.median(episodes) if episodes else None
    if semantic and interaction_totals is None:
        aligned = [item.get("state") in ("PATIENT", "CAMERA") for item in semantic]
        alignment_ratio = sum(aligned) / len(aligned)
        dwell_ms = _median_aligned_dwell_ms(
            timestamps=[float(item["timestamp_ms"]) for item in raw.gaze_semantic_observations],
            aligned_flags=[item.get("state") in ("PATIENT", "CAMERA") for item in raw.gaze_semantic_observations],
        )
        if dwell_ms is None:
            reasons["median_visual_alignment_dwell_ms"] = UnavailableReason.INSUFFICIENT_SIGNAL
    elif not semantic:
        alignment_ratio, dwell_ms = None, None
        reason = UnavailableReason.GAZE_CALIBRATION_PENDING if not raw.gaze_semantic_observations else UnavailableReason.INSUFFICIENT_SIGNAL
        if (raw.gaze_semantic_observations and raw.gaze_observations and
                sum(item.get("state") == "outside_calibrated_geometry" for item in raw.gaze_observations)
                > len(raw.gaze_observations) / 2):
            reason = UnavailableReason.OUTSIDE_CALIBRATED_GEOMETRY
        reasons["visual_alignment_ratio"] = reason
        reasons["median_visual_alignment_dwell_ms"] = reason
    else:
        alignment_ratio, dwell_ms = None, None

    nod_count, nod_rate_min = raw.nod_count, raw.nod_rate_min
    if nod_count is None:
        reason = raw.nod_unavailable_reason or UnavailableReason.INSUFFICIENT_SIGNAL
        reasons["nod_count"] = reason
        reasons["nod_rate_min"] = reason
    elif nod_rate_min is None:
        reasons["nod_rate_min"] = raw.nod_unavailable_reason or UnavailableReason.INSUFFICIENT_SIGNAL

    smile_activity_ratio, mean_smile_activation = _smile(
        raw=raw,
        reasons=reasons,
    )
    if raw.smile_observations:
        end_ms = raw.extractor.get('window_end_ms', raw.smile_observations[-1]['timestamp_ms'])
        smile_states = [{'timestamp_ms': item['timestamp_ms'], 'state': ('INSIDE' if item.get('smile_detected') else 'OUTSIDE') if item.get('smile_detected') is not None else 'UNAVAILABLE'} for item in raw.smile_observations]
        smile_totals, _ = time_weighted_states(smile_states, end_ms=end_ms, max_support_ms=min(200., 1000. / raw.sample_fps))
        smile_activity_ratio = smile_totals['INSIDE'] / sum(smile_totals.values()) if sum(smile_totals.values()) else None

    processed = NonverbalProcessedFeatures(
        visual_alignment_ratio=alignment_ratio,
        median_visual_alignment_dwell_ms=dwell_ms,
        interaction_gaze_duration_ms=interaction_totals['INSIDE'] if interaction_totals else None,
        outside_gaze_duration_ms=interaction_totals['OUTSIDE'] if interaction_totals else None,
        interaction_gaze_ratio=(interaction_totals['INSIDE'] / sum(interaction_totals.values())) if interaction_totals and sum(interaction_totals.values()) else None,
        median_interaction_dwell_ms=interaction_dwell,
        nod_count=nod_count,
        nod_rate_min=nod_rate_min,
        context=context if context in ("speaking", "listening") else None,
        smile_activity_ratio=smile_activity_ratio,
        mean_smile_activation=mean_smile_activation,
    )
    return NonverbalPreprocessingResult(processed=processed, reasons=reasons)


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
        # The shared extractor samples at 10 Hz. Missing observations break
        # continuity; a gap must never count as observed alignment dwell.
        if prev_ts is not None and (ts <= prev_ts or ts - prev_ts > 200):
            if run_start_ts is not None:
                episodes.append(prev_ts - run_start_ts)
            run_start_ts = None
            prev_ts = None
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


def _smile(
    *,
    raw: NonverbalRawFeatures,
    reasons: dict[str, UnavailableReason],
) -> tuple[float | None, float | None]:
    """Aggregate the MediaPipe smile activation and explicit detection flags."""
    samples = raw.smile_activation_samples

    if not samples:
        reasons["smile_activity_ratio"] = UnavailableReason.INSUFFICIENT_SIGNAL
        reasons["mean_smile_activation"] = UnavailableReason.INSUFFICIENT_SIGNAL
        return None, None

    mean_smile_activation = sum(samples) / len(samples)

    if raw.smile_detected_samples:
        smile_activity_ratio = sum(raw.smile_detected_samples) / len(raw.smile_detected_samples)
    else:
        reasons["smile_activity_ratio"] = UnavailableReason.FEATURE_UNAVAILABLE
        smile_activity_ratio = None
    return smile_activity_ratio, mean_smile_activation
