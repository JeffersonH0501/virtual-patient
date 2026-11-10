"""Process entry points that isolate native multimedia libraries from the API."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

TURN_VIDEO_RESULT_PREFIX = "__TURN_VIDEO_RESULT__ "


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="job_type", required=True)

    pipeline = subparsers.add_parser("pipeline")
    pipeline.add_argument("interview_id", type=int)
    pipeline.add_argument("recording_id")
    pipeline.add_argument("--full-video", action="store_true")

    turn_video = subparsers.add_parser("turn-video")
    turn_video.add_argument("job_id")
    subparsers.add_parser("turn-video-server")
    return parser.parse_args()


def _run_turn_video_server() -> None:
    """Process JSON commands while keeping visual models loaded."""
    from app.multimodal.turn_video_queue import (
        PersistentTurnVideoResources,
        _process_job,
    )

    resources = PersistentTurnVideoResources()
    live_landmarker = None
    for line in sys.stdin:
        raw_command = line.strip()
        if not raw_command:
            continue
        command = json.loads(raw_command)
        if command.get("command") == "shutdown":
            return
        request_id = str(command.get("request_id", ""))
        try:
            if command.get("command") == "warmup":
                response = {"request_id": request_id, "status": "ready"}
            elif command.get("command") == "turn-video":
                status = _process_job(str(command["job_id"]), resources=resources)
                response = {"request_id": request_id, "status": status}
            elif command.get("command") == "calibration-visual":
                from pathlib import Path

                from app.models.calibration import (
                    UnifiedCalibrationMetadata, GuidedOnlyMetadata,
    CameraCalibrationMetadata,
                    GazeCalibrationMetadata,
                )
                from app.nonverbal.calibration_worker import (
                    process_unified,
                    process_camera,
                    process_gaze,
                )

                stage = command.get("stage")
                if stage == "live-gaze":
                    import cv2
                    import mediapipe as mp
                    from app.nonverbal.mediapipe_extractor import create_face_landmarker, observation_from_result
                    from app.nonverbal.mediapipe_calibration import gaze_observation, gaze_screen_state
                    if live_landmarker is None:
                        live_landmarker = create_face_landmarker(image_mode=True)
                    frame = cv2.imread(command["media_path"])
                    if frame is None:
                        raise ValueError("Invalid gaze test frame")
                    profile = command["metadata"]["profile"]
                    geometry = profile["capture_geometry"]
                    if frame.shape[1] != geometry["video_width"] or frame.shape[0] != geometry["video_height"]:
                        result = {"state": "indeterminate"}
                    else:
                        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                        shared = observation_from_result(0, frame, live_landmarker.detect(image))
                        gaze = gaze_observation(shared, profile)
                        result = {"state": gaze_screen_state(gaze)}
                elif stage == "guided":
                    from app.nonverbal.video_observations import extract_nonverbal_video_observations
                    from app.nonverbal.guided_checks import analyze_guided_checks
                    metadata = GuidedOnlyMetadata.model_validate(command["metadata"])
                    stage_durations = {}
                    observations = extract_nonverbal_video_observations(Path(command["media_path"]),
                        stage_durations=stage_durations, calibration_profile=metadata.profile)
                    result = {"passed": True, "guided_checks": analyze_guided_checks(observations,
                        metadata.guided_checks, metadata.profile, camera_result=metadata.camera_result,
                        protocol="guided_checks_v4_orientation", environment=metadata.guided_environment.model_dump(mode="json"),
                        geometry=metadata.geometry.model_dump(mode="json"))}
                    result["guided_checks"]["processing_costs"] = stage_durations
                elif stage == "unified":
                    metadata = UnifiedCalibrationMetadata.model_validate(command["metadata"])
                    result = process_unified(Path(command["media_path"]), metadata)
                elif stage == "gaze":
                    metadata = GazeCalibrationMetadata.model_validate(command["metadata"])
                    result = process_gaze(
                        Path(command["media_path"]),
                        metadata,
                    )
                elif stage == "camera":
                    metadata = CameraCalibrationMetadata.model_validate(command["metadata"])
                    # Camera calibration applies the gaze affine matrix while
                    # assembling its reference center, so inference stays raw.
                    result = process_camera(
                        Path(command["media_path"]),
                        metadata,
                    )
                else:
                    raise ValueError("Unsupported visual calibration stage")
                response = {"request_id": request_id, "result": result}
            else:
                raise ValueError("Unsupported visual worker command")
        except Exception as error:  # noqa: BLE001 - keep the worker available when safe.
            logging.getLogger(__name__).exception(
                "Persistent visual worker command failed request_id=%s", request_id
            )
            response = {"request_id": request_id, "error": str(error)}
        print(TURN_VIDEO_RESULT_PREFIX + json.dumps(response), flush=True)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("app").setLevel(logging.INFO)
    args = _parse_args()
    if args.job_type == "pipeline":
        from app.multimodal.pipeline import process_multimodal_interview

        asyncio.run(process_multimodal_interview(args.interview_id, args.recording_id, use_full_video=args.full_video))
        return

    if args.job_type == "turn-video-server":
        _run_turn_video_server()
        return

    from app.multimodal.turn_video_queue import _process_job

    _process_job(args.job_id)


if __name__ == "__main__":
    main()
