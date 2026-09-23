"""Authenticated temporary multimodal calibration processing.

The active flow processes gaze, camera, and voice as independent checkpoints.
Each upload is analyzed in a crash-isolated worker and deleted immediately. The
client keeps passed checkpoint results in memory, assembles the final draft, and
only persists it when the user starts the simulation. The original combined
endpoint remains available for compatibility with earlier clients.

No ``CalibrationAttemptDB`` or ``CalibrationMediaAssetDB`` row is ever created by
this flow, and the calibration media is never stored permanently (Requirement:
zero calibration DB rows and zero permanent calibration files before the
interview starts).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
import uuid
from time import perf_counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.models.calibration import (
    CalibrationCaptureMetadata,
    CameraCalibrationMetadata,
    GazeCalibrationMetadata,
    VoiceCalibrationMetadata,
)
from app.multimodal.schemas import PersonalBaseline
from app.multimodal.turn_video_queue import enqueue_calibration_visual_analysis
from app.models.user import User
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
CALIBRATION_PROCESS_TIMEOUT_SECONDS = 180

# Versioned identifier for this calibration protocol/result. Persisted with the
# calibration result so a stored baseline is traceable to how it was produced.
CALIBRATION_VERSION = "multimodal_calibration_v1"


class CalibrationProcessResponse(BaseModel):
    """Result of a temporary calibration processing request.

    The client keeps this in memory as a draft. Nothing is persisted server-side
    until the user starts an interview and the draft is saved into
    ``interview_metadata.calibration``.
    """

    status: str  # "passed" | "failed"
    failure_reason: str | None
    calibration_version: str
    profile: dict | None
    quality: dict | None
    personal_baseline: PersonalBaseline | None


class CalibrationStageResponse(BaseModel):
    stage: Literal["gaze", "camera", "voice"]
    status: Literal["passed", "failed"]
    failure_reason: str | None
    result: dict | None


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
    path: Path,
    metadata: CalibrationCaptureMetadata,
    mode: str,
) -> tuple[dict, float]:
    """Run one calibration branch and emit its end-to-end wall-clock time."""
    started_at = perf_counter()
    try:
        if mode in {"gaze", "camera"}:
            future = enqueue_calibration_visual_analysis(
                uuid.uuid4().hex,
                mode,
                path,
                metadata.model_dump(mode="json"),
            )
            result = await asyncio.wrap_future(future)
        else:
            result = await _run_isolated_worker(path, metadata, mode)
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


def _assemble_result(video_result: dict, audio_result: dict) -> tuple[str, str | None, dict, dict, dict | None]:
    """Combine the isolated video/audio worker outputs into a calibration result.

    Returns ``(status, failure_reason, profile, quality, personal_baseline)``.
    The assembly logic is unchanged from the previous durable flow so a valid
    calibration produces a functionally equivalent numeric result.
    """
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
    failure_reason = None if passed else (video_result["failure_reason"] or "insufficient_audio")
    result_status = "passed" if passed else "failed"
    personal_baseline = profile.get("personal_baseline") if passed else None
    return result_status, failure_reason, profile, quality, personal_baseline


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
    finally:
        if not handle.closed:
            handle.close()
        await upload.close()
    return temp_path, total_bytes


def _delete_temp(path: Path | None) -> None:
    """Delete a temporary calibration file, ignoring an already-gone file.

    Calibration media is never persisted; this is always invoked from a
    ``finally`` block so a processing failure still removes the file.
    """
    if path is None:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("calibration_process_event event=temp_delete_failed")


@router.post("/process", response_model=CalibrationProcessResponse)
async def process_calibration(
    video: Annotated[UploadFile, File()],
    duration_ms: Annotated[int, Form(ge=1)],
    metadata_json: Annotated[str, Form()],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Process a calibration clip temporarily and return a result draft.

    No database row and no permanent media asset are created. The upload is
    streamed to a temporary file, analyzed by the crash-isolated video and audio
    workers, and the temporary file is always deleted before returning.
    """
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

    temp_path: Path | None = None
    try:
        temp_path, size_bytes = await _write_upload_to_temp(video, extension)
        if size_bytes <= 0:
            raise HTTPException(status_code=400, detail="Calibration media upload is empty")

        analysis_started_at = perf_counter()
        video_result, video_seconds = await _run_timed_worker(temp_path, metadata, "video")
        logger.info(
            "Calibration video stage timing user_id=%s performance=%s",
            current_user.id,
            json.dumps(video_result.get("performance", {}), sort_keys=True),
        )
        audio_result, audio_seconds = await _run_timed_worker(temp_path, metadata, "audio")
        total_seconds = perf_counter() - analysis_started_at
        logger.info(
            "Calibration analysis timing user_id=%s video_seconds=%.3f audio_seconds=%.3f total_seconds=%.3f slowest_branch=%s",
            current_user.id,
            video_seconds,
            audio_seconds,
            total_seconds,
            "video" if video_seconds >= audio_seconds else "audio",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Calibration processing failed user_id=%s", current_user.id)
        return CalibrationProcessResponse(
            status="failed",
            failure_reason="processing_failed",
            calibration_version=CALIBRATION_VERSION,
            profile=None,
            quality=None,
            personal_baseline=None,
        )
    finally:
        _delete_temp(temp_path)

    result_status, failure_reason, profile, quality, baseline_payload = _assemble_result(
        video_result, audio_result
    )
    personal_baseline = (
        PersonalBaseline.model_validate(baseline_payload) if baseline_payload else None
    )
    return CalibrationProcessResponse(
        status=result_status,
        failure_reason=failure_reason,
        calibration_version=CALIBRATION_VERSION,
        profile=profile,
        quality=quality,
        personal_baseline=personal_baseline,
    )


@router.post("/process-stage", response_model=CalibrationStageResponse)
async def process_calibration_stage(
    stage: Annotated[Literal["gaze", "camera", "voice"], Form()],
    media: Annotated[UploadFile, File()],
    duration_ms: Annotated[int, Form(ge=1)],
    metadata_json: Annotated[str, Form()],
    current_user: User = Depends(get_current_active_user),
):
    """Analyze one temporary calibration checkpoint independently."""
    metadata_types = {
        "gaze": GazeCalibrationMetadata,
        "camera": CameraCalibrationMetadata,
        "voice": VoiceCalibrationMetadata,
    }
    try:
        metadata_payload = json.loads(metadata_json)
        if stage == "voice":
            metadata_payload["duration_ms"] = duration_ms
        metadata = metadata_types[stage].model_validate(metadata_payload)
    except Exception as error:
        raise HTTPException(status_code=422, detail="Invalid calibration stage metadata") from error

    content_type = (media.content_type or "").split(";", 1)[0].lower()
    extension = ALLOWED_VIDEO.get(content_type)
    if extension is None:
        raise HTTPException(status_code=415, detail="Unsupported calibration media type")

    temp_path: Path | None = None
    try:
        temp_path, size_bytes = await _write_upload_to_temp(media, extension)
        if size_bytes <= 0:
            raise HTTPException(status_code=400, detail="Calibration media upload is empty")
        result, elapsed_seconds = await _run_timed_worker(temp_path, metadata, stage)
        safe_quality = {
            key: result.get(key)
            for key in (
                "passed", "failure_reason", "voiced_duration_ms", "clipping_detected"
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
    except Exception:
        logger.exception(
            "performance_event component=calibration operation=checkpoint phase=failed "
            "user_id=%s stage=%s capture_duration_ms=%s parent_rss_mb=%s",
            current_user.id, stage, duration_ms, current_rss_mb(),
        )
        return CalibrationStageResponse(
            stage=stage,
            status="failed",
            failure_reason="processing_failed",
            result=None,
        )
    finally:
        _delete_temp(temp_path)

    passed = bool(result.get("passed"))
    return CalibrationStageResponse(
        stage=stage,
        status="passed" if passed else "failed",
        failure_reason=result.get("failure_reason"),
        result=result,
    )
