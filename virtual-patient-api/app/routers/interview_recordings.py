"""Authenticated capture, storage, and replay of synchronized interview media."""

from __future__ import annotations

import json
import logging
import mimetypes
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Dict, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_from_token
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.media import LocalMediaStorage, get_media_storage
from app.models.medical_interview import (
    InterviewMediaAssetDB,
    InterviewRecapResponse,
    InterviewRecordingDB,
    InterviewTurnDB,
    MediaAssetKind,
    MedicalInterviewDB,
    RecapTurn,
    RecordingStartRequest,
    RecordingStateResponse,
    RecordingStatus,
    RecordingUnavailableRequest,
    SenderType,
    TurnUpsertRequest,
)
from app.models.medical_interview.interview_message import InterviewMessageDB
from app.models.user import UserDB, UserRole
from app.paraverbal import StudentTurnAudio, analyze_student_turns
from app.nonverbal import StudentTurnVideo, analyze_student_turn_videos
from app.nonverbal.pyfeat_extractor import analyze_pyfeat_student_turn_videos


router = APIRouter(prefix="/medical-interviews", tags=["interview-recordings"])
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ALLOWED_CONTENT_TYPES = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "video/webm": ".webm",
    "video/mp4": ".mp4",
}
RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")
KNOWN_FAILURE_CODES = {
    "browser-capture-unsupported",
    "recording-codec-unsupported",
    "capture-start-failed",
    "recording-upload-failed",
    "temporary-storage-failed",
    "media-recorder-failed",
}


def _current_media_user(
    authorization: Annotated[Optional[str], Header()] = None,
    access_token: Annotated[Optional[str], Cookie()] = None,
    db: Session = Depends(get_db),
) -> UserDB:
    token = access_token
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user = get_current_user_from_token(token, db)
    if user is None or user.disabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return user


def _get_interview(db: Session, interview_id: int) -> MedicalInterviewDB:
    interview = db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == interview_id).first()
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return interview


def _require_owner(interview: MedicalInterviewDB, user: UserDB) -> None:
    if interview.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the interview owner can modify its recording")


def _require_replay_access(interview: MedicalInterviewDB, user: UserDB) -> None:
    if interview.user_id == user.id or user.role == UserRole.SUPERUSER:
        return
    owner_organization_id = interview.user.organization_id if interview.user else None
    if user.role == UserRole.TEACHER and user.organization_id == owner_organization_id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recording access denied")


def _recording_response(recording: InterviewRecordingDB) -> RecordingStateResponse:
    return RecordingStateResponse(
        interview_id=recording.medical_interview_id,
        recording_id=recording.id,
        recording_status=RecordingStatus(recording.status),
        duration_ms=recording.duration_ms,
    )


@router.post("/{interview_id}/recording/start", response_model=RecordingStateResponse)
def start_recording(
    interview_id: int,
    payload: RecordingStartRequest,
    user: UserDB = Depends(_current_media_user),
    db: Session = Depends(get_db),
):
    interview = _get_interview(db, interview_id)
    _require_owner(interview, user)
    if getattr(interview.status, "value", interview.status) != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only active interviews can start recording")

    recording = db.query(InterviewRecordingDB).filter(
        InterviewRecordingDB.medical_interview_id == interview_id
    ).first()
    if recording is None:
        retention_expires_at = None
        if settings.media_retention_days is not None:
            retention_expires_at = payload.started_at + timedelta(days=settings.media_retention_days)
        recording = InterviewRecordingDB(
            medical_interview_id=interview_id,
            status=RecordingStatus.RECORDING.value,
            started_at=payload.started_at,
            capture_config=payload.capture_config,
            consent_basis="institutional",
            consent_policy_version=settings.media_consent_policy_version,
            retention_expires_at=retention_expires_at,
        )
        db.add(recording)
        db.commit()
        db.refresh(recording)
        logger.info(
            "recording_storage_event interview_id=%s recording_id=%s event=started",
            interview_id,
            recording.id,
        )
    return _recording_response(recording)


