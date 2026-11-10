"""Authenticated calibration processing with private interview references."""

from __future__ import annotations

import json
import os
import logging
import tempfile
from time import perf_counter
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.media.calibration import preserve_capture, discard_capture_references, require_pending_resume
from app.media.storage import get_media_storage
from app.models.calibration_capture import CalibrationCaptureDB
from app.models.medical_interview import MedicalInterviewDB
from app.controllers.interview_lifecycle import lock_row

from app.core.auth import get_current_active_user
from app.models.calibration import (
    UnifiedCalibrationMetadata, GuidedOnlyMetadata,
    CameraCalibrationMetadata,
    GazeCalibrationMetadata, LiveGazeMetadata,
)
from app.multimodal.video_processing_client import (
    process_calibration_video,
    warmup_video_processing_worker,
)
from app.models.user import User, UserRole
from app.utils.runtime_metrics import current_rss_mb, process_id

router = APIRouter(prefix="/calibration", tags=["calibration"])
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Container formats accepted for the combined calibration clip, mapped to a safe
# temp-file suffix. The browser records one WebM carrying both tracks.
ALLOWED_VIDEO = {"video/webm": ".webm", "video/mp4": ".mp4"}
# Provisional cap on a single calibration upload. Calibration is a short clip;
# this bound protects the temp filesystem from an oversized upload. It is not a
# clinical or methodology parameter.
MAX_CALIBRATION_BYTES = 100 * 1024 * 1024  # 100 MiB
CALIBRATION_UPLOAD_CHUNK_BYTES = 1024 * 1024  # 1 MiB


@router.get("/tests")
def list_calibration_tests(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """List the authenticated superuser's retained test references."""
    if current_user.role != UserRole.SUPERUSER:
        raise HTTPException(403, "Calibration tests are only available to superusers")
    rows = db.query(MedicalInterviewDB.id, MedicalInterviewDB.created_at,
        func.count(CalibrationCaptureDB.id).label("capture_count")).join(
        CalibrationCaptureDB, CalibrationCaptureDB.medical_interview_id == MedicalInterviewDB.id).filter(
        MedicalInterviewDB.user_id == current_user.id,
        MedicalInterviewDB.interview_metadata["calibration_test"].as_boolean().is_(True),
    ).group_by(MedicalInterviewDB.id, MedicalInterviewDB.created_at).order_by(MedicalInterviewDB.created_at.desc()).all()
    return {"tests": [{"interview_id": row.id, "created_at": row.created_at, "capture_count": row.capture_count} for row in rows]}

@router.delete("/drafts/{interview_id}", status_code=204)
def discard_calibration_draft(interview_id: int, current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)):
    """Erase calibration references while preserving the owned interview record."""
    interview = lock_row(db, MedicalInterviewDB, interview_id)
    if interview is None or interview.user_id != current_user.id:
        raise HTTPException(404, "Interview not found")
    if interview.start_time is not None or interview.recording is not None or interview.messages:
        raise HTTPException(409, "A started interview cannot be discarded as calibration")
    discard_capture_references(db, interview)
    return None

