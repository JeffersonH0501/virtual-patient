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
    for line in sys.stdin:
        raw_command = line.strip()
        if not raw_command:
            continue
        command = json.loads(raw_command)
        if command.get("command") == "shutdown":
            return
        request_id = str(command.get("request_id", ""))
        try:
            if command.get("command") == "turn-video":
                status = _process_job(str(command["job_id"]), resources=resources)
                response = {"request_id": request_id, "status": status}
            elif command.get("command") == "calibration-visual":
                from pathlib import Path

                from app.models.calibration import (
                    CameraCalibrationMetadata,
                    GazeCalibrationMetadata,
                )
                from app.nonverbal.calibration_worker import process_camera, process_gaze

                stage = command.get("stage")
                if stage == "gaze":
                    metadata = GazeCalibrationMetadata.model_validate(command["metadata"])
                    tracker = resources.tracker_for(None, kalman_enabled=False)
                    result = process_gaze(
                        Path(command["media_path"]),
                        metadata,
                        tracker=tracker,
                    )
                elif stage == "camera":
                    metadata = CameraCalibrationMetadata.model_validate(command["metadata"])
                    # Camera calibration applies the gaze affine matrix while
                    # assembling its reference center, so inference stays raw.
                    tracker = resources.tracker_for(None, kalman_enabled=False)
                    result = process_camera(
                        Path(command["media_path"]),
                        metadata,
                        tracker=tracker,
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

        asyncio.run(process_multimodal_interview(args.interview_id, args.recording_id))
        return

    if args.job_type == "turn-video-server":
        _run_turn_video_server()
        return

    from app.multimodal.turn_video_queue import _process_job

    _process_job(args.job_id)


if __name__ == "__main__":
    main()
