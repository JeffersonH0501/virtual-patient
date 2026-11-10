"""Capture and finalize recording segments without changing the interview transcript."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.controllers.interview_lifecycle import require_capture_open
from app.controllers.recording_segments import owned_interview as _owned_interview, latest_segment, lock_recording, pending_patient_message, seal_segment
from app.core.database import get_db
from app.media.retention import media_retention_deadline
from app.media.upload_route import RecordingUploadRoute
from app.models.medical_interview import InterviewRecordingDB, InterviewRecordingSegmentDB, InterviewTurnDB, RecordingStatus
from app.models.user import UserDB
from app.media.access import _current_media_user
from app.media.patient_roi import validate_patient_roi as _validate_patient_roi
from app.core.config import settings
MEDIA_RETENTION_MONTHS = settings.media_retention_months


router = APIRouter(prefix="/medical-interviews", tags=["interview-recordings"], route_class=RecordingUploadRoute)
logger = logging.getLogger(__name__)


class ResumeRequest(BaseModel):
    request_id: UUID


class SegmentStartRequest(ResumeRequest):
    capture_config: dict[str, Any] = Field(default_factory=dict)
    resume_attempt_id: UUID | None = None
    previous_segment_id: UUID | None = None


def _ensure_recording(db, interview, recording):
    if recording is None:
        recording = InterviewRecordingDB(
            medical_interview_id=interview.id,
            started_at=interview.start_time,
            capture_config={'mediaTransport': 'reusable_blocks_v1'},
            retention_expires_at=media_retention_deadline(interview.start_time, MEDIA_RETENTION_MONTHS),
        )
        db.add(recording)
        db.flush()
    return recording


def _capture_config(config):
    return {key: value for key, value in config.items()
            if not key.startswith("_") and key != "encoded_media_timing"}


@router.post("/{interview_id}/recording/resume")
def resume_recording(
    interview_id: int, payload: ResumeRequest,
    user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db),
):
    interview = _owned_interview(db, interview_id, user)
    if (interview.interview_metadata or {}).get('recording_transport') != 'reusable_blocks_v1':
        raise HTTPException(409, {'code': 'recording_transport_conflict'})
    recording = lock_recording(db, interview_id)
    config = dict(recording.capture_config or {}) if recording else {}
    requests = dict(config.get("resume_requests") or {})
    request_id = str(payload.request_id)
    if request_id in requests:
        return requests[request_id]
    require_capture_open(interview)
    if interview.start_time is None:
        raise HTTPException(status_code=409, detail="The interview has not started")

    pending = config.get("resume_attempt")
    if pending:
        response = requests[pending["id"]]
    else:
        previous = latest_segment(db, recording) if recording is not None else None
        pending_message_id = pending_patient_message(db, interview_id)
        duration = seal_segment(db, previous, pending_message_id) if previous is not None else 0
        response = {
            "resume_attempt_id": request_id,
            "offset_ms": previous.offset_ms + duration if previous is not None else 0,
            "previous_segment_id": previous.id if previous is not None else None,
            "previous_duration_ms": duration,
            "pending_patient_message_id": pending_message_id,
            "recoverable_segments": [
                {"segment_id": item.id, "duration_ms": item.duration_ms}
                for item in db.query(InterviewRecordingSegmentDB).filter_by(recording_id=recording.id)
                .order_by(InterviewRecordingSegmentDB.sequence).all()
                if item.sealed_at is not None and item.duration_ms > 0
            ] if recording is not None else [],
        }
        config["resume_attempt"] = {**response, "id": request_id, "created_at": datetime.now(timezone.utc).isoformat()}
    recording = _ensure_recording(db, interview, recording)
    response["retention_expires_at"] = recording.retention_expires_at.isoformat() if recording.retention_expires_at else None
    if (interview.interview_metadata or {}).get('recording_transport') == 'reusable_blocks_v1':
        config['mediaTransport'] = 'reusable_blocks_v1'
    requests[request_id] = response
    recording.capture_config = {**config, "resume_requests": requests}
    metadata = dict(interview.interview_metadata or {})
    metadata.pop("message_request", None)
    interview.interview_metadata = metadata
    db.commit()
    return response


@router.post("/{interview_id}/recording/segments")
def start_segment(
    interview_id: int, payload: SegmentStartRequest,
    user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db),
):
    interview = _owned_interview(db, interview_id, user)
    if (interview.interview_metadata or {}).get('recording_transport') != 'reusable_blocks_v1':
        raise HTTPException(409, {'code': 'recording_transport_conflict'})
    recording = lock_recording(db, interview_id)
    segment_id = str(payload.request_id)
    requested = payload.model_dump(mode="json", exclude={"request_id"})
    existing = db.get(InterviewRecordingSegmentDB, segment_id)
    if existing is not None:
        if (recording is None or existing.recording_id != recording.id or
                (existing.capture_config or {}).get("_start_request") != requested):
            raise HTTPException(status_code=409, detail="Segment request ID is already in use")
        return {"segment_id": existing.id, "offset_ms": existing.offset_ms,
                "retention_expires_at": recording.retention_expires_at}
    require_capture_open(interview)
    if interview.start_time is None:
        raise HTTPException(status_code=409, detail="The interview has not started")
    config = dict(recording.capture_config or {}) if recording else {}
    previous = latest_segment(db, recording) if recording is not None else None
    attempt = config.get("resume_attempt")
    calibration = (interview.interview_metadata or {}).get("calibration")
    pending_message_id = None
    if attempt or payload.resume_attempt_id is not None:
        if not attempt or attempt["id"] != str(payload.resume_attempt_id) or not attempt.get("calibration"):
            raise HTTPException(status_code=409, detail="The current resume attempt requires a verified calibration")
        calibration = attempt["calibration"]
        pending_message_id = attempt.get("pending_patient_message_id")
    elif previous is not None:
        previous_geometry = (previous.capture_config or {}).get("geometry")
        if (previous.sealed_at is None or previous.id != str(payload.previous_segment_id) or
                not previous_geometry or previous_geometry != payload.capture_config.get("geometry")):
            raise HTTPException(status_code=409, detail="The previous segment requires a new calibration")
        calibration = previous.calibration
        pending_message_id = pending_patient_message(db, interview_id)
    elif recording is not None and (recording.assets or db.query(InterviewTurnDB.id).filter_by(
        medical_interview_id=interview_id
    ).first()):
        raise HTTPException(status_code=409, detail="An existing capture must be resumed")
    if not calibration or calibration.get("status") != "passed":
        raise HTTPException(status_code=409, detail="A verified calibration is required")
    if previous is not None and previous.sealed_at is None:
        raise HTTPException(status_code=409, detail="An active recording segment already exists")
    _validate_patient_roi(payload.capture_config.get("patientRoiSnapshots", []))
    transport = (interview.interview_metadata or {}).get('recording_transport')
    expected_geometry = (calibration.get("profile") or {}).get("capture_geometry")
    if transport == "reusable_blocks_v1" and expected_geometry:
        supplied_geometry = payload.capture_config.get("geometry") or {}
        if any(supplied_geometry.get(key) != value for key, value in expected_geometry.items()):
            raise HTTPException(409, {"code": "capture_geometry_changed"})
    if payload.capture_config.get('mediaTransport') == 'reusable_blocks_v1' and transport != 'reusable_blocks_v1':
        raise HTTPException(409, 'An existing interview cannot change recording transport')
    recording = _ensure_recording(db, interview, recording)
    offset = previous.offset_ms + previous.duration_ms if previous is not None else 0
    db.add(InterviewRecordingSegmentDB(
        id=segment_id, recording_id=recording.id, offset_ms=offset,
        sequence=previous.sequence + 1 if previous is not None else 0,
        capture_config={**_capture_config(payload.capture_config),
                        **({'mediaTransport': transport} if transport == 'reusable_blocks_v1' else {}), "_start_request": requested,
                        "_pending_patient_message_id": pending_message_id},
        calibration=calibration,
    ))
    config.pop("resume_attempt", None)
    transport = (interview.interview_metadata or {}).get('recording_transport')
    if transport == 'reusable_blocks_v1':
        if previous is not None and (previous.capture_config or {}).get('mediaTransport') != transport:
            raise HTTPException(409, 'An active interview cannot change recording transport')
        config['mediaTransport'] = transport
    recording.capture_config = config
    recording.status = RecordingStatus.RECORDING.value
    db.commit()
    return {"segment_id": segment_id, "offset_ms": offset,
            "retention_expires_at": recording.retention_expires_at}


