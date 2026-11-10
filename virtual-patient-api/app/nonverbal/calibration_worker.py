"""Visual checkpoint processing in the existing isolated worker."""
from __future__ import annotations
from pathlib import Path
from app.models.calibration import CameraCalibrationMetadata, GazeCalibrationMetadata, UnifiedCalibrationMetadata

CALIBRATION_SAMPLE_FPS = 10.0


def process_gaze(path: Path, metadata: GazeCalibrationMetadata, *, landmarker=None, observations=None) -> dict:
    from app.nonverbal.mediapipe_calibration import build_profile
    from app.nonverbal.video_observations import extract_nonverbal_video_observations

    if observations is None:
        observations = extract_nonverbal_video_observations(
            path, sample_fps=CALIBRATION_SAMPLE_FPS, landmarker=landmarker)
    return build_profile(observations, metadata)


def process_camera(path: Path, metadata: CameraCalibrationMetadata, *, landmarker=None, observations=None) -> dict:
    from app.nonverbal.mediapipe_calibration import build_camera_reference
    from app.nonverbal.video_observations import extract_nonverbal_video_observations

    if observations is None:
        observations = extract_nonverbal_video_observations(
            path, sample_fps=CALIBRATION_SAMPLE_FPS, landmarker=landmarker)
    return build_camera_reference(observations, metadata)


def process_unified(path: Path, metadata: UnifiedCalibrationMetadata) -> dict:
    from app.nonverbal.video_observations import extract_nonverbal_video_observations
    from app.nonverbal.mediapipe_extractor import create_face_landmarker
    landmarker = create_face_landmarker()
    try:
        observations = extract_nonverbal_video_observations(
            path, sample_fps=CALIBRATION_SAMPLE_FPS, landmarker=landmarker)
    finally:
        landmarker.close()
    gaze_end = max(target.presentation_end_ms for target in metadata.targets)
    gaze = process_gaze(path, metadata, observations=[item for item in observations if item.shared.timestamp_ms < gaze_end])
    result = {"gaze": gaze, "passed": False, "failed_stage": "gaze"}
    if not gaze["passed"] and not gaze.get("experimental_quality_bypass"):
        if metadata.guided_checks:
            from app.nonverbal.guided_checks import analyze_guided_checks
            result["guided_checks"] = analyze_guided_checks(observations, metadata.guided_checks, None,
                environment=metadata.guided_environment.model_dump(mode="json"), geometry=metadata.geometry.model_dump(mode="json"),
                protocol=metadata.guided_protocol)
        return result
    profile = gaze["profile"]
    camera_metadata = CameraCalibrationMetadata(affine_matrix=profile["affine_matrix"], geometry=metadata.geometry,
        geometry_stable=metadata.geometry_stable, gaze_source=metadata.gaze_source,
        experimental_quality_bypass=metadata.experimental_quality_bypass)
    try:
        camera = process_camera(path, camera_metadata, observations=[item for item in observations if metadata.camera_reference_start_ms <= item.shared.timestamp_ms < metadata.camera_reference_end_ms])
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Camera reference processing failed after valid gaze calibration")
        camera = {"passed": False, "failure_reason": "processing_failed"}
    passed = gaze["passed"] and camera["passed"]
    experimental = bool((gaze["passed"] or gaze.get("experimental_quality_bypass")) and
        (camera["passed"] or camera.get("experimental_quality_bypass")) and not passed)
    result.update(camera=camera,camera_metadata=camera_metadata.model_dump(mode="json"),passed=passed,
        failed_stage=None if passed else "camera" if not (camera["passed"] or camera.get("experimental_quality_bypass")) else "gaze" if not gaze["passed"] else "camera",
        quality_failed_stage=None if passed else "gaze" if not gaze["passed"] else "camera",experimental_quality_bypass=experimental)
    if metadata.guided_checks:
        from app.nonverbal.guided_checks import analyze_guided_checks
        diagnostic_profile = dict(profile)
        if camera["passed"] or camera.get("experimental_quality_bypass"):
            diagnostic_profile["camera_reference_center"] = camera.get("camera_reference_center")
            if camera.get("camera_eye_reference"):
                diagnostic_profile["camera_eye_reference"] = camera["camera_eye_reference"]
        result["guided_checks"] = analyze_guided_checks(observations, metadata.guided_checks, diagnostic_profile,
            environment=metadata.guided_environment.model_dump(mode="json"), geometry=metadata.geometry.model_dump(mode="json"),
            protocol=metadata.guided_protocol, camera_result=camera)
    return result