@router.post("/warm-up")
async def warm_up_visual_worker(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict[str, str]:
    """Begin loading the shared visual models when calibration starts."""
    try:
        await warmup_video_processing_worker()
    except Exception as error:  # noqa: BLE001 - return a controlled service failure.
        logger.warning(
            "Calibration visual warmup failed user_id=%s error_type=%s",
            current_user.id,
            type(error).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Visual calibration service is unavailable",
        ) from error
    return {"status": "ready"}


class CalibrationStageResponse(BaseModel):
    stage: Literal["gaze", "camera", "unified", "guided"]
    status: Literal["passed", "failed"]
    failure_reason: str | None
    result: dict | None
    attestation: str | None = None


async def _run_timed_worker(
    path: Path,
    metadata: CameraCalibrationMetadata | GazeCalibrationMetadata | GuidedOnlyMetadata,
    mode: str,
) -> tuple[dict, float]:
    """Run one calibration branch and emit its end-to-end wall-clock time."""
    started_at = perf_counter()
    try:
        result = await process_calibration_video(path, metadata, mode)
    except Exception:
        elapsed = perf_counter() - started_at
        logger.exception(
            "Calibration analysis branch failed branch=%s elapsed_seconds=%.3f",
            mode,
            elapsed,
        )
        raise
    elapsed = perf_counter() - started_at
    logger.info(
        "Calibration analysis branch completed branch=%s elapsed_seconds=%.3f",
        mode,
        elapsed,
    )
    return result, elapsed


async def _write_upload_to_temp(upload: UploadFile, extension: str) -> tuple[Path, int]:
    """Stream a calibration upload to a temporary file, capping the bytes read.

    Returns the temp path and the number of bytes written. The caller owns
    deleting the returned path (always, in a ``finally`` block). Raises 413 when
    the upload exceeds the maximum allowed size.
    """
    handle = tempfile.NamedTemporaryFile(
        delete=False, prefix="virtual-patient-calibration-", suffix=extension
    )
    temp_path = Path(handle.name)
    total_bytes = 0
    try:
        await upload.seek(0)
        while True:
            chunk = await upload.read(CALIBRATION_UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_CALIBRATION_BYTES:
                raise HTTPException(status_code=413, detail="Calibration media exceeds the maximum allowed size")
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())
    except BaseException:
        handle.close()
        temp_path.unlink(missing_ok=True)
        raise
    finally:
        if not handle.closed:
            handle.close()
        await upload.close()
    return temp_path, total_bytes


def _delete_temp(path: Path | None) -> None:
    """Delete a temporary calibration file, ignoring an already-gone file.

    The private reference copy is independent of this worker input.
    """
    if path is None:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("calibration_process_event event=temp_delete_failed")


@router.post("/gaze-test/frame")
async def process_gaze_test_frame(
    media: Annotated[UploadFile, File()],
    attestations_json: Annotated[str, Form()],
    geometry_json: Annotated[str, Form()],
    attempt_id: Annotated[str, Form(min_length=36, max_length=36)],
    current_user: User = Depends(get_current_active_user),
):
    """Evaluate one temporary frame using this user's signed test calibration."""
    if current_user.role != UserRole.SUPERUSER:
        raise HTTPException(403, "Gaze tests are only available to superusers")
    from app.multimodal.calibration_attestation import verify_calibration_checkpoints
    try:
        attestations = json.loads(attestations_json)
        geometry = json.loads(geometry_json)
    except (TypeError, ValueError) as error:
        raise HTTPException(422, "Invalid gaze test metadata") from error
    verified = verify_calibration_checkpoints(current_user.id, 0, attestations, attempt_id)
    if geometry != verified["profile"]["capture_geometry"]:
        raise HTTPException(409, "Capture geometry changed; recalibration is required")
    if media.content_type != "image/jpeg":
        raise HTTPException(415, "A JPEG frame is required")
    try:
        content = await media.read(2 * 1024 * 1024 + 1)
    finally:
        await media.close()
    if not content or len(content) > 2 * 1024 * 1024:
        raise HTTPException(413, "Invalid gaze test frame size")
    path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, prefix="virtual-patient-gaze-", suffix=".jpg") as handle:
            path = Path(handle.name)
            handle.write(content)
        result = await process_calibration_video(path, LiveGazeMetadata(profile=verified["profile"]), "live-gaze")
        return {"state": result.get("state") if result.get("state") in {"inside", "outside"} else "indeterminate"}
    except Exception as error:
        logger.exception("Live gaze processing failed")
        raise HTTPException(503, "Gaze test processing failed") from error
    finally:
        _delete_temp(path)