@router.put("/{interview_id}/recording/turns/{message_id}", response_model=RecapTurn)
def upsert_turn(
    interview_id: int,
    message_id: int,
    payload: TurnUpsertRequest,
    user: UserDB = Depends(_current_media_user),
    db: Session = Depends(get_db),
):
    interview = _get_interview(db, interview_id)
    _require_owner(interview, user)
    message = db.query(InterviewMessageDB).filter(
        InterviewMessageDB.id == message_id,
        InterviewMessageDB.interview_id == interview_id,
    ).first()
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview message not found")
    expected_speaker = (
        "student"
        if getattr(message.sender_type, "value", message.sender_type) == SenderType.USER.value
        else "patient"
    )
    if payload.speaker != expected_speaker:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Turn speaker does not match the interview message",
        )
    if payload.end_ms < payload.start_ms:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Turn end must not precede its start")

    turn = db.query(InterviewTurnDB).filter(
        InterviewTurnDB.medical_interview_id == interview_id,
        InterviewTurnDB.message_id == message_id,
    ).first()
    values = payload.model_dump()
    if turn is None:
        turn = InterviewTurnDB(
            medical_interview_id=interview_id,
            message_id=message_id,
            **values,
        )
        db.add(turn)
    else:
        for key, value in values.items():
            setattr(turn, key, value)
    db.commit()
    db.refresh(turn)
    return _turn_response(turn)


@router.post("/{interview_id}/recording/finalize", response_model=RecordingStateResponse)
async def finalize_recording(
    interview_id: int,
    background_tasks: BackgroundTasks,
    duration_ms: Annotated[int, Form(ge=0)],
    source_durations: Annotated[str, Form()],
    capture_config: Annotated[str, Form()] = "{}",
    student_audio: Annotated[Optional[UploadFile], File()] = None,
    student_video: Annotated[Optional[UploadFile], File()] = None,
    patient_audio: Annotated[Optional[UploadFile], File()] = None,
    patient_video: Annotated[Optional[UploadFile], File()] = None,
    user: UserDB = Depends(_current_media_user),
    db: Session = Depends(get_db),
    storage: LocalMediaStorage = Depends(get_media_storage),
):
    interview = _get_interview(db, interview_id)
    _require_owner(interview, user)
    recording = db.query(InterviewRecordingDB).filter(
        InterviewRecordingDB.medical_interview_id == interview_id
    ).first()
    if recording is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Recording has not been started")

    try:
        durations: Dict[str, int] = json.loads(source_durations)
        parsed_capture_config = json.loads(capture_config)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid recording metadata") from error
    if not isinstance(durations, dict) or not isinstance(parsed_capture_config, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Recording metadata must be JSON objects",
        )

    uploads = {
        MediaAssetKind.STUDENT_AUDIO.value: student_audio,
        MediaAssetKind.STUDENT_VIDEO.value: student_video,
        MediaAssetKind.PATIENT_AUDIO.value: patient_audio,
        MediaAssetKind.PATIENT_VIDEO.value: patient_video,
    }
    logger.info(
        "recording_storage_event interview_id=%s recording_id=%s event=finalize_requested "
        "duration_ms=%s asset_kinds=%s",
        interview_id,
        recording.id,
        duration_ms,
        sorted(kind for kind, upload in uploads.items() if upload is not None),
    )
    validated_durations = _validate_source_durations(durations, uploads, duration_ms)
    latest_turn = db.query(InterviewTurnDB).filter(
        InterviewTurnDB.medical_interview_id == interview_id
    ).order_by(InterviewTurnDB.end_ms.desc()).first()
    if latest_turn and latest_turn.end_ms > duration_ms + settings.media_duration_tolerance_ms:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A turn extends beyond the common recording timeline",
        )
    saved_keys: list[str] = []
    recording.status = RecordingStatus.FINALIZING.value
    db.commit()
    try:
        for kind, upload in uploads.items():
            if upload is None:
                continue
            source_duration = validated_durations[kind]
            content_type = (upload.content_type or "").split(";", 1)[0].lower()
            extension = ALLOWED_CONTENT_TYPES.get(content_type)
            if extension is None:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Unsupported media type for {kind}",
                )
            stored = await storage.save_upload(
                interview_id,
                recording.id,
                kind,
                upload,
                extension,
            )
            saved_keys.append(stored.storage_key)
            if stored.size_bytes == 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{kind} is empty",
                )
            asset = db.query(InterviewMediaAssetDB).filter(
                InterviewMediaAssetDB.recording_id == recording.id,
                InterviewMediaAssetDB.kind == kind,
            ).first()
            if asset is None:
                asset = InterviewMediaAssetDB(recording_id=recording.id, kind=kind)
                db.add(asset)
            asset.storage_key = stored.storage_key
            asset.content_type = content_type
            asset.size_bytes = stored.size_bytes
            asset.duration_ms = source_duration
            asset.sha256 = stored.sha256
            asset.status = "ready"
            logger.info(
                "recording_storage_event interview_id=%s recording_id=%s event=asset_saved "
                "kind=%s size_bytes=%s duration_ms=%s content_type=%s",
                interview_id,
                recording.id,
                kind,
                stored.size_bytes,
                source_duration,
                content_type,
            )

        available_count = sum(1 for upload in uploads.values() if upload is not None)
        recording.duration_ms = duration_ms
        recording.ended_at = datetime.now(timezone.utc)
        recording.capture_config = parsed_capture_config
        recording.failure_code = None
        recording.status = _status_for_asset_count(available_count).value
        if available_count == 0:
            recording.failure_code = "no-media-files"
        db.commit()
        db.refresh(recording)
        response = _recording_response(recording)
        logger.info(
            "recording_storage_event interview_id=%s recording_id=%s event=finalized "
            "status=%s asset_count=%s duration_ms=%s",
            interview_id,
            recording.id,
            recording.status,
            available_count,
            duration_ms,
        )
        background_tasks.add_task(
            _process_recording_observations,
            interview_id,
            recording.id,
        )
        return response
    except HTTPException as error:
        logger.warning(
            "recording_storage_event interview_id=%s recording_id=%s event=validation_failed "
            "status_code=%s detail=%s",
            interview_id,
            recording.id,
            error.status_code,
            error.detail,
        )
        db.rollback()
        for storage_key in saved_keys:
            storage.delete(storage_key)
        recording = db.query(InterviewRecordingDB).filter(InterviewRecordingDB.id == recording.id).first()
        if recording:
            recording.status = RecordingStatus.FAILED.value
            recording.failure_code = "media-validation-failed"
            db.commit()
        raise
    except Exception as error:
        logger.exception(
            "recording_storage_event interview_id=%s recording_id=%s event=storage_failed "
            "error_type=%s",
            interview_id,
            recording.id,
            type(error).__name__,
        )
        db.rollback()
        for storage_key in saved_keys:
            storage.delete(storage_key)
        recording = db.query(InterviewRecordingDB).filter(InterviewRecordingDB.id == recording.id).first()
        if recording:
            recording.status = RecordingStatus.FAILED.value
            recording.failure_code = "media-storage-failed"
            db.commit()
        raise HTTPException(status_code=status.HTTP_507_INSUFFICIENT_STORAGE, detail="Unable to store interview media") from error


