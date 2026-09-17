"""Single-pass full-video nonverbal extraction and timestamp segmentation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Sequence

from app.multimodal.schemas import NonverbalRawFeatures
from app.nonverbal.ccdbhg import NodAnalysis, NodEvent
from app.nonverbal.gaze import GazeObservation, create_tracker, extract_gaze
from app.nonverbal.gaze_calibration import classify_gaze
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
    sample_fps: float = 10.0,
    landmarker: Any | None = None,
    tracker: Any | None = None,
    timings: dict[str, list[float]] | None = None,
) -> list[EnrichedFrameObservation]:
    """Decode the complete video once and fan out one MediaPipe result per frame."""
    gaze_tracker = tracker or create_tracker()
    observations = []
    for shared in extract_video(video_path, sample_fps=sample_fps, landmarker=landmarker, timings=timings):
        started = perf_counter()
        smile = extract_smile(shared)
        if timings is not None:
            timings.setdefault("smile", []).append((perf_counter() - started) * 1000)
        started = perf_counter()
        gaze = (
            extract_gaze(shared, gaze_tracker, timings=timings)
            if timings is not None
            else extract_gaze(shared, gaze_tracker)
        )
        if timings is not None:
            timings.setdefault("gaze_total", []).append((perf_counter() - started) * 1000)
        # The decoded HD frame is needed only by BlazeGaze. Retaining it for the
        # complete video can consume gigabytes and destabilize native libraries;
        # downstream smile/nod/quality stages use landmarks and matrices only.
        observations.append(EnrichedFrameObservation(replace(shared, frame=None), smile, gaze))
    return observations


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
    sample_fps: float = 10.0,
    nod_analysis: NodAnalysis | None = None,
    calibration_profile: dict | None = None,
    patient_roi_snapshots: Sequence[dict] = (),
) -> NonverbalRawFeatures:
    """Build the turn contract without changing absolute observation timestamps."""
    smiles = [item.smile for item in observations if item.smile is not None]
    assigned_events: list[NodEvent] = []
    if nod_analysis is not None and nod_analysis.evaluated:
        assigned_events = [
            event for event in nod_analysis.events
            if window.start_ms <= event.midpoint_ms < window.end_ms
        ]
    duration_minutes = max(0.0, window.end_ms - window.start_ms) / 60000.0
    nod_count = len(assigned_events) if nod_analysis and nod_analysis.evaluated else None
    nod_rate = nod_count / duration_minutes if nod_count is not None and duration_minutes > 0 else None
    nod_reason = None
    if nod_count is None:
        nod_reason = (nod_analysis.reason if nod_analysis else "insufficient_signal")
    elif nod_rate is None:
        nod_reason = "insufficient_signal"
    def roi_at(timestamp_ms: float) -> dict | None:
        eligible = [item for item in patient_roi_snapshots if float(item.get("timestampMs", item.get("timestamp_ms", -1))) <= timestamp_ms]
        selected = eligible[-1] if eligible else (patient_roi_snapshots[0] if patient_roi_snapshots else None)
        if selected is None:
            return None
        return {
            "x_normalized": selected.get("xNormalized", selected.get("x_normalized")),
            "y_normalized": selected.get("yNormalized", selected.get("y_normalized")),
            "width_normalized": selected.get("widthNormalized", selected.get("width_normalized")),
            "height_normalized": selected.get("heightNormalized", selected.get("height_normalized")),
        }

    semantic = [
        {
            "timestamp_ms": item.gaze.timestamp_ms,
            "state": classify_gaze(
                (item.gaze.unclipped_x, item.gaze.unclipped_y) if item.gaze.valid and item.gaze.unclipped_x is not None and item.gaze.unclipped_y is not None else None,
                calibration_profile,
                roi_at(item.gaze.timestamp_ms),
            ),
        }
        for item in observations
    ] if calibration_profile is not None else []
    return NonverbalRawFeatures(
        face_score_samples=[1.0 for item in observations if item.shared.face_valid],
        gaze_yaw_samples=[],
        gaze_pitch_samples=[],
        au12_samples=[item.smile.smile_activation for item in observations if item.smile],
        smile_detected_samples=[item.smile.smile_detected for item in observations if item.smile],
        gaze_observations=[asdict(item.gaze) for item in observations],
        gaze_semantic_observations=semantic,
        head_pitch_samples=[],
        nod_events=[asdict(event) for event in assigned_events],
        nod_count=nod_count,
        nod_rate_min=nod_rate,
        nod_unavailable_reason=nod_reason,
        frame_timestamps_ms=[item.shared.timestamp_ms for item in observations],
        sample_fps=sample_fps,
        turn_duration_ms=max(0, int(window.end_ms - window.start_ms)),
        extractor={"name": "mediapipe_blazegaze_ccdbhg", "version": "1"},
        video_quality={
            "sampled_frames": len(observations),
            "valid_face_frames": sum(item.shared.face_valid for item in observations),
            "valid_smile_frames": len(smiles),
            "valid_gaze_frames": sum(item.gaze.valid for item in observations),
        },
    )