@router.post("/nonverbal-test", response_model=CalibrationStageResponse)
async def process_nonverbal_test(
    stage: Annotated[Literal["unified", "camera", "guided"], Form()],
    media: Annotated[UploadFile, File()],
    duration_ms: Annotated[int, Form(ge=1)],
    metadata_json: Annotated[str, Form()],
    attempt_id: Annotated[str, Form(min_length=36, max_length=36)],
    current_user: User = Depends(get_current_active_user),
):
    """Analyze a superuser's temporary capture without an interview or retained media."""
    if current_user.role != UserRole.SUPERUSER:
        raise HTTPException(403, "Nonverbal tests are only available to superusers")
    from jose import jwt, JWTError
    from app.core.config import settings
    from app.multimodal.calibration_attestation import AUDIENCE, sign_checkpoint, verify_calibration_checkpoints

    try:
        payload = json.loads(metadata_json)
        metadata_type = {"unified": UnifiedCalibrationMetadata, "camera": CameraCalibrationMetadata,
                         "guided": GuidedOnlyMetadata}[stage]
        metadata = metadata_type.model_validate(payload)
        if stage == "unified" and metadata.camera_reference_end_ms > duration_ms:
            raise ValueError("Camera interval exceeds captured duration")
        if stage == "guided":
            if metadata.guided_checks[-1].end_ms > duration_ms:
                raise ValueError("Guided checks exceed captured duration")
            from app.models.calibration import NONVERBAL_CHECK_KINDS
            if tuple(item.kind for item in metadata.guided_checks) == NONVERBAL_CHECK_KINDS:
                metadata.profile = {}
                metadata.camera_result = {}
            else:
                verified = verify_calibration_checkpoints(current_user.id, 0, metadata.attestations, attempt_id)
                if verified["profile"]["capture_geometry"] != metadata.geometry.model_dump(mode="json"):
                    raise ValueError("Capture geometry changed")
                camera = jwt.decode(metadata.attestations["camera"], settings.secret_key,
                                    algorithms=["HS256"], audience=AUDIENCE)
                metadata.profile = verified["profile"]
                metadata.camera_result = camera["result"]
            metadata.attestations = {}
        elif stage == "camera":
            gaze = jwt.decode(payload["attestations"]["gaze"], settings.secret_key,
                              algorithms=["HS256"], audience=AUDIENCE)
            if (gaze["sub"] != str(current_user.id) or gaze["interview_id"] != 0
                    or gaze["stage"] != "gaze" or gaze.get("resume_attempt_id") != attempt_id
                    or gaze["result"].get("passed") is not True
                    or gaze["result"]["profile"]["affine_matrix"] != metadata.affine_matrix
                    or gaze["metadata"]["geometry"] != metadata.geometry.model_dump(mode="json")):
                raise ValueError("Camera checkpoint does not match gaze calibration")
        if hasattr(metadata, "experimental_quality_bypass"):
            metadata.experimental_quality_bypass = False
    except (ValueError, TypeError, KeyError, IndexError, JWTError) as error:
        raise HTTPException(422, "Invalid nonverbal test metadata") from error

    extension = ALLOWED_VIDEO.get((media.content_type or "").split(";", 1)[0].lower())
    if extension is None:
        raise HTTPException(415, "Unsupported calibration media type")
    path = None
    try:
        path, size = await _write_upload_to_temp(media, extension)
        if not size:
            raise HTTPException(400, "Calibration media upload is empty")
        result, elapsed = await _run_timed_worker(path, metadata, stage)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Nonverbal test processing failed")
        raise HTTPException(503, "Nonverbal test processing failed") from error
    finally:
        _delete_temp(path)
    if stage == "guided":
        if isinstance(result.get("guided_checks"), dict):
            result["guided_checks"]["processing_time_seconds"] = elapsed
        return CalibrationStageResponse(stage=stage, status="passed" if result.get("passed") else "failed",
                                        failure_reason=result.get("failure_reason"), result=result)
    if stage == "unified":
        checkpoints = {}
        for name in ("gaze", "camera"):
            outcome = result.get(name)
            if outcome is None:
                continue
            data = metadata.model_dump(mode="json") if name == "gaze" else result["camera_metadata"]
            passed = outcome.get("passed") is True
            checkpoints[name] = {"stage": name, "status": "passed" if passed else "failed",
                "failure_reason": outcome.get("failure_reason"), "result": outcome,
                "attestation": sign_checkpoint(current_user.id, 0, name, outcome, data, attempt_id) if passed else None}
        failed = result.get("failed_stage")
        return CalibrationStageResponse(stage=stage, status="passed" if result.get("passed") else "failed",
            failure_reason=(result.get(failed) or {}).get("failure_reason") if failed else None,
            result={"checkpoints": checkpoints, "failed_stage": failed, "processing_time_seconds": elapsed})
    passed = result.get("passed") is True
    return CalibrationStageResponse(stage=stage, status="passed" if passed else "failed",
        failure_reason=result.get("failure_reason"), result=result,
        attestation=sign_checkpoint(current_user.id, 0, stage, result, metadata.model_dump(mode="json"), attempt_id) if passed else None)