@router.post("/{interview_id}/recording/unavailable", response_model=RecordingStateResponse)
def mark_recording_unavailable(
    interview_id: int,
    payload: RecordingUnavailableRequest,
    user: UserDB = Depends(_current_media_user),
    db: Session = Depends(get_db),
):
    interview = _get_interview(db, interview_id)
    _require_owner(interview, user)
    recording = db.query(InterviewRecordingDB).filter(
        InterviewRecordingDB.medical_interview_id == interview_id
    ).first()
    if recording is None:
        recording = InterviewRecordingDB(
            medical_interview_id=interview_id,
            status=RecordingStatus.UNAVAILABLE.value,
            started_at=interview.start_time,
            capture_config={},
            consent_basis="institutional",
            consent_policy_version=settings.media_consent_policy_version,
        )
        db.add(recording)
    failure_code = (
        payload.failure_code
        if payload.failure_code in KNOWN_FAILURE_CODES
        else "capture-unavailable"
    )
    recording.status = (
        RecordingStatus.FAILED.value
        if failure_code
        in {"recording-upload-failed", "temporary-storage-failed", "media-recorder-failed"}
        else RecordingStatus.UNAVAILABLE.value
    )
    recording.duration_ms = payload.duration_ms
    recording.ended_at = datetime.now(timezone.utc)
    recording.failure_code = failure_code
    db.commit()
    db.refresh(recording)
    logger.warning(
        "recording_storage_event interview_id=%s recording_id=%s event=unavailable "
        "status=%s failure_code=%s duration_ms=%s",
        interview_id,
        recording.id,
        recording.status,
        failure_code,
        recording.duration_ms,
    )
    return _recording_response(recording)


