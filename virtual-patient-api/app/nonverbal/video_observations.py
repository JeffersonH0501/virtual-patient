"""Single-pass full-video nonverbal extraction and timestamp segmentation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import perf_counter
from typing import Any, Iterable, Sequence

from app.multimodal.schemas import NonverbalRawFeatures
from app.nonverbal.ccdbhg import NodAnalysis, NodEvent
from app.nonverbal.gaze import (
    GAZE_BATCH_SIZE,
    GazeObservation,
    create_tracker,
    create_batch_buffers,
    extract_gaze,
    extract_gaze_batch,
)
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
    pending = []
    batch_buffers = create_batch_buffers()

    def flush() -> None:
        if not pending:
            return
        gaze_started = perf_counter()
        if hasattr(gaze_tracker, "batched_infer_fn"):
            gazes = extract_gaze_batch(
                pending,
                gaze_tracker,
                timings=timings,
                batch_buffers=batch_buffers,
            )
        else:
            gazes = [
                extract_gaze(item, gaze_tracker, timings=timings)
                if timings is not None
                else extract_gaze(item, gaze_tracker)
                for item in pending
            ]
        if timings is not None:
            elapsed_ms = (perf_counter() - gaze_started) * 1000
            timings.setdefault("gaze_batch_total", []).append(elapsed_ms)
            timings.setdefault("gaze_total", []).extend(
                [elapsed_ms / len(pending)] * len(pending)
            )
        for shared, gaze in zip(pending, gazes):
            started = perf_counter()
            smile = extract_smile(shared)
            if timings is not None:
                timings.setdefault("smile", []).append(
                    (perf_counter() - started) * 1000
                )
            observations.append(
                EnrichedFrameObservation(replace(shared, frame=None), smile, gaze)
            )
        pending.clear()

    for shared in extract_video(
        video_path, sample_fps=sample_fps, landmarker=landmarker, timings=timings
    ):
        pending.append(shared)
        if len(pending) == GAZE_BATCH_SIZE:
            flush()
    flush()
    return observations


def extract_nonverbal_video_observations_parallel(
    video_path: Path,
    *,
    sample_fps: float = 10.0,
    tracker: Any | None = None,
    timings: dict[str, list[float]] | None = None,
    queue_capacity: int = 16,
) -> list[EnrichedFrameObservation]:
    """Overlap sequential MediaPipe production with ordered gaze consumption."""
    if queue_capacity <= 0:
        raise ValueError("queue_capacity must be positive")
    gaze_tracker = tracker or create_tracker()
    batch_buffers = create_batch_buffers()
    queue: Queue[Any] = Queue(maxsize=queue_capacity)
    cancelled = Event()
    sentinel = object()
    producer_error: list[BaseException] = []

    def put(item: Any) -> bool:
        while not cancelled.is_set():
            try:
                queue.put(item, timeout=0.1)
                return True
            except Full:
                continue
        return False

    def produce() -> None:
        try:
            for shared in extract_video(video_path, sample_fps=sample_fps, timings=timings):
                if not put(shared):
                    return
            if not put(sentinel):
                return
        except BaseException as error:  # noqa: BLE001 - propagate across thread.
            producer_error.append(error)
        finally:
            if producer_error:
                put(sentinel)

    producer = Thread(target=produce, name="mediapipe-producer", daemon=False)
    producer.start()
    observations: list[EnrichedFrameObservation] = []
    pending: list[SharedFrameObservation] = []

    def flush() -> None:
        if not pending:
            return
        gaze_started = perf_counter()
        gazes = extract_gaze_batch(
            pending,
            gaze_tracker,
            timings=timings,
            batch_buffers=batch_buffers,
        )
        if timings is not None:
            elapsed_ms = (perf_counter() - gaze_started) * 1000
            timings.setdefault("gaze_batch_total", []).append(elapsed_ms)
            timings.setdefault("gaze_total", []).extend(
                [elapsed_ms / len(pending)] * len(pending)
            )
        for shared, gaze in zip(pending, gazes):
            started = perf_counter()
            smile = extract_smile(shared)
            if timings is not None:
                timings.setdefault("smile", []).append(
                    (perf_counter() - started) * 1000
                )
            observations.append(
                EnrichedFrameObservation(replace(shared, frame=None), smile, gaze)
            )
        pending.clear()

    try:
        while True:
            try:
                item = queue.get(timeout=0.1)
            except Empty:
                if not producer.is_alive() and queue.empty():
                    break
                continue
            if item is sentinel:
                break
            pending.append(item)
            if len(pending) == GAZE_BATCH_SIZE:
                flush()
        flush()
        if producer_error:
            raise producer_error[0]
        return observations
    except BaseException:  # noqa: BLE001 - cancel producer and preserve error.
        cancelled.set()
        raise
    finally:
        cancelled.set()
        producer.join(timeout=5.0)
        if producer.is_alive():
            raise RuntimeError("MediaPipe producer did not terminate")


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
