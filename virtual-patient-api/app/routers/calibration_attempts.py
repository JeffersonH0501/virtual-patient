"""Authenticated lifecycle for durable multimodal calibration attempts."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from time import perf_counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.media.storage import get_media_storage
from app.models.calibration import CalibrationAttemptDB, CalibrationCaptureMetadata, CalibrationMediaAssetDB, CalibrationStatus
from app.models.medical_interview import MedicalInterviewDB
from app.models.user import User

router = APIRouter(prefix="/calibration-attempts", tags=["calibration"])
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
ALLOWED_VIDEO = {"video/webm": ".webm", "video/mp4": ".mp4"}
MAX_CALIBRATION_BYTES = 100 * 1024 * 1024
CALIBRATION_PROCESS_TIMEOUT_SECONDS = 180


class AttemptResponse(BaseModel):
    id: str
    status: str
    failure_reason: str | None
    is_active: bool
    medical_interview_id: int | None
    profile: dict | None
    quality: dict | None


def _response(attempt: CalibrationAttemptDB) -> AttemptResponse:
    return AttemptResponse(id=attempt.id, status=attempt.status, failure_reason=attempt.failure_reason, is_active=attempt.is_active, medical_interview_id=attempt.medical_interview_id, profile=attempt.profile, quality=attempt.quality)


async def _run_isolated_worker(path: Path, metadata: CalibrationCaptureMetadata, mode: str) -> dict:
    """Run native libraries in a child process so an abort cannot kill the API."""
    with tempfile.TemporaryDirectory(prefix="calibration-worker-") as directory:
        metadata_path = Path(directory) / "metadata.json"
        result_path = Path(directory) / f"{mode}-result.json"
        metadata_path.write_text(metadata.model_dump_json(), encoding="utf-8")
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.nonverbal.calibration_worker", mode,
            str(path), str(metadata_path), str(result_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=CALIBRATION_PROCESS_TIMEOUT_SECONDS)
        except TimeoutError:
            process.kill()
            await process.communicate()
            raise RuntimeError("Calibration worker timed out")
        if not result_path.is_file():
            detail = stderr.decode("utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"Calibration worker exited with {process.returncode}: {detail}")
        return json.loads(result_path.read_text(encoding="utf-8"))


async def _run_timed_worker(
    attempt_id: str,
    path: Path,
    metadata: CalibrationCaptureMetadata,
    mode: str,
) -> tuple[dict, float]:
    """Run one calibration branch and emit its end-to-end wall-clock time."""
    started_at = perf_counter()
    try:
        result = await _run_isolated_worker(path, metadata, mode)
    except Exception:
        elapsed = perf_counter() - started_at
        logger.exception(
            "Calibration analysis branch failed attempt_id=%s branch=%s elapsed_seconds=%.3f",
            attempt_id,
            mode,
            elapsed,
        )
        raise
    elapsed = perf_counter() - started_at
    logger.info(
        "Calibration analysis branch completed attempt_id=%s branch=%s elapsed_seconds=%.3f",
        attempt_id,
        mode,
        elapsed,
    )
    return result, elapsed


@router.post("", response_model=AttemptResponse)
def create_attempt(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    # A native worker or disconnected request can leave an attempt in PROCESSING.
    # Starting a replacement attempt makes that interrupted state terminal.
    now = datetime.now(timezone.utc)
    interrupted = db.query(CalibrationAttemptDB).filter(
        CalibrationAttemptDB.user_id == current_user.id,
        CalibrationAttemptDB.status == CalibrationStatus.PROCESSING.value,
        CalibrationAttemptDB.completed_at.is_(None),
    ).all()
    for previous in interrupted:
        previous.status = CalibrationStatus.FAILED.value
        previous.failure_reason = "processing_interrupted"
        previous.completed_at = now
    attempt = CalibrationAttemptDB(user_id=current_user.id, status=CalibrationStatus.NOT_STARTED.value, started_at=datetime.now(timezone.utc), calibration_metadata={})
    db.add(attempt); db.commit(); db.refresh(attempt)
    return _response(attempt)


@router.post("/{attempt_id}/process", response_model=AttemptResponse)
async def process_attempt(
    attempt_id: str,
    video: Annotated[UploadFile, File()],
    duration_ms: Annotated[int, Form(ge=1)],
    metadata_json: Annotated[str, Form()],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    attempt = db.query(CalibrationAttemptDB).filter(CalibrationAttemptDB.id == attempt_id, CalibrationAttemptDB.user_id == current_user.id).first()
    if not attempt or attempt.status != CalibrationStatus.NOT_STARTED.value:
        raise HTTPException(status_code=409, detail="Calibration attempt cannot be processed")
    try:
        metadata = CalibrationCaptureMetadata.model_validate(json.loads(metadata_json))
    except Exception as error:
        raise HTTPException(status_code=422, detail="Invalid calibration metadata") from error
    if metadata.voice_baseline_end_ms > duration_ms + 1000:
        raise HTTPException(status_code=422, detail="Calibration metadata exceeds media duration")
    content_type = (video.content_type or "").split(";", 1)[0].lower()
    extension = ALLOWED_VIDEO.get(content_type)
    if extension is None:
        raise HTTPException(status_code=415, detail="Unsupported calibration media type")
    attempt.status = CalibrationStatus.PROCESSING.value
    attempt.calibration_metadata = metadata.model_dump()
    db.commit()
    storage = get_media_storage()
    stored = await storage.save_calibration_upload(current_user.id, attempt.id, "video", video, extension)
    if stored.size_bytes > MAX_CALIBRATION_BYTES:
        storage.delete(stored.storage_key)
        attempt.status = CalibrationStatus.FAILED.value; attempt.failure_reason = "media_too_large"; attempt.completed_at = datetime.now(timezone.utc); db.commit()
        return _response(attempt)
    if stored.size_bytes <= 0:
        attempt.status = CalibrationStatus.FAILED.value; attempt.failure_reason = "empty_media"; db.commit()
        return _response(attempt)
    asset = CalibrationMediaAssetDB(calibration_attempt_id=attempt.id, kind="video", storage_key=stored.storage_key, content_type=content_type, size_bytes=stored.size_bytes, duration_ms=duration_ms, sha256=stored.sha256, asset_metadata={"contains_audio": True})
    db.add(asset); db.commit()
    path = storage.resolve(stored.storage_key)
    try:
        analysis_started_at = perf_counter()
        video_result, video_seconds = await _run_timed_worker(attempt.id, path, metadata, "video")
        logger.info(
            "Calibration video stage timing attempt_id=%s performance=%s",
            attempt.id,
            json.dumps(video_result.get("performance", {}), sort_keys=True),
        )
        audio_result, audio_seconds = await _run_timed_worker(attempt.id, path, metadata, "audio")
        total_seconds = perf_counter() - analysis_started_at
        logger.info(
            "Calibration analysis timing attempt_id=%s video_seconds=%.3f audio_seconds=%.3f total_seconds=%.3f slowest_branch=%s",
            attempt.id,
            video_seconds,
            audio_seconds,
            total_seconds,
            "video" if video_seconds >= audio_seconds else "audio",
        )
        profile = video_result["profile"]
        quality = video_result["quality"]
        quality["valid_speech_duration_ms"] = audio_result["voiced_duration_ms"]
        quality["clipping_detected"] = audio_result["clipping_detected"]
        audio_passed = (
            audio_result["voiced_duration_ms"] >= 3000
            and not audio_result["clipping_detected"]
            and audio_result["baseline_f0_semitones"] is not None
            and audio_result["baseline_loudness"] is not None
        )
        if video_result["neutral_head"] and audio_passed:
            camera_center = profile.get("camera_reference_center") or [0.0, 0.0]
            profile["personal_baseline"] = {
                **video_result["neutral_head"],
                "baseline_f0_semitones": audio_result["baseline_f0_semitones"],
                "baseline_loudness": audio_result["baseline_loudness"],
                "neutral_gaze_yaw": float(camera_center[0]),
                "neutral_gaze_pitch": float(camera_center[1]),
            }
        passed = bool(video_result["passed"] and audio_passed and profile.get("personal_baseline"))
        attempt.profile = profile; attempt.quality = quality
        attempt.status = CalibrationStatus.PASSED.value if passed else CalibrationStatus.FAILED.value
        attempt.failure_reason = None if passed else (video_result["failure_reason"] or "insufficient_audio")
    except Exception:
        logger.exception("Calibration attempt processing failed", extra={"attempt_id": attempt.id})
        attempt.status = CalibrationStatus.FAILED.value; attempt.failure_reason = "processing_failed"
    attempt.completed_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(attempt)
    return _response(attempt)


@router.post("/{attempt_id}/link/{interview_id}", response_model=AttemptResponse)
def link_attempt(attempt_id: str, interview_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    attempt = db.query(CalibrationAttemptDB).filter(CalibrationAttemptDB.id == attempt_id, CalibrationAttemptDB.user_id == current_user.id).with_for_update().first()
    interview = db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == interview_id, MedicalInterviewDB.user_id == current_user.id).first()
    if not attempt or not interview:
        raise HTTPException(status_code=404, detail="Calibration attempt or interview not found")
    if attempt.status != CalibrationStatus.PASSED.value or (attempt.medical_interview_id not in (None, interview_id)):
        raise HTTPException(status_code=409, detail="Calibration attempt cannot be linked")
    db.query(CalibrationAttemptDB).filter(CalibrationAttemptDB.medical_interview_id == interview_id, CalibrationAttemptDB.is_active.is_(True)).update({"is_active": False})
    attempt.medical_interview_id = interview_id; attempt.is_active = True
    db.commit(); db.refresh(attempt)
    return _response(attempt)
