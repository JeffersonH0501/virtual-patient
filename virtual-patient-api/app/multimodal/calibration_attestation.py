"""Verify calibration checkpoints produced by the server, not client assertions."""
from datetime import datetime, timedelta, timezone
from math import isfinite
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError
from fastapi import HTTPException
from app.core.config import settings

AUDIENCE = "calibration-checkpoint"


def sign_checkpoint(user_id, interview_id, stage, result, metadata, resume_attempt_id=None):
    return jwt.encode({"sub": str(user_id), "aud": AUDIENCE, "interview_id": interview_id, "stage": stage,
                       "result": result, "metadata": metadata, "resume_attempt_id": resume_attempt_id,
                       "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, settings.secret_key, algorithm="HS256")


def verify_calibration_checkpoints(user_id, interview_id, tokens, resume_attempt_id=None, *, allow_experimental=False):
    try:
        checkpoints = {}
        for stage in ("gaze", "camera"):
            data = jwt.decode(tokens[stage], settings.secret_key, algorithms=["HS256"], audience=AUDIENCE)
            accepted = data["result"].get("passed") is True or allow_experimental and data["result"].get("experimental_quality_bypass") is True
            if data["sub"] != str(user_id) or data["interview_id"] != interview_id or data["stage"] != stage or not accepted:
                raise ValueError("Invalid checkpoint identity or outcome")
            if data["metadata"].get("experimental_quality_bypass") and not allow_experimental:
                raise ValueError("Experimental checkpoints cannot authorize an interview")
            if data.get("resume_attempt_id") != resume_attempt_id:
                raise ValueError("Calibration belongs to a different capture attempt")
            checkpoints[stage] = data
        gaze = checkpoints["gaze"]["result"]
        camera = checkpoints["camera"]["result"]
        profile = dict(gaze["profile"])
        if profile.get("experimental_only") and not allow_experimental:
            raise ValueError("Experimental profiles cannot authorize an interview")
        camera_metadata = checkpoints["camera"]["metadata"]
        source = profile.get("gaze_source")
        if source != "mediapipe_five_point_v1":
            raise ValueError("A supported server-issued gaze calibration is required")
        if source == "mediapipe_five_point_v1" and (profile.get("calibration_target_count") != 5 or not camera.get("camera_eye_reference")
                or checkpoints["gaze"]["metadata"].get("gaze_source") != source):
            raise ValueError("Five-point MediaPipe calibration and lens reference are required")
        if source == "mediapipe_five_point_v1":
            lens = camera["camera_eye_reference"]
            experimental_lens = allow_experimental and camera.get("experimental_quality_bypass") is True
            if (len(lens["center"]) != 2 or not all(isfinite(value) for value in lens["center"])
                    or not isfinite(lens["radius"]) or lens["radius"] <= 0 or lens["radius"] > .04 and not experimental_lens):
                raise ValueError("MediaPipe lens reference is invalid")
        if (camera_metadata["affine_matrix"] != profile["affine_matrix"]
                or camera_metadata.get("gaze_source") != source):
            raise ValueError("Camera and gaze checkpoints do not match")
        if (checkpoints["camera"]["metadata"]["geometry"] != checkpoints["gaze"]["metadata"]["geometry"]
                or checkpoints["camera"]["metadata"]["geometry_stable"] is not True):
            raise ValueError("Camera geometry must match gaze calibration")
        center = camera["camera_reference_center"]
        baseline = {
            **camera["neutral_head"],
            "neutral_gaze_yaw": center[0], "neutral_gaze_pitch": center[1],
        }
        return {
            "status": "passed", "failure_reason": None,
            "version": "multimodal_calibration_attested_v12_mediapipe_five_point",
            "profile": {**profile, "camera_reference_center": center,
                        **({"camera_eye_reference":camera["camera_eye_reference"]} if source == "mediapipe_five_point_v1" else {}),
                        "personal_baseline": baseline, "capture_geometry": checkpoints["gaze"]["metadata"]["geometry"]},
            "quality": {**gaze.get("quality", {}), **camera.get("quality", {})},
            "personal_baseline": baseline,
            "capture_ids": {stage: checkpoint["result"].get("capture_id") for stage, checkpoint in checkpoints.items()},
        }
    except ExpiredSignatureError as error:
        raise HTTPException(status_code=410, detail="Calibration checkpoints have expired") from error
    except (JWTError, KeyError, ValueError, TypeError, IndexError) as error:
        raise HTTPException(status_code=422, detail="Valid server-issued calibration checkpoints are required") from error
