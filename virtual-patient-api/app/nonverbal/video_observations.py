"""Single-pass full-video nonverbal extraction and timestamp segmentation."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, dataclass, replace
from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Sequence

from app.media.patient_roi import parse_patient_roi_snapshots
from app.multimodal.schemas import NonverbalRawFeatures
from app.nonverbal.ccdbhg import NodAnalysis, NodEvent
from app.nonverbal.gaze import GazeObservation
from app.nonverbal.gaze_calibration import classify_interaction_gaze
from app.nonverbal.mediapipe_extractor import extract_video
from app.nonverbal.shared_observations import SharedFrameObservation
from app.nonverbal.smile import SmileObservation, extract_smile


@dataclass(frozen=True)
class TurnWindow:
    turn_id: str
    start_ms: float
    end_ms: float
    conversation_speaker: str


@dataclass(frozen=True)
class EnrichedFrameObservation:
    shared: SharedFrameObservation
    smile: SmileObservation | None
    gaze: GazeObservation


def extract_nonverbal_video_observations(
    video_path: Path,
    *,
    sample_fps: float = 15.0,
    landmarker: Any | None = None,
    timings: dict[str, list[float]] | None = None,
    stage_durations: dict[str, float] | None = None,
    calibration_profile: dict | None = None,
) -> list[EnrichedFrameObservation]:
    """Extract shared facial observations and calibrated MediaPipe gaze."""
    from app.nonverbal.mediapipe_calibration import gaze_observation

    started = perf_counter()
    observations = []
    for shared in extract_video(video_path, sample_fps=sample_fps, landmarker=landmarker, timings=timings):
        gaze_started = perf_counter()
        gaze = (gaze_observation(shared, calibration_profile) if calibration_profile
                else GazeObservation(shared.timestamp_ms, False, "gaze_calibration_pending"))
        if timings is not None:
            timings.setdefault("gaze_batch_total", []).append((perf_counter() - gaze_started) * 1000)
        smile_started = perf_counter()
        smile = extract_smile(shared)
        if timings is not None:
            timings.setdefault("smile", []).append((perf_counter() - smile_started) * 1000)
        observations.append(EnrichedFrameObservation(replace(shared, frame=None), smile, gaze))
    if stage_durations is not None:
        elapsed = perf_counter() - started
        stage_durations.update(shared_seconds=elapsed, combined_seconds=elapsed, mode="mediapipe_only")
    return observations


def extract_nonverbal_video_observations_parallel(
    video_path: Path, *, sample_fps: float = 15.0,
    timings: dict[str, list[float]] | None = None,
    queue_capacity: int = 16, calibration_profile: dict | None = None,
) -> list[EnrichedFrameObservation]:
    if queue_capacity <= 0:
        raise ValueError("queue_capacity must be positive")
    return extract_nonverbal_video_observations(
        video_path, sample_fps=sample_fps, timings=timings, calibration_profile=calibration_profile)


def segment_nonverbal_observations_by_turn(
    observations: Iterable[EnrichedFrameObservation],
    windows: Sequence[TurnWindow],
) -> dict[str, list[EnrichedFrameObservation]]:
    """Assign absolute-timestamp observations using half-open turn windows."""
    result = {window.turn_id: [] for window in windows}
    for observation in observations:
        timestamp_ms = observation.shared.timestamp_ms
        for window in windows:
            if window.start_ms <= timestamp_ms < window.end_ms:
                result[window.turn_id].append(observation)
    return result


def build_turn_raw_features(
    observations: Sequence[EnrichedFrameObservation],
    window: TurnWindow,
    *,
    sample_fps: float = 15.0,
    nod_analysis: NodAnalysis | None = None,
    calibration_profile: dict | None = None,
    patient_roi_snapshots: list[dict] | None = None,
    interaction_area_snapshots: list[dict] | None = None,
    roi_duration_ms: float | None = None,
) -> NonverbalRawFeatures:
    """Build the turn contract without changing absolute observation timestamps."""
    gaze_source = (calibration_profile or {}).get('gaze_source')
    smiles = [item.smile for item in observations if item.smile is not None]
    assigned_events: list[NodEvent] = []
    locally_evaluated = bool(nod_analysis and nod_analysis.evaluated and observations and any(
        window.start_ms <= timestamp < window.end_ms
        for timestamp in nod_analysis.evaluated_timestamps_ms
    ))
    if locally_evaluated:
        assigned_events = [
            event for event in nod_analysis.events
            if window.start_ms <= event.midpoint_ms < window.end_ms
        ]
    duration_minutes = max(0.0, window.end_ms - window.start_ms) / 60000.0
    nod_count = len(assigned_events) if locally_evaluated else None
    nod_rate = nod_count / duration_minutes if nod_count is not None and duration_minutes > 0 else None
    nod_reason = None
    if nod_count is None:
        nod_reason = (nod_analysis.reason if nod_analysis else None) or "insufficient_signal"
    elif nod_rate is None:
        nod_reason = "insufficient_signal"
    try:
        snapshots = parse_patient_roi_snapshots(interaction_area_snapshots, roi_duration_ms)
    except ValueError:
        # A corrupt historical ROI can otherwise turn patient-directed gaze into
        # OTHER_INTERFACE. Keep gaze unavailable while retaining smile and nods.
        snapshots = None
    timestamps = [sample["timestamp_ms"] for sample in snapshots] if snapshots else []

    def roi_at(timestamp_ms: float) -> dict | None:
        index = bisect_right(timestamps, timestamp_ms) - 1
        return snapshots[index] if snapshots and index >= 0 else None

    semantic = [
        {
            "timestamp_ms": item.gaze.timestamp_ms,
            "state": classify_interaction_gaze(
                (item.gaze.unclipped_x, item.gaze.unclipped_y)
                if item.gaze.valid
                and item.gaze.unclipped_x is not None and item.gaze.unclipped_y is not None
                else None,
                calibration_profile,
                roi_at(item.gaze.timestamp_ms),
                camera_match=item.gaze.state == 'mediapipe_camera',
            ),
        }
        for item in observations
    ] if calibration_profile is not None else []
    from app.nonverbal.preprocessing import time_weighted_states
    source_rates = [item.shared.source_fps for item in observations if getattr(item.shared, 'source_fps', None)]
    effective_sample_fps = min(sample_fps, min(source_rates)) if source_rates else sample_fps
    support_ms = min(200., 1000. / effective_sample_fps)
    gaze_support, _ = time_weighted_states(semantic, end_ms=window.end_ms, max_support_ms=support_ms)
    smile_states = [{'timestamp_ms': item.shared.timestamp_ms, 'state': ('INSIDE' if item.smile.smile_detected else 'OUTSIDE') if item.smile else 'UNAVAILABLE'} for item in observations]
    smile_support, _ = time_weighted_states(smile_states, end_ms=window.end_ms, max_support_ms=support_ms)
    valid_times = [item.shared.timestamp_ms for item in observations]
    effective_fps = ((len(valid_times) - 1) * 1000 / (valid_times[-1] - valid_times[0])) if len(valid_times) > 1 and valid_times[-1] > valid_times[0] else None
    return NonverbalRawFeatures(
        face_score_samples=[1.0 for item in observations if item.shared.face_valid],
        gaze_yaw_samples=[],
        gaze_pitch_samples=[],
        smile_activation_samples=[item.smile.smile_activation for item in observations if item.smile],
        smile_detected_samples=[item.smile.smile_detected for item in observations if item.smile],
        gaze_observations=[asdict(item.gaze) for item in observations],
        gaze_semantic_observations=semantic,
        smile_observations=[asdict(item.smile) if item.smile else {'timestamp_ms': item.shared.timestamp_ms} for item in observations],
        head_pitch_samples=[],
        nod_events=[asdict(event) for event in assigned_events],
        nod_predictions=[asdict(item) for item in nod_analysis.predictions
                         if window.start_ms <= item.timestamp_ms < window.end_ms] if nod_analysis else [],
        nod_frame_features=[item for item in nod_analysis.frame_features
                            if window.start_ms <= item['timestamp_ms'] < window.end_ms] if nod_analysis else [],
        nod_count=nod_count,
        nod_rate_min=nod_rate,
        nod_unavailable_reason=nod_reason,
        frame_timestamps_ms=[item.shared.timestamp_ms for item in observations],
        sample_fps=effective_sample_fps,
        turn_duration_ms=max(0, int(window.end_ms - window.start_ms)),
        extractor={"name": "mediapipe_ccdbhg", "version": "5_interaction_area", "window_end_ms": window.end_ms,
                   "gaze_source": gaze_source,
                   "sampling_max_gap_ms": max((item.shared.sampling_max_gap_ms for item in observations), default=100.0)},
        video_quality={
            "expected_frames": max(0, window.end_ms - window.start_ms) * effective_sample_fps / 1000,
            "valid_nod_predictions": sum(window.start_ms <= timestamp < window.end_ms
                for timestamp in nod_analysis.evaluated_timestamps_ms) * effective_sample_fps / 30
                if nod_analysis else 0,
            "nod_evaluable_ms": sum(window.start_ms <= timestamp < window.end_ms
                for timestamp in nod_analysis.evaluated_timestamps_ms) * 1000 / 30 if nod_analysis else 0,
            "nod_eligible_ms": max(0, window.end_ms - window.start_ms - 1000),
            "sampled_frames": len(observations),
            "effective_fps": effective_fps,
            "valid_face_frames": sum(item.shared.face_valid for item in observations),
            "valid_smile_frames": len(smiles),
            "invalid_smile_frames": sum(item.shared.face_valid and any(
                value is not None and not isfinite(value)
                for value in ((item.shared.blendshapes or {}).get("mouthSmileLeft"),
                              (item.shared.blendshapes or {}).get("mouthSmileRight")))
                for item in observations),
            "valid_gaze_frames": sum(item['state'] != 'UNAVAILABLE' for item in semantic),
            "evaluable_gaze_ms": sum(gaze_support.values()),
            "evaluable_smile_ms": sum(smile_support.values()),
        },
    )
