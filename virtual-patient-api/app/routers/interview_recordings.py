"""Authenticated capture, storage, and replay of synchronized interview media."""

from __future__ import annotations

import json
import logging
import mimetypes
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, Optional

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
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_from_token
from app.core.database import get_db
from app.media import LocalMediaStorage, get_media_storage
from app.multimodal.legacy_adapter import normalize_observation
from app.multimodal.pipeline import process_multimodal_interview
from app.multimodal.reprocess import reprocess_interview_evaluation
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


router = APIRouter(prefix="/medical-interviews", tags=["interview-recordings"])
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Interview media governance settings. Hardcoded on purpose: these values are
# fixed for the deployment and are not sourced from the environment.
# No automatic deletion is performed yet, so retention has no expiry by default.
MEDIA_RETENTION_DAYS: int | None = None
MEDIA_CONSENT_POLICY_VERSION = "institutional-v1"

# Non-terminal observation_processing statuses reported by the multimodal
# pipeline (see app/multimodal/pipeline.py STATUS_*). While a run is in one of
# these states a new reprocess request must be rejected to avoid interleaved
# writes to the same per-turn columns.
_PENDING_OBSERVATION_STATUSES = frozenset({"queued", "processing"})
MEDIA_DURATION_TOLERANCE_MS = 500

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


def _require_completed_for_replay(interview: MedicalInterviewDB) -> None:
    # The recap and its media assets are review artifacts. They only become
    # accessible once the interview is completed (text evaluation ready);
    # multimodal processing may still be running in the background. While the
    # interview is in_progress, processing or interrupted, replay stays blocked.
    if interview.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Interview results are not ready yet",
        )


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
    if getattr(interview.status, "value", interview.status) != "in_progress":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only in-progress interviews can start recording")
    if interview.start_time is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The interview has not started")

    recording = db.query(InterviewRecordingDB).filter(
        InterviewRecordingDB.medical_interview_id == interview_id
    ).first()
    if recording is None:
        retention_expires_at = None
        if MEDIA_RETENTION_DAYS is not None:
            retention_expires_at = payload.started_at + timedelta(days=MEDIA_RETENTION_DAYS)
        recording = InterviewRecordingDB(
            medical_interview_id=interview_id,
            status=RecordingStatus.RECORDING.value,
            started_at=payload.started_at,
            capture_config=payload.capture_config,
            consent_basis="institutional",
            consent_policy_version=MEDIA_CONSENT_POLICY_VERSION,
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
    if latest_turn and latest_turn.end_ms > duration_ms + MEDIA_DURATION_TOLERANCE_MS:
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
        recording.capture_config = {
            **parsed_capture_config,
            # Seed the observable lifecycle before the pipeline picks it up. The
            # stage name matches the pipeline's initial STAGE_QUEUED so the
            # vocabulary is consistent from finalize through processing.
            "observation_processing": {"status": "queued", "stage": "queued"},
        }
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
        # The router only schedules the staged multimodal pipeline; it performs
        # no extraction, preprocessing, thresholding, or labeling inline
        # (Requirement 19.6). The pipeline owns its own DB session and updates
        # the observation_processing lifecycle as it advances.
        background_tasks.add_task(
            process_multimodal_interview,
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
            consent_policy_version=MEDIA_CONSENT_POLICY_VERSION,
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
    _require_completed_for_replay(interview)
    recording = db.query(InterviewRecordingDB).filter(
        InterviewRecordingDB.medical_interview_id == interview_id
    ).first()
    turns = _recap_turns(db, interview)
    if recording is None:
        return InterviewRecapResponse(
            interview_id=interview_id,
            recording_status=RecordingStatus.UNAVAILABLE,
            observation_processing={"status": "unavailable"},
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
        observation_processing=(recording.capture_config or {}).get(
            "observation_processing", {"status": "unavailable"}
        ),
        turns=turns,
        **sources,
    )


@router.post("/{interview_id}/recording/reprocess", response_model=RecordingStateResponse)
def reprocess_recording(
    interview_id: int,
    background_tasks: BackgroundTasks,
    user: UserDB = Depends(_current_media_user),
    db: Session = Depends(get_db),
):
    """Re-run the whole analysis for a completed interview from the review screen.

    The regeneration runs the two operations in order: first the full multimodal
    pipeline (paraverbal + non-verbal extraction and per-turn integrated
    labels), then the final textual communication evaluation. Only the owner can
    trigger it, and only once the interview is completed and its recording has
    durable media to re-analyze. The interview lifecycle status is left
    unchanged (``completed``) so the review and its recap stay reachable while
    the work runs; the UI tracks progress through ``observation_processing``.
    """
    interview = _get_interview(db, interview_id)
    _require_owner(interview, user)
    if getattr(interview.status, "value", interview.status) != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only completed interviews can be reprocessed",
        )
    recording = db.query(InterviewRecordingDB).filter(
        InterviewRecordingDB.medical_interview_id == interview_id
    ).first()
    if recording is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This interview has no recording to reprocess",
        )
    # A run already in flight must not be duplicated: the pipeline overwrites the
    # same per-turn columns, so two concurrent runs could interleave writes.
    current = (recording.capture_config or {}).get("observation_processing", {})
    if current.get("status") in _PENDING_OBSERVATION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analysis is already being regenerated",
        )

    # Re-seed the observable lifecycle before the pipeline picks it up, mirroring
    # the seed written at finalize so the vocabulary stays consistent.
    recording.capture_config = {
        **(recording.capture_config or {}),
        "observation_processing": {"status": "queued", "stage": "queued"},
    }
    db.commit()
    db.refresh(recording)
    logger.info(
        "recording_storage_event interview_id=%s recording_id=%s event=reprocess_requested",
        interview_id,
        recording.id,
    )
    background_tasks.add_task(
        reprocess_interview_evaluation,
        interview_id,
        recording.id,
    )
    return _recording_response(recording)


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
    _require_completed_for_replay(interview)
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
        if abs(source_duration - common_duration_ms) > MEDIA_DURATION_TOLERANCE_MS:
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
        # Normalize each stored observation into the layered read shape so the
        # recap renders both new layered rows and legacy flat rows uniformly
        # (Requirements 22.1, 22.2, 23.1). This is a read-time transform only:
        # stored JSON is never rewritten, so there is no destructive migration
        # (Requirement 22.3). Layered rows pass through unchanged apart from a
        # ``schema`` marker; legacy rows are wrapped without fabricating labels.
        paraverbal=_without_none(
            normalize_observation(turn.paraverbal, modality="paraverbal")
        ),
        nonverbal_features=_without_none(
            normalize_observation(turn.nonverbal_features, modality="nonverbal")
        ),
    )


def _without_none(value: Any) -> Any:
    """Remove unavailable optional measurements from API observation payloads."""
    if isinstance(value, dict):
        return {key: _without_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_without_none(item) for item in value if item is not None]
    return value


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
