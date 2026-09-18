"""Read-only performance profile for the latest persisted interview.

The script calls the production extractors and processing functions but never
persists their outputs. Run it in the existing API container.
"""

from __future__ import annotations

import json
import hashlib
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import resource
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from pathlib import Path
from time import perf_counter
from threading import Event, Thread
from time import sleep
from typing import Any, Callable


PROCESS_STARTED = perf_counter()
IMPORT_STARTED = perf_counter()

import numpy as np
import torch

from app.core.database import SessionLocal
from app.media import get_media_storage
from app.models.calibration import CalibrationAttemptDB, CalibrationStatus
from app.models.medical_interview import (
    InterviewMediaAssetDB,
    InterviewRecordingDB,
    InterviewTurnDB,
    MediaAssetKind,
    MedicalInterviewDB,
)
from app.multimodal import pipeline
from app.multimodal.config_loader import load_methodology_config
from app.multimodal.schemas import PersonalBaseline
from app.nonverbal import ccdbhg
from app.nonverbal.gaze import create_tracker
from app.nonverbal.mediapipe_extractor import create_face_landmarker
from app.nonverbal.preprocessing import preprocess_nonverbal_turn
from app.nonverbal.video_observations import (
    TurnWindow,
    build_turn_raw_features,
    extract_nonverbal_video_observations,
    extract_nonverbal_video_observations_parallel,
    segment_nonverbal_observations_by_turn,
)
from app.paraverbal import opensmile_extractor
from app.paraverbal.opensmile_extractor import StudentTurnAudio
from app.paraverbal.preprocessing import preprocess_paraverbal

IMPORT_MS = (perf_counter() - IMPORT_STARTED) * 1000.0