@router.delete("/resume/{interview_id}/{attempt_id}", status_code=204)
def discard_resume_calibration(
    interview_id: int,
    attempt_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    interview = lock_row(db, MedicalInterviewDB, interview_id)
    if interview is None or interview.user_id != current_user.id:
        raise HTTPException(404, "Interview not found")
    recording, _ = require_pending_resume(db, interview, attempt_id)
    recording.capture_config = {key: value for key, value in recording.capture_config.items()
                                if key != "resume_attempt"}
    captures = db.query(CalibrationCaptureDB).filter(
        CalibrationCaptureDB.medical_interview_id == interview_id,
        CalibrationCaptureDB.capture_metadata["resume_attempt_id"].as_string() == attempt_id,
    ).all()
    keys = [capture.storage_key for capture in captures]
    for capture in captures:
        db.delete(capture)
    db.commit()
    for key in keys:
        try:
            get_media_storage().delete(key)
        except (OSError, ValueError):
            logger.warning("calibration_process_event event=resume_capture_delete_deferred")


@router.post("/process-stage", response_model=CalibrationStageResponse)
async def process_calibration_stage(
    stage: Annotated[Literal["gaze", "camera", "unified", "guided"], Form()],
    interview_id: Annotated[int, Form(ge=1)],
    media: Annotated[UploadFile, File()],
    duration_ms: Annotated[int, Form(ge=1)],
    metadata_json: Annotated[str, Form()],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    resume_attempt_id: Annotated[str | None, Form()] = None,
):
    """Preserve an owned capture, then analyze or reuse its recorded outcome."""
    metadata_types = {
        "unified": UnifiedCalibrationMetadata, "guided": GuidedOnlyMetadata,
        "gaze": GazeCalibrationMetadata,
        "camera": CameraCalibrationMetadata,
    }
    try:
        metadata_payload = json.loads(metadata_json)
        metadata = metadata_types[stage].model_validate(metadata_payload)
        if stage == "unified" and metadata.camera_reference_end_ms > duration_ms:
            raise ValueError("Camera interval exceeds captured duration")
        if stage == "unified" and metadata.guided_checks and metadata.guided_checks[-1].end_ms > duration_ms:
            raise ValueError("Guided checks exceed captured duration")
    except Exception as error:
        raise HTTPException(status_code=422, detail="Invalid calibration stage metadata") from error

    content_type = (media.content_type or "").split(";", 1)[0].lower()
    if hasattr(metadata, "experimental_quality_bypass"):
        experiment = db.get(MedicalInterviewDB, interview_id)
        metadata.experimental_quality_bypass = bool(current_user.role == UserRole.SUPERUSER and resume_attempt_id is None
            and experiment is not None and experiment.user_id == current_user.id and experiment.start_time is None
            and (experiment.interview_metadata or {}).get("calibration_test") is True)
    if stage == "guided":
        from app.multimodal.calibration_attestation import verify_calibration_checkpoints
        if current_user.role != UserRole.SUPERUSER:
            raise HTTPException(403, "Guided checks are only available to superusers")
        interview = db.get(MedicalInterviewDB, interview_id)
        if interview is None or interview.user_id != current_user.id or not (interview.interview_metadata or {}).get("calibration_test"):
            raise HTTPException(404, "Calibration test not found")
        verified = verify_calibration_checkpoints(current_user.id, interview_id, metadata.attestations, resume_attempt_id, allow_experimental=True)
        if verified["profile"]["capture_geometry"] != metadata.geometry.model_dump(mode="json"):
            raise HTTPException(422, "Repeat calibration after changing capture geometry")
        if metadata.guided_checks[-1].end_ms > duration_ms:
            raise HTTPException(422, "Guided checks exceed captured duration")
        camera_capture = db.get(CalibrationCaptureDB, verified["capture_ids"]["camera"])
        if camera_capture is None or camera_capture.medical_interview_id != interview_id:
            raise HTTPException(422, "Camera reference is no longer available")
        metadata.profile = verified["profile"]
        metadata.camera_result = (camera_capture.result or {}).get("camera", camera_capture.result)
        metadata.attestations = {}
    extension = ALLOWED_VIDEO.get(content_type)
    if extension is None:
        raise HTTPException(status_code=415, detail="Unsupported calibration media type")

    temp_path: Path | None = None
    capture = None
    try:
        temp_path, size_bytes = await _write_upload_to_temp(media, extension)
        if size_bytes <= 0:
            raise HTTPException(status_code=400, detail="Calibration media upload is empty")
        capture_metadata = metadata.model_dump(mode="json")
        for optional_field in ("guided_checks", "guided_environment", "guided_protocol"):
            if optional_field not in metadata_payload:
                capture_metadata.pop(optional_field, None)
        capture = await preserve_capture(db, current_user.id, interview_id, stage, temp_path,
            content_type, duration_ms, capture_metadata, resume_attempt_id)
        if capture.result is not None and capture.result.get("failure_reason") != "processing_failed":
            result, elapsed_seconds = capture.result, 0.0
        else:
            processing_started_at = perf_counter()
            try:
                result, elapsed_seconds = await _run_timed_worker(temp_path, metadata, stage)
            except Exception:
                result, elapsed_seconds = {"passed": False, "failure_reason": "processing_failed"}, perf_counter() - processing_started_at
            result["processing_time_seconds"] = elapsed_seconds
            if isinstance(result.get("guided_checks"), dict):
                result["guided_checks"]["processing_time_seconds"] = elapsed_seconds
            result["capture_id"] = capture.id
            if stage == "unified":
                for checkpoint in ("gaze", "camera"):
                    if isinstance(result.get(checkpoint), dict):
                        result[checkpoint]["capture_id"] = capture.id
            # Refresh under a row lock so expiry/deletion cannot be overwritten.
            from app.controllers.interview_lifecycle import lock_row
            capture = lock_row(db, CalibrationCaptureDB, capture.id)
            if capture is None:
                raise HTTPException(409, "Calibration reference was deleted")
            capture.result = result
            db.commit()
        safe_quality = {
            key: result.get(key)
            for key in (
                "passed", "failure_reason"
            )
            if key in result
        }
        nested_quality = result.get("quality")
        if isinstance(nested_quality, dict):
            safe_quality.update({
                key: nested_quality.get(key)
                for key in (
                    "valid_sample_count", "valid_face_ratio", "camera_valid_duration_ms",
                    "camera_face_valid_ratio", "geometry_stable",
                )
                if key in nested_quality
            })
        logger.info(
            "performance_event component=calibration operation=checkpoint phase=complete "
            "user_id=%s stage=%s capture_duration_ms=%s upload_bytes=%s duration_ms=%.3f "
            "api_pid=%s api_rss_mb=%s outcome=%s",
            current_user.id,
            stage,
            duration_ms,
            size_bytes,
            elapsed_seconds * 1000,
            process_id(),
            current_rss_mb(),
            json.dumps(safe_quality, sort_keys=True),
        )
    except HTTPException:
        raise
    except Exception as error:
        db.rollback()
        logger.exception(
            "performance_event component=calibration operation=checkpoint phase=failed "
            "user_id=%s stage=%s capture_duration_ms=%s parent_rss_mb=%s",
            current_user.id, stage, duration_ms, current_rss_mb(),
        )
        raise HTTPException(503, "Calibration could not be saved; retry the original upload") from error
    finally:
        _delete_temp(temp_path)

    passed = bool(result.get("passed"))
    experimental_allowed = getattr(metadata,"experimental_quality_bypass",False)
    accepted = passed or experimental_allowed and result.get("experimental_quality_bypass") is True
    if result.get("failure_reason") == "processing_failed":
        return CalibrationStageResponse(stage=stage, status="failed", failure_reason="processing_failed", result=result)
    from app.multimodal.calibration_attestation import sign_checkpoint
    if stage == "guided":
        return CalibrationStageResponse(stage=stage, status="passed" if passed else "failed",
            failure_reason=result.get("failure_reason"), result=result)
    if stage == "unified":
        if not passed:
            failed_stage = result.get("failed_stage")
            failed_result = result.get(failed_stage, {})
            logger.warning(
                "calibration_rejected stage=%s reason=%s quality=%s",
                failed_stage, failed_result.get("failure_reason"),
                json.dumps(failed_result.get("quality", {}), sort_keys=True),
            )
        checkpoints = {}
        for checkpoint in ("gaze", "camera"):
            outcome = result.get(checkpoint)
            if outcome is None:
                continue
            checkpoint_metadata = metadata.model_dump(mode="json") if checkpoint == "gaze" else result["camera_metadata"]
            checkpoints[checkpoint] = {
                "stage": checkpoint, "status": "passed" if outcome["passed"] or experimental_allowed and outcome.get("experimental_quality_bypass") else "failed",
                "failure_reason": outcome.get("failure_reason"), "result": outcome,
                "attestation": sign_checkpoint(current_user.id, interview_id, checkpoint, outcome, checkpoint_metadata, resume_attempt_id) if outcome["passed"] or experimental_allowed and outcome.get("experimental_quality_bypass") else None,
            }
        return CalibrationStageResponse(stage=stage, status="passed" if accepted else "failed",
            failure_reason=result.get(result.get("failed_stage"), {}).get("failure_reason") if not passed else None,
            result={"checkpoints": checkpoints, "failed_stage": result.get("failed_stage"),
                    "experimental_quality_bypass": result.get("experimental_quality_bypass", False),
                    "processing_time_seconds": result.get("processing_time_seconds"),
                    **({"guided_checks": result["guided_checks"]} if "guided_checks" in result else {})})

    return CalibrationStageResponse(
        stage=stage,
        status="passed" if accepted else "failed",
        failure_reason=result.get("failure_reason"),
        result=result,
        attestation=sign_checkpoint(current_user.id, interview_id, stage, result, metadata.model_dump(mode="json"), resume_attempt_id) if accepted else None,
    )
