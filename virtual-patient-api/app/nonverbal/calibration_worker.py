"""Crash-isolated video/audio workers for multimodal calibration."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from time import perf_counter
import numpy as np
from app.models.calibration import CameraCalibrationMetadata, CalibrationCaptureMetadata, GazeCalibrationMetadata

CALIBRATION_SAMPLE_FPS = 10.0


def summarize_timings(timings: dict[str, list[float]]) -> dict:
    summary = {}
    for name, samples in timings.items():
        if not samples:
            continue
        values = np.asarray(samples, dtype=float)
        summary[name] = {
            "count": int(len(values)),
            "total_ms": float(values.sum()),
            "mean_ms": float(values.mean()),
            "p50_ms": float(np.percentile(values, 50)),
            "p90_ms": float(np.percentile(values, 90)),
            "p95_ms": float(np.percentile(values, 95)),
            "max_ms": float(values.max()),
        }
    return summary


def process_video(path: Path, metadata: CalibrationCaptureMetadata) -> dict:
    startup_timings: dict[str, list[float]] = {}
    started = perf_counter()
    from app.nonverbal.ccdbhg import head_pose_features
    from app.nonverbal.gaze import create_tracker
    from app.nonverbal.gaze_calibration import build_profile
    from app.nonverbal.mediapipe_extractor import create_face_landmarker
    from app.nonverbal.video_observations import extract_nonverbal_video_observations
    startup_timings["startup.video_module_imports"] = [(perf_counter() - started) * 1000]

    started = perf_counter()
    landmarker = create_face_landmarker(timings=startup_timings)
    startup_timings["startup.mediapipe_landmarker_creation"] = [(perf_counter() - started) * 1000]
    started = perf_counter()
    tracker = create_tracker(kalman_enabled=False, timings=startup_timings)
    startup_timings["startup.webeyetrack_and_blazegaze_creation"] = [(perf_counter() - started) * 1000]
    timings: dict[str, list[float]] = startup_timings
    started = perf_counter()
    try:
        observations = extract_nonverbal_video_observations(path, sample_fps=CALIBRATION_SAMPLE_FPS, tracker=tracker, landmarker=landmarker, timings=timings)
    finally:
        landmarker.close()
    timings["pipeline.video_extraction_wall"] = [(perf_counter() - started) * 1000]
    shared = [item.shared for item in observations]
    valid_faces = [item for item in shared if item.face_valid]
    # Voice is evaluated by a separate OpenSMILE-only process. Passing neutral
    # placeholders here lets this result represent only the visual gate.
    started = perf_counter()
    profile, quality, passed, reason = build_profile([item.gaze for item in observations], metadata, face_valid_ratio=len(valid_faces) / len(shared) if shared else 0.0, voiced_duration_ms=3000, clipping=False)
    head = [head_pose_features(item.facial_transformation_matrix) for item in valid_faces if item.facial_transformation_matrix is not None]
    neutral_head = None
    if head:
        median_head = np.median(np.asarray(head), axis=0)
        neutral_head = {"neutral_head_yaw": float(median_head[0]), "neutral_head_pitch": float(median_head[2]), "neutral_head_roll": float(median_head[1])}
    timings["pipeline.calibration_finalization"] = [(perf_counter() - started) * 1000]
    return {"profile": profile, "quality": quality, "passed": passed, "failure_reason": reason, "neutral_head": neutral_head, "performance": summarize_timings(timings), "optimization_counters": tracker._optimization_counters}


def process_audio(path: Path, metadata: CalibrationCaptureMetadata) -> dict:
    from app.paraverbal.opensmile_extractor import StudentTurnAudio, analyze_student_turns

    voice = analyze_student_turns(path, [StudentTurnAudio("voice", metadata.voice_baseline_start_ms, metadata.voice_baseline_end_ms, "Clear communication helps us understand a patient's needs during a clinical consultation.")], min_voiced_duration_ms=3000).get("voice")
    return {
        "voiced_duration_ms": voice.voiced_duration_ms if voice else 0,
        "clipping_detected": bool(voice and "clipping_detected" in voice.audio_quality.get("issues", [])),
        "baseline_f0_semitones": float(np.median(voice.f0_samples_semitones)) if voice and voice.f0_samples_semitones else None,
        "baseline_loudness": float(np.median(voice.loudness_samples)) if voice and voice.loudness_samples else None,
    }


def process_gaze(
    path: Path,
    metadata: GazeCalibrationMetadata,
    *,
    tracker=None,
    landmarker=None,
) -> dict:
    from app.nonverbal.gaze import create_tracker
    from app.nonverbal.gaze_calibration import build_gaze_profile
    from app.nonverbal.mediapipe_extractor import create_face_landmarker
    from app.nonverbal.video_observations import extract_nonverbal_video_observations

    owns_landmarker = landmarker is None
    landmarker = landmarker or create_face_landmarker()
    tracker = tracker or create_tracker(kalman_enabled=False)
    try:
        observations = extract_nonverbal_video_observations(path, sample_fps=CALIBRATION_SAMPLE_FPS, tracker=tracker, landmarker=landmarker)
    finally:
        if owns_landmarker:
            landmarker.close()
    shared = [item.shared for item in observations]
    valid_faces = [item for item in shared if item.face_valid]
    profile, quality, passed, reason = build_gaze_profile(
        [item.gaze for item in observations], metadata,
        face_valid_ratio=len(valid_faces) / len(shared) if shared else 0.0,
    )
    return {"profile": profile, "quality": quality, "passed": passed, "failure_reason": reason}


def process_camera(
    path: Path,
    metadata: CameraCalibrationMetadata,
    *,
    tracker=None,
    landmarker=None,
) -> dict:
    from app.nonverbal.ccdbhg import head_pose_features
    from app.nonverbal.gaze import create_tracker
    from app.nonverbal.gaze_calibration import MIN_CAMERA_VALID_MS, MIN_FACE_VALID_RATIO, apply_affine
    from app.nonverbal.mediapipe_extractor import create_face_landmarker
    from app.nonverbal.video_observations import extract_nonverbal_video_observations

    owns_landmarker = landmarker is None
    landmarker = landmarker or create_face_landmarker()
    tracker = tracker or create_tracker(kalman_enabled=False)
    try:
        observations = extract_nonverbal_video_observations(path, sample_fps=CALIBRATION_SAMPLE_FPS, tracker=tracker, landmarker=landmarker)
    finally:
        if owns_landmarker:
            landmarker.close()
    shared = [item.shared for item in observations]
    valid_faces = [item for item in shared if item.face_valid]
    gaze = [item.gaze for item in observations if item.gaze.valid and item.gaze.unclipped_x is not None and item.gaze.unclipped_y is not None]
    duration_ms = 0.0 if len(gaze) < 2 else float(sum(min(gaze[index + 1].timestamp_ms - gaze[index].timestamp_ms, 150.0) for index in range(len(gaze) - 1)))
    calibrated = apply_affine(np.asarray([[item.unclipped_x, item.unclipped_y] for item in gaze]), np.asarray(metadata.affine_matrix)) if gaze else np.empty((0, 2))
    head = [head_pose_features(item.facial_transformation_matrix) for item in valid_faces if item.facial_transformation_matrix is not None]
    face_ratio = len(valid_faces) / len(shared) if shared else 0.0
    passed = face_ratio >= MIN_FACE_VALID_RATIO and duration_ms >= MIN_CAMERA_VALID_MS and bool(head)
    neutral_head = None
    if head:
        median = np.median(np.asarray(head), axis=0)
        neutral_head = {"neutral_head_yaw": float(median[0]), "neutral_head_pitch": float(median[2]), "neutral_head_roll": float(median[1])}
    return {
        "passed": passed,
        "failure_reason": None if passed else ("face" if face_ratio < MIN_FACE_VALID_RATIO or not head else "camera"),
        "camera_reference_center": np.median(calibrated, axis=0).tolist() if len(calibrated) else None,
        "neutral_head": neutral_head,
        "quality": {"camera_valid_duration_ms": duration_ms, "camera_face_valid_ratio": face_ratio},
    }


def process_voice(path: Path, duration_ms: int) -> dict:
    from app.paraverbal.opensmile_extractor import StudentTurnAudio, analyze_student_turns

    voice = analyze_student_turns(path, [StudentTurnAudio("voice", 0, duration_ms, "Clear communication helps us understand a patient's needs during a clinical consultation.")], min_voiced_duration_ms=3000).get("voice")
    result = {
        "voiced_duration_ms": voice.voiced_duration_ms if voice else 0,
        "clipping_detected": bool(voice and "clipping_detected" in voice.audio_quality.get("issues", [])),
        "baseline_f0_semitones": float(np.median(voice.f0_samples_semitones)) if voice and voice.f0_samples_semitones else None,
        "baseline_loudness": float(np.median(voice.loudness_samples)) if voice and voice.loudness_samples else None,
    }
    result["passed"] = bool(result["voiced_duration_ms"] >= 3000 and not result["clipping_detected"] and result["baseline_f0_semitones"] is not None and result["baseline_loudness"] is not None)
    result["failure_reason"] = None if result["passed"] else ("clipping" if result["clipping_detected"] else "insufficient_audio")
    return result


def main() -> None:
    if len(sys.argv) != 5 or sys.argv[1] not in {"video", "audio", "gaze", "camera", "voice"}:
        raise SystemExit("usage: calibration_worker video|audio|gaze|camera|voice MEDIA METADATA_JSON RESULT_JSON")
    mode = sys.argv[1]
    media_path, metadata_path, result_path = map(Path, sys.argv[2:])
    raw_metadata = metadata_path.read_text(encoding="utf-8")
    if mode in {"video", "audio"}:
        metadata = CalibrationCaptureMetadata.model_validate_json(raw_metadata)
        result = process_video(media_path, metadata) if mode == "video" else process_audio(media_path, metadata)
    elif mode == "gaze":
        result = process_gaze(media_path, GazeCalibrationMetadata.model_validate_json(raw_metadata))
    elif mode == "camera":
        result = process_camera(media_path, CameraCalibrationMetadata.model_validate_json(raw_metadata))
    else:
        result = process_voice(media_path, int(json.loads(raw_metadata)["duration_ms"]))
    result_path.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