class Timer:
    def __init__(self) -> None:
        self.values: dict[str, list[float]] = defaultdict(list)

    def call(self, name: str, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        started = perf_counter()
        result = function(*args, **kwargs)
        self.values[name].append((perf_counter() - started) * 1000.0)
        return result

    def total(self, name: str) -> float:
        return float(sum(self.values.get(name, ())))


def _asset(db: Any, recording_id: str, kind: str) -> InterviewMediaAssetDB:
    return (
        db.query(InterviewMediaAssetDB)
        .filter_by(recording_id=recording_id, kind=kind, status="ready")
        .one()
    )


def _probe(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate,nb_read_frames,duration",
            "-show_entries", "format=duration,size", "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"calls": 0, "total_ms": 0.0, "mean_ms": None, "p50_ms": None, "p90_ms": None, "p95_ms": None, "max_ms": None}
    ordered = sorted(values)
    percentile = lambda fraction: ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]
    return {
        "calls": len(values), "total_ms": float(sum(values)), "mean_ms": statistics.mean(values),
        "p50_ms": percentile(0.50), "p90_ms": percentile(0.90),
        "p95_ms": percentile(0.95), "max_ms": max(values),
    }


def _current_rss_kib() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    return 0


def _time_audio(path: Path, turns: list[InterviewTurnDB], timer: Timer) -> tuple[dict[str, Any], dict[str, Any]]:
    import opensmile

    windows = [StudentTurnAudio(t.id, t.start_ms, t.end_ms, t.transcript) for t in turns]
    extracted: dict[str, Any] = {}
    started_total = perf_counter()
    smile = timer.call(
        "audio.opensmile_initialization",
        opensmile.Smile,
        feature_set=opensmile.FeatureSet.eGeMAPSv02,
        feature_level=opensmile.FeatureLevel.LowLevelDescriptors,
    )
    with tempfile.TemporaryDirectory(prefix="multimodal-profile-") as directory:
        temp_dir = Path(directory)
        for turn in windows:
            wav_path = temp_dir / f"{turn.turn_id}.wav"
            duration_ms = turn.end_ms - turn.start_ms
            timer.call("audio.ffmpeg", opensmile_extractor._decode_segment, path, wav_path, turn.start_ms, duration_ms)
            samples, sample_rate = timer.call("audio.loading", opensmile_extractor._read_pcm_wav, wav_path)
            started = perf_counter()
            raw = opensmile_extractor._extract_raw_features(
                wav_path, samples, duration_ms, turn.transcript, smile=smile,
                min_voiced_duration_ms=opensmile_extractor.MIN_VOICED_DURATION_MS,
            )
            elapsed = (perf_counter() - started) * 1000.0
            timer.values["audio.opensmile_and_raw"].append(elapsed)
            if raw is not None:
                extracted[turn.turn_id] = raw
    extraction_ms = (perf_counter() - started_total) * 1000.0
    processed = {}
    for turn_id, raw in extracted.items():
        processed[turn_id] = timer.call("audio.preprocessing", preprocess_paraverbal, raw, baseline=None)
    opensmile_ms = timer.total("audio.opensmile_and_raw")
    return extracted, {
        "total_ms": extraction_ms + timer.total("audio.preprocessing"),
        "extraction_ms": extraction_ms,
        "ffmpeg_ms": timer.total("audio.ffmpeg"),
        "loading_ms": timer.total("audio.loading"),
        "initialization_ms": timer.total("audio.opensmile_initialization"),
        "opensmile_and_raw_ms": opensmile_ms,
        "preprocessing_ms": timer.total("audio.preprocessing"),
        "observed_turns": len(extracted),
        "valid_voiced_ms": sum(raw.voiced_duration_ms for raw in extracted.values()),
        "processed": processed,
    }


def _time_nods(shared: list[Any], timer: Timer) -> tuple[ccdbhg.NodAnalysis, dict[str, Any]]:
    original_landmark = ccdbhg.landmark_features
    original_head = ccdbhg.head_pose_features

    def landmark(item: Any) -> np.ndarray:
        return timer.call("nod.landmarks", original_landmark, item)

    def head(matrix: np.ndarray) -> np.ndarray:
        return timer.call("nod.head_pose", original_head, matrix)

    ccdbhg.landmark_features = landmark
    ccdbhg.head_pose_features = head
    total_started = perf_counter()
    try:
        features = timer.call("nod.channels", ccdbhg.frame_features, shared)
    finally:
        ccdbhg.landmark_features = original_landmark
        ccdbhg.head_pose_features = original_head
    windows = timer.call("nod.resampling", ccdbhg.resample_windows, features)
    _, std, model = timer.call("nod.model_load", ccdbhg.load_default_bundle)
    predictions = []
    for timestamp, window in windows:
        model_input = timer.call("nod.normalization", ccdbhg.preprocess_window, window, std)
        tensor = timer.call("nod.numpy_to_torch", torch.from_numpy, model_input.T[None])
        tensor = timer.call("nod.float_conversion", tensor.float)
        started = perf_counter()
        with torch.no_grad():
            logits = model(tensor)
        timer.values["nod.inference"].append((perf_counter() - started) * 1000.0)
        started = perf_counter()
        probabilities = torch.softmax(logits, dim=1)[0]
        class_id = int(torch.argmax(probabilities))
        predictions.append(ccdbhg.WindowPrediction(timestamp, class_id, float(probabilities[class_id])))
        timer.values["nod.softmax_argmax"].append((perf_counter() - started) * 1000.0)
    events = timer.call("nod.event_consolidation", ccdbhg.nod_events, predictions)
    total_ms = (perf_counter() - total_started) * 1000.0
    analysis = ccdbhg.NodAnalysis(tuple(events), bool(predictions), None if predictions else "insufficient_signal")
    return analysis, {
        "total_ms": total_ms,
        "input_observations": len(shared),
        "feature_samples": len(features),
        "resampled_samples": len(windows) + ccdbhg.WINDOW_SAMPLES - 1 if windows else 0,
        "windows": len(windows),
        "inference_calls": len(windows),
        "batch_size": 1,
        "landmark_ms": timer.total("nod.landmarks"),
        "channels_ms": timer.total("nod.channels"),
        "head_pose_ms": timer.total("nod.head_pose"),
        "resampling_ms": timer.total("nod.resampling"),
        "model_load_ms": timer.total("nod.model_load"),
        "normalization_ms": timer.total("nod.normalization"),
        "numpy_to_torch_ms": timer.total("nod.numpy_to_torch") + timer.total("nod.float_conversion"),
        "inference_ms": timer.total("nod.inference"),
        "mean_inference_ms_window": statistics.mean(timer.values["nod.inference"]) if windows else None,
        "softmax_argmax_ms": timer.total("nod.softmax_argmax"),
        "event_consolidation_ms": timer.total("nod.event_consolidation"),
        "events": len(events),
    }


def _time_video(path: Path, turns: list[InterviewTurnDB], recording: InterviewRecordingDB, timer: Timer, *, parallel_video: bool = False, queue_capacity: int = 16) -> tuple[dict[str, Any], dict[str, Any]]:
    timings: dict[str, list[float]] = {}
    initialization_started = perf_counter()
    landmarker = None if parallel_video else create_face_landmarker(timings=timings)
    tracker = create_tracker(timings=timings)
    initialization_ms = (perf_counter() - initialization_started) * 1000.0
    try:
        extraction_started = perf_counter()
        if parallel_video:
            observations = extract_nonverbal_video_observations_parallel(
                path, sample_fps=10.0, tracker=tracker, timings=timings,
                queue_capacity=queue_capacity,
            )
        else:
            observations = extract_nonverbal_video_observations(
                path, sample_fps=10.0, landmarker=landmarker, tracker=tracker, timings=timings
            )
        shared_extraction_ms = (perf_counter() - extraction_started) * 1000.0
    finally:
        if landmarker is not None:
            landmarker.close()
    shared = [item.shared for item in observations]
    nod_analysis, nod = _time_nods(shared, timer)
    windows = [TurnWindow(t.id, t.start_ms, t.end_ms, t.speaker) for t in turns]
    segmented = timer.call("video.turn_segmentation", segment_nonverbal_observations_by_turn, observations, windows)
    raw_by_turn = {}
    for window in windows:
        raw_by_turn[window.turn_id] = timer.call(
            "video.feature_aggregation", build_turn_raw_features,
            segmented[window.turn_id], window, nod_analysis=nod_analysis,
            calibration_profile=None,
            patient_roi_snapshots=(recording.capture_config or {}).get("patientRoiSnapshots", []),
        )
    processed = {}
    reasons = {}
    for turn in turns:
        result = timer.call(
            "video.preprocessing", preprocess_nonverbal_turn,
            raw_by_turn[turn.id], "speaking" if turn.speaker == "student" else "listening", baseline=None,
        )
        processed[turn.id] = result.processed
        reasons[turn.id] = result.reasons
    sums = {key: float(sum(values)) for key, values in timings.items()}
    decode_calls = len(timings.get("video_decode", [])) - 1
    valid_face = sum(item.face_valid for item in shared)
    valid_gaze = sum(item.gaze.valid for item in observations)
    invalid_states: dict[str, int] = defaultdict(int)
    for item in observations:
        if not item.gaze.valid:
            invalid_states[item.gaze.state] += 1
    blaze_batches = int(tracker._optimization_counters.get("blazegaze_batches", 0))
    return raw_by_turn, {
        "total_ms": initialization_ms + shared_extraction_ms + nod["total_ms"] + timer.total("video.turn_segmentation") + timer.total("video.feature_aggregation") + timer.total("video.preprocessing"),
        "initialization_ms": initialization_ms,
        "shared_extraction_ms": shared_extraction_ms,
        "video_open_ms": sums.get("startup.video_open", 0.0),
        "decode_ms": sums.get("video_decode", 0.0),
        "decode_calls": decode_calls,
        "frame_conversion_ms": sums.get("frame_conversion", 0.0),
        "mediapipe_ms": sums.get("mediapipe_face_landmarker", 0.0),
        "shared_construction_unattributed_ms": max(0.0, shared_extraction_ms - sums.get("video_decode", 0.0) - sums.get("frame_conversion", 0.0) - sums.get("mediapipe_face_landmarker", 0.0) - sums.get("gaze_batch_total", 0.0) - sums.get("smile", 0.0)),
        "selected_frames": len(observations),
        "valid_face_frames": valid_face,
        "no_face_frames": len(observations) - valid_face,
        "smile_ms": sums.get("smile", 0.0),
        "gaze_ms": sums.get("gaze_batch_total", 0.0),
        "gaze_prepare_ms": sums.get("webeyetrack_prepare_input", 0.0),
        "gaze_face_reconstruction_ms": sums.get("prepare_input.face_origin.reconstruction.total", 0.0),
        "gaze_uvz_ms": sums.get("prepare_input.face_origin.reconstruction.uvz_to_xyz", 0.0),
        "gaze_depth_ms": sums.get("prepare_input.face_origin.reconstruction.depth_refinement_loop", 0.0),
        "gaze_eyepatch_ms": sums.get("prepare_input.eyepatch.total", 0.0),
        "gaze_head_vector_ms": sums.get("prepare_input.head_vector.total", 0.0),
        "gaze_packaging_ms": sums.get("blazegaze_batch_packaging", 0.0),
        "gaze_inference_ms": sums.get("blazegaze_batch_inference", 0.0),
        "gaze_affine_kalman_ms": sums.get("webeyetrack_affine_and_kalman", 0.0),
        "valid_gaze": valid_gaze,
        "invalid_gaze": len(observations) - valid_gaze,
        "invalid_gaze_states": dict(invalid_states),
        "blazegaze_batches": blaze_batches,
        "blazegaze_samples": int(tracker._optimization_counters.get("blazegaze_samples", 0)),
        "mean_effective_batch_size": (
            float(tracker._optimization_counters.get("blazegaze_samples", 0)) / blaze_batches
            if blaze_batches else None
        ),
        "blazegaze_max_batch_size": tracker._optimization_counters.get("blazegaze_max_batch_size"),
        "mean_inference_ms_sample": sums.get("blazegaze_batch_inference", 0.0) / valid_gaze if valid_gaze else None,
        "turn_segmentation_ms": timer.total("video.turn_segmentation"),
        "feature_aggregation_ms": timer.total("video.feature_aggregation"),
        "preprocessing_ms": timer.total("video.preprocessing"),
        "nod": nod,
        "processed": processed,
        "reasons": reasons,
        "timing_sums": sums,
        "timing_distributions": {
            key: _distribution(values)
            for key, values in timings.items()
            if key.startswith("mediapipe.") or key.startswith("frame_conversion.")
        },
    }


def main() -> None:
    rss_before_kib = _current_rss_kib()
    benchmark_started = perf_counter()
    cpu_started = os.times()
    monitor_stop = Event()
    monitor = {"peak_threads": 0, "peak_rss_kib": 0}

    def sample_process() -> None:
        while not monitor_stop.is_set():
            try:
                fields = {}
                for line in Path("/proc/self/status").read_text().splitlines():
                    if ":" in line:
                        key, value = line.split(":", 1)
                        fields[key] = value.strip()
                monitor["peak_threads"] = max(monitor["peak_threads"], int(fields["Threads"]))
                monitor["peak_rss_kib"] = max(
                    monitor["peak_rss_kib"], int(fields["VmRSS"].split()[0])
                )
            except (OSError, KeyError, ValueError):
                pass
            sleep(0.25)

    monitor_thread = Thread(target=sample_process, name="profile-monitor", daemon=True)
    monitor_thread.start()
    timer = Timer()
    db = SessionLocal()
    try:
        recording = db.query(InterviewRecordingDB).order_by(InterviewRecordingDB.created_at.desc()).first()
        interview = db.query(MedicalInterviewDB).filter_by(id=recording.medical_interview_id).one()
        turns = db.query(InterviewTurnDB).filter_by(medical_interview_id=interview.id).order_by(InterviewTurnDB.sequence).all()
        student_turns = [turn for turn in turns if turn.speaker == "student"]
        audio_asset = _asset(db, recording.id, MediaAssetKind.STUDENT_AUDIO.value)
        video_asset = _asset(db, recording.id, MediaAssetKind.STUDENT_VIDEO.value)
        storage = get_media_storage()
        audio_path = storage.resolve(audio_asset.storage_key)
        video_path = storage.resolve(video_asset.storage_key)
        probe_ms = 0.0
        calibration = db.query(CalibrationAttemptDB).filter(
            CalibrationAttemptDB.medical_interview_id == interview.id,
            CalibrationAttemptDB.status == CalibrationStatus.PASSED.value,
            CalibrationAttemptDB.is_active.is_(True),
        ).first()
        config = timer.call("post.config", load_methodology_config)
        variant = os.environ.get("PROFILE_VARIANT", "baseline")
        parallel_video = variant in {"b16", "b32", "ab16", "ab32"}
        queue_capacity = 32 if variant in {"b32", "ab32"} else 16
        if variant in {"a", "ab16", "ab32"}:
            audio_timer, video_timer = Timer(), Timer()
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="modality") as executor:
                audio_future = executor.submit(_time_audio, audio_path, student_turns, audio_timer)
                video_future = executor.submit(
                    _time_video, video_path, turns, recording, video_timer,
                    parallel_video=parallel_video, queue_capacity=queue_capacity,
                )
                audio_raw, audio = audio_future.result()
                video_raw, video = video_future.result()
        else:
            audio_raw, audio = _time_audio(audio_path, student_turns, timer)
            video_raw, video = _time_video(
                video_path, turns, recording, timer,
                parallel_video=parallel_video, queue_capacity=queue_capacity,
            )

        para_processed = audio.pop("processed")
        nonverbal_processed = video.pop("processed")
        nonverbal_reasons = video.pop("reasons")
        para_refs = timer.call("post.session_references", pipeline._session_references, processed_by_turn=para_processed, feature_names=pipeline._PARAVERBAL_SESSION_FEATURES, min_turns=int(config.thresholds.get("min_turns_for_session_stats", 0) or 0))
        nonverbal_refs = timer.call("post.session_references", pipeline._session_references, processed_by_turn=nonverbal_processed, feature_names=pipeline._NONVERBAL_SESSION_FEATURES, min_turns=int(config.thresholds.get("min_turns_for_session_stats", 0) or 0))
        outcome = pipeline._OutcomeTracker()
        results = []
        for turn in turns:
            results.append(timer.call(
                "post.threshold_labels_assembly", pipeline._assemble_turn_result,
                turn=turn, config=config, versions=config.versions.model_dump(), config_hash=config.config_hash,
                baseline_available=False, paraverbal_raw=audio_raw.get(turn.id),
                paraverbal_processed=para_processed.get(turn.id), para_session_refs=para_refs,
                nonverbal_raw=video_raw.get(turn.id), nonverbal_processed=nonverbal_processed.get(turn.id),
                nonverbal_reasons=nonverbal_reasons.get(turn.id, {}), nonverbal_session_refs=nonverbal_refs,
                outcome=outcome,
            ))
        timer.call("post.fusion_handoff", pipeline._late_fusion_handoff, interview_id=interview.id, recording_id=recording.id)
        timer.call("post.serialization", lambda: [item.model_dump(mode="json") for item in results])
        end_to_end_ms = (perf_counter() - PROCESS_STARTED) * 1000.0
        original_frames = video["decode_calls"]
        feature_summary = []
        for turn, result in zip(turns, results):
            nv = result.nonverbal.processed if result.nonverbal and result.nonverbal.processed else {}
            feature_summary.append({
                "turn_id": turn.id, "sequence": turn.sequence, "speaker": turn.speaker,
                "nod_count": nv.get("nod_count"), "nod_rate_min": nv.get("nod_rate_min"),
                "smile_activity_ratio": nv.get("smile_activity_ratio"),
                "mean_smile_activation": nv.get("mean_smile_activation"),
                "visual_alignment_ratio": nv.get("visual_alignment_ratio"),
                "median_visual_alignment_dwell_ms": nv.get("median_visual_alignment_dwell_ms"),
            })
        wall_seconds = (perf_counter() - benchmark_started)
        cpu_ended = os.times()
        cpu_seconds = (
            cpu_ended.user + cpu_ended.system - cpu_started.user - cpu_started.system
        )
        monitor_stop.set()
        monitor_thread.join(timeout=1.0)
        feature_json = json.dumps(feature_summary, sort_keys=True, separators=(",", ":"))
        payload = {
            "interview": {
                "interview_id": interview.id, "recording_id": recording.id,
                "video_path": str(video_path), "duration_ms": recording.duration_ms,
                "resolution": [recording.capture_config["video"]["width"], recording.capture_config["video"]["height"]],
                "configured_frame_rate": recording.capture_config["video"]["frameRate"],
                "original_frames": original_frames, "turns": len(turns),
                "student_speaking_ms": sum(t.end_ms - t.start_ms for t in student_turns),
                "patient_speaking_ms": sum(t.end_ms - t.start_ms for t in turns if t.speaker == "patient"),
                "file_size": video_asset.size_bytes, "probe_ms": probe_ms,
            },
            "calibration": None if calibration is None else {"id": calibration.id, "status": calibration.status, "version": calibration.calibration_version},
            "environment": {"python": sys.version, "torch": torch.__version__, "cpu_count": os.cpu_count(), "platform": platform.platform()},
            "variant": variant,
            "startup": {"imports_ms": IMPORT_MS, "until_main_ms": (PROCESS_STARTED - PROCESS_STARTED) * 1000.0},
            "audio": audio,
            "video": video,
            "post": {
                "config_ms": timer.total("post.config"), "session_references_ms": timer.total("post.session_references"),
                "threshold_labels_assembly_ms": timer.total("post.threshold_labels_assembly"),
                "fusion_handoff_ms": timer.total("post.fusion_handoff"), "serialization_ms": timer.total("post.serialization"),
            },
            "end_to_end_ms": end_to_end_ms,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "rss_before_kib": rss_before_kib,
            "rss_after_kib": _current_rss_kib(),
            "sampled_peak_rss_kib": monitor["peak_rss_kib"],
            "peak_threads": monitor["peak_threads"],
            "cpu_seconds": cpu_seconds,
            "average_cpu_percent_total": cpu_seconds / wall_seconds * 100.0,
            "average_cpu_percent_capacity": cpu_seconds / wall_seconds / max(os.cpu_count() or 1, 1) * 100.0,
            "outcome": outcome.final_status(),
            "feature_summary": feature_summary,
            "feature_digest": hashlib.sha256(feature_json.encode()).hexdigest(),
        }
        if os.environ.get("PROFILE_COMPACT") == "1":
            compact = {
                "variant": variant,
                "end_to_end_ms": payload["end_to_end_ms"],
                "audio_ms": audio["total_ms"], "video_ms": video["total_ms"],
                "decode_ms": video["decode_ms"], "conversion_ms": video["frame_conversion_ms"],
                "mediapipe_ms": video["mediapipe_ms"], "gaze_ms": video["gaze_ms"],
                "blazegaze_ms": video["gaze_inference_ms"], "nod_ms": video["nod"]["total_ms"],
                "post_ms": sum(payload["post"].values()),
                "peak_rss_kib": payload["peak_rss_kib"], "sampled_peak_rss_kib": monitor["peak_rss_kib"],
                "rss_before_kib": payload["rss_before_kib"], "rss_after_kib": payload["rss_after_kib"],
                "peak_threads": monitor["peak_threads"], "cpu_seconds": cpu_seconds,
                "average_cpu_percent_total": payload["average_cpu_percent_total"],
                "average_cpu_percent_capacity": payload["average_cpu_percent_capacity"],
                "selected_frames": video["selected_frames"], "valid_faces": video["valid_face_frames"],
                "valid_gaze": video["valid_gaze"], "invalid_gaze": video["invalid_gaze"],
                "eyes_closed": video["invalid_gaze_states"].get("eyes_closed", 0),
                "nod_events": video["nod"]["events"], "feature_digest": payload["feature_digest"],
            }
            print("PROFILE_JSON=" + json.dumps(compact, separators=(",", ":")))
        else:
            print("PROFILE_JSON=" + json.dumps(payload, default=str, separators=(",", ":")))
    finally:
        monitor_stop.set()
        monitor_thread.join(timeout=1.0)
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