@router.get("/{interview_id}/recap", response_model=InterviewRecapResponse)
def get_recap(
    interview_id: int,
    user: UserDB = Depends(_current_media_user),
    db: Session = Depends(get_db),
    storage: LocalMediaStorage = Depends(get_media_storage),
):
    interview = _get_interview(db, interview_id)
    _require_replay_access(interview, user)
    recording = db.query(InterviewRecordingDB).filter(
        InterviewRecordingDB.medical_interview_id == interview_id
    ).first()
    turns = _recap_turns(db, interview)
    if recording is None:
        return InterviewRecapResponse(
            interview_id=interview_id,
            recording_status=RecordingStatus.UNAVAILABLE,
            turns=turns,
        )
    assets = {}
    for asset in recording.assets:
        if asset.status != "ready":
            continue
        try:
            storage.resolve(asset.storage_key)
        except (FileNotFoundError, ValueError):
            continue
        assets[asset.kind] = asset
    sources = {
        f"{kind.value}_source": (
            f"/medical-interviews/{interview_id}/recording/assets/{kind.value}"
            if kind.value in assets
            else None
        )
        for kind in MediaAssetKind
    }
    recording_status = RecordingStatus(recording.status)
    if recording_status in {RecordingStatus.READY, RecordingStatus.PARTIAL}:
        recording_status = _status_for_asset_count(len(assets))
    return InterviewRecapResponse(
        interview_id=interview_id,
        recording_status=recording_status,
        duration_ms=recording.duration_ms,
        turns=turns,
        **sources,
    )


@router.get("/{interview_id}/recording/assets/{asset_kind}")
async def stream_recording_asset(
    interview_id: int,
    asset_kind: MediaAssetKind,
    request: Request,
    user: UserDB = Depends(_current_media_user),
    db: Session = Depends(get_db),
    storage: LocalMediaStorage = Depends(get_media_storage),
):
    interview = _get_interview(db, interview_id)
    _require_replay_access(interview, user)
    asset = db.query(InterviewMediaAssetDB).join(InterviewRecordingDB).filter(
        InterviewRecordingDB.medical_interview_id == interview_id,
        InterviewMediaAssetDB.kind == asset_kind.value,
        InterviewMediaAssetDB.status == "ready",
    ).first()
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording asset not found")
    try:
        path = storage.resolve(asset.storage_key)
    except FileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording asset unavailable") from error

    file_size = path.stat().st_size
    range_header = request.headers.get("range")
    start, end, response_status = _parse_range(range_header, file_size)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Cache-Control": "private, no-store",
    }
    if response_status == status.HTTP_206_PARTIAL_CONTENT:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    return StreamingResponse(
        storage.iter_range(path, start, end),
        status_code=response_status,
        media_type=asset.content_type or mimetypes.guess_type(path.name)[0],
        headers=headers,
    )


def _parse_range(range_header: Optional[str], file_size: int) -> tuple[int, int, int]:
    if file_size <= 0:
        return 0, -1, status.HTTP_200_OK
    if not range_header:
        return 0, file_size - 1, status.HTTP_200_OK
    match = RANGE_PATTERN.match(range_header.strip())
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"},
        )
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
    if start_text:
        start = int(start_text)
        end = int(end_text) if end_text else file_size - 1
    else:
        suffix_length = int(end_text)
        start = max(file_size - suffix_length, 0)
        end = file_size - 1
    if start >= file_size or start > end:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"},
        )
    return start, min(end, file_size - 1), status.HTTP_206_PARTIAL_CONTENT


def _validate_source_durations(
    durations: Dict[str, int],
    uploads: Dict[str, Optional[UploadFile]],
    common_duration_ms: int,
) -> Dict[str, int]:
    validated: Dict[str, int] = {}
    for kind, upload in uploads.items():
        if upload is None:
            continue
        if kind not in durations:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Missing duration for {kind}",
            )
        try:
            source_duration = int(durations[kind])
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid duration for {kind}",
            ) from error
        if source_duration < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid duration for {kind}",
            )
        if abs(source_duration - common_duration_ms) > settings.media_duration_tolerance_ms:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{kind} duration differs from the common timeline",
            )
        validated[kind] = source_duration
    return validated


def _status_for_asset_count(available_count: int) -> RecordingStatus:
    if available_count >= len(MediaAssetKind):
        return RecordingStatus.READY
    if available_count > 0:
        return RecordingStatus.PARTIAL
    return RecordingStatus.UNAVAILABLE


def _turn_response(turn: InterviewTurnDB) -> RecapTurn:
    return RecapTurn(
        turn_id=turn.id,
        message_id=turn.message_id,
        speaker=turn.speaker,
        start_ms=turn.start_ms,
        end_ms=turn.end_ms,
        transcript=turn.transcript,
        input_source=turn.input_source,
        timing_source=turn.timing_source,
        timing_quality=turn.timing_quality,
        paraverbal=turn.paraverbal,
        nonverbal_features=turn.nonverbal_features,
        pyfeat_nonverbal_features=turn.pyfeat_nonverbal_features,
    )


async def _attach_student_paraverbal_observations(
    db: Session,
    storage: LocalMediaStorage,
    interview_id: int,
    recording: InterviewRecordingDB,
) -> None:
    """Populate observations without making raw-media availability a DB contract."""
    if not settings.paraverbal_analysis_enabled:
        return
    student_audio = db.query(InterviewMediaAssetDB).filter(
        InterviewMediaAssetDB.recording_id == recording.id,
        InterviewMediaAssetDB.kind == MediaAssetKind.STUDENT_AUDIO.value,
        InterviewMediaAssetDB.status == "ready",
    ).first()
    if student_audio is None:
        logger.info(
            "recording_storage_event interview_id=%s recording_id=%s "
            "event=paraverbal_skipped reason=student_audio_unavailable",
            interview_id,
            recording.id,
        )
        return
    student_turns = db.query(InterviewTurnDB).filter(
        InterviewTurnDB.medical_interview_id == interview_id,
        InterviewTurnDB.speaker == "student",
    ).order_by(InterviewTurnDB.sequence).all()
    if not student_turns:
        logger.info(
            "recording_storage_event interview_id=%s recording_id=%s "
            "event=paraverbal_skipped reason=student_turns_unavailable",
            interview_id,
            recording.id,
        )
        return
    try:
        audio_path = storage.resolve(student_audio.storage_key)
        observations = await run_in_threadpool(
            analyze_student_turns,
            audio_path,
            [
                StudentTurnAudio(
                    turn_id=turn.id,
                    start_ms=turn.start_ms,
                    end_ms=turn.end_ms,
                    transcript=turn.transcript,
                )
                for turn in student_turns
            ],
        )
    except Exception:
        logger.exception(
            "Paraverbal extraction failed for interview %s; transcript remains available",
            interview_id,
        )
        return
    for turn in student_turns:
        turn.paraverbal = observations.get(turn.id)
    logger.info(
        "recording_storage_event interview_id=%s recording_id=%s "
        "event=paraverbal_completed student_turn_count=%s observation_count=%s",
        interview_id,
        recording.id,
        len(student_turns),
        len(observations),
    )


async def _attach_student_nonverbal_observations(
    db: Session,
    storage: LocalMediaStorage,
    interview_id: int,
    recording: InterviewRecordingDB,
) -> None:
    """Populate descriptive per-turn visual observations from student video."""
    if not settings.nonverbal_analysis_enabled:
        return
    student_video = db.query(InterviewMediaAssetDB).filter(
        InterviewMediaAssetDB.recording_id == recording.id,
        InterviewMediaAssetDB.kind == MediaAssetKind.STUDENT_VIDEO.value,
        InterviewMediaAssetDB.status == "ready",
    ).first()
    if student_video is None:
        logger.info(
            "recording_storage_event interview_id=%s recording_id=%s "
            "event=nonverbal_skipped reason=student_video_unavailable",
            interview_id,
            recording.id,
        )
        return
    turn_windows = db.query(InterviewTurnDB).filter(
        InterviewTurnDB.medical_interview_id == interview_id,
    ).order_by(InterviewTurnDB.sequence).all()
    if not turn_windows:
        logger.info(
            "recording_storage_event interview_id=%s recording_id=%s "
            "event=nonverbal_skipped reason=turn_windows_unavailable",
            interview_id,
            recording.id,
        )
        return
    try:
        video_path = storage.resolve(student_video.storage_key)
        observations = await run_in_threadpool(
            analyze_student_turn_videos,
            video_path,
            [
                StudentTurnVideo(
                    turn_id=turn.id,
                    start_ms=turn.start_ms,
                    end_ms=turn.end_ms,
                    conversation_speaker=turn.speaker,
                )
                for turn in turn_windows
            ],
        )
    except Exception:
        logger.exception(
            "Nonverbal extraction failed for interview %s; transcript remains available",
            interview_id,
        )
        return
    for turn in turn_windows:
        turn.nonverbal_features = observations.get(turn.id)
    logger.info(
        "recording_storage_event interview_id=%s recording_id=%s "
        "event=nonverbal_completed turn_window_count=%s observation_count=%s",
        interview_id,
        recording.id,
        len(turn_windows),
        len(observations),
    )


async def _attach_student_pyfeat_benchmark_observations(
    db: Session,
    storage: LocalMediaStorage,
    interview_id: int,
    recording: InterviewRecordingDB,
) -> None:
    """Persist Py-Feat v2 observations separately for later benchmarking."""
    if not settings.pyfeat_analysis_enabled:
        return
    student_video = db.query(InterviewMediaAssetDB).filter(
        InterviewMediaAssetDB.recording_id == recording.id,
        InterviewMediaAssetDB.kind == MediaAssetKind.STUDENT_VIDEO.value,
        InterviewMediaAssetDB.status == "ready",
    ).first()
    turn_windows = db.query(InterviewTurnDB).filter(
        InterviewTurnDB.medical_interview_id == interview_id,
    ).order_by(InterviewTurnDB.sequence).all()
    if student_video is None or not turn_windows:
        logger.info(
            "recording_storage_event interview_id=%s recording_id=%s "
            "event=pyfeat_skipped reason=%s",
            interview_id,
            recording.id,
            "student_video_unavailable" if student_video is None else "turn_windows_unavailable",
        )
        return
    try:
        observations = await run_in_threadpool(
            analyze_pyfeat_student_turn_videos,
            storage.resolve(student_video.storage_key),
            [
                StudentTurnVideo(
                    turn_id=turn.id,
                    start_ms=turn.start_ms,
                    end_ms=turn.end_ms,
                    conversation_speaker=turn.speaker,
                )
                for turn in turn_windows
            ],
        )
    except Exception:
        logger.exception(
            "Py-Feat benchmark extraction failed for interview %s; OpenFace remains available",
            interview_id,
        )
        return
    for turn in turn_windows:
        turn.pyfeat_nonverbal_features = observations.get(turn.id)
    logger.info(
        "recording_storage_event interview_id=%s recording_id=%s "
        "event=pyfeat_completed turn_window_count=%s observation_count=%s",
        interview_id,
        recording.id,
        len(turn_windows),
        len(observations),
    )


async def _process_recording_observations(
    interview_id: int,
    recording_id: str,
) -> None:
    """Extract derived observations after durable media storage has responded."""
    db = SessionLocal()
    try:
        recording = db.query(InterviewRecordingDB).filter(
            InterviewRecordingDB.id == recording_id,
            InterviewRecordingDB.medical_interview_id == interview_id,
        ).first()
        if recording is None:
            logger.warning(
                "recording_processing_event interview_id=%s recording_id=%s "
                "event=skipped reason=recording_unavailable",
                interview_id,
                recording_id,
            )
            return
        logger.info(
            "recording_processing_event interview_id=%s recording_id=%s event=started",
            interview_id,
            recording_id,
        )
        storage = get_media_storage()
        await _attach_student_paraverbal_observations(
            db=db,
            storage=storage,
            interview_id=interview_id,
            recording=recording,
        )
        await _attach_student_nonverbal_observations(
            db=db,
            storage=storage,
            interview_id=interview_id,
            recording=recording,
        )
        await _attach_student_pyfeat_benchmark_observations(
            db=db,
            storage=storage,
            interview_id=interview_id,
            recording=recording,
        )
        db.commit()
        logger.info(
            "recording_processing_event interview_id=%s recording_id=%s event=completed",
            interview_id,
            recording_id,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "recording_processing_event interview_id=%s recording_id=%s event=failed",
            interview_id,
            recording_id,
        )
    finally:
        db.close()


def _recap_turns(db: Session, interview: MedicalInterviewDB) -> list[RecapTurn]:
    turns = db.query(InterviewTurnDB).filter(
        InterviewTurnDB.medical_interview_id == interview.id
    ).order_by(InterviewTurnDB.sequence).all()
    messages = db.query(InterviewMessageDB).filter(
        InterviewMessageDB.interview_id == interview.id
    ).order_by(InterviewMessageDB.created_at, InterviewMessageDB.id).all()
    turns_by_message_id = {
        turn.message_id: turn for turn in turns if turn.message_id is not None
    }
    result: list[RecapTurn] = []
    for message in messages:
        turn = turns_by_message_id.get(message.id)
        if turn is not None:
            result.append(_turn_response(turn))
            continue
        sender_type = getattr(message.sender_type, "value", message.sender_type)
        result.append(
            RecapTurn(
                turn_id=f"legacy-{message.id}",
                message_id=message.id,
                speaker="student" if sender_type == SenderType.USER.value else "patient",
                transcript=message.content,
                input_source="legacy_message",
                timing_source="unavailable",
                timing_quality="unavailable",
            )
        )
    result.extend(
        _turn_response(turn) for turn in turns if turn.message_id is None
    )
    return result
