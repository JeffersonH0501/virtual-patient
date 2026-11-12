"""Immutable per-turn media upload; one file per student turn.

Replaces the former per-exchange block router. Each student turn uploads its own
camera/microphone original; the durable ``TurnVideoAnalysisDB`` job then reads
that file directly. Transfer and probing never hold conversation locks.
"""
import hashlib
import json
import logging
import subprocess
import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from app.controllers.interview_lifecycle import require_capture_open, require_no_pending_reply, threaded_capture
from app.controllers.recording_segments import latest_segment, lock_recording
from app.core.database import get_db
from app.media import LocalMediaStorage, get_media_storage
from app.media.probe import probe_media_timing
from app.media.upload_route import RecordingUploadRoute
from app.models.medical_interview import InterviewMessageDB, InterviewRecordingDB, InterviewRecordingSegmentDB, TurnVideoAnalysisDB
from app.models.turn_media import InterviewTurnMediaDB
from app.models.user import UserDB
from app.media.access import (ALLOWED_CONTENT_TYPES, _current_media_user, _discard_saved_media,
    _get_interview, _require_replay_access, _require_completed_for_replay, _stream_private_media)
from app.controllers.recording_segments import owned_interview as _owned_interview, recording_segment as _segment

router = APIRouter(prefix="/medical-interviews", tags=["interview-recordings"], route_class=RecordingUploadRoute)
logger = logging.getLogger(__name__)


def _require_turn_transport(recording):
    if recording is None or (recording.capture_config or {}).get('mediaTransport') != 'per_turn_v1':
        raise HTTPException(409, {'code': 'recording_transport_conflict'})


class TurnFinalization(BaseModel):
    turn_media_ids: list[UUID] = Field(default_factory=list, max_length=10000)
    missing_message_ids: list[int] = Field(default_factory=list, max_length=10000)


class TurnMediaMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capture_attempt_id: UUID
    order: int = Field(ge=0, le=100000)
    duration_ms: int = Field(gt=0, le=3_600_000)
    message_id: int = Field(gt=0)
    speaker: str = Field(pattern="^student$")
    session_clock_ms: int = Field(ge=0)
    interaction_area_snapshots: list[dict] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def coherent(self):
        from app.media.patient_roi import validate_patient_roi as _validate_patient_roi
        _validate_patient_roi(self.interaction_area_snapshots)
        return self


def _receipt(media):
    return {"turn_media_id": media.id, "capture_attempt_id": media.capture_attempt_id,
            "order": media.order, "duration_ms": media.duration_ms, "message_id": media.message_id,
            "sha256": media.sha256, "metadata_hash": media.metadata_hash, "preserved": True}


def _authorize(db, interview_id, user, payload, writer, resume_attempt):
    interview = _owned_interview(db, interview_id, user)
    recording = lock_recording(db, interview_id)
    segment = _segment(db, recording, payload.capture_attempt_id)
    _require_turn_transport(recording)
    attempt = (recording.capture_config or {}).get("resume_attempt")
    current = latest_segment(db, recording)
    if (writer is None or current is None or
            (attempt and attempt["id"] != resume_attempt) or
            (not attempt and (current.id != writer or current.sealed_at is not None))):
        raise HTTPException(409, {"code": "stale_capture"})
    require_capture_open(interview)
    from datetime import datetime, timezone
    if recording.retention_expires_at and recording.retention_expires_at <= datetime.now(timezone.utc):
        raise HTTPException(410, 'Recording retention has expired')
    return recording, segment


def _message(db, interview_id, payload):
    message = db.get(InterviewMessageDB, payload.message_id)
    if message is None or message.interview_id != interview_id or message.sender_type != "user":
        raise HTTPException(422, "Turn media must belong to this interview and a student message")


@router.post('/{interview_id}/recording/turns/recovery')
def record_recovery_gap(interview_id: int, payload: TurnFinalization,
        resume_attempt_id: Annotated[UUID, Header(alias='X-Resume-Attempt')],
        user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db)):
    db.info['capture_wait'] = True
    interview = _owned_interview(db, interview_id, user)
    recording = lock_recording(db, interview_id)
    _require_turn_transport(recording)
    attempt = (recording.capture_config or {}).get('resume_attempt') if recording else None
    if not attempt or attempt['id'] != str(resume_attempt_id):
        raise HTTPException(409, {'code': 'stale_capture'})
    ids = {item[0] for item in db.query(InterviewMessageDB.id).filter_by(interview_id=interview_id)}
    if not set(payload.missing_message_ids) <= ids:
        raise HTTPException(422, 'Evidence gaps must refer to this interview')
    metadata = dict(interview.interview_metadata or {})
    metadata['missing_evidence_message_ids'] = sorted(set(metadata.get('missing_evidence_message_ids', [])) | set(payload.missing_message_ids))
    interview.interview_metadata = metadata
    db.commit()
    return {'recorded': True}


@router.post('/{interview_id}/recording/turns/finalize')
def finalize_turns(interview_id: int, payload: TurnFinalization,
        capture_segment_id: Annotated[UUID | None, Header(alias='X-Capture-Segment')] = None,
        user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db),
        storage: LocalMediaStorage = Depends(get_media_storage)):
    from datetime import datetime, timezone
    from app.controllers.recording_segments import require_capture_epoch, seal_segment
    from app.multimodal.turn_staging import ordered_turn_media, stage_turn_media
    from app.multimodal.processing_jobs import stage_processing_job
    db.info['capture_wait'] = True
    interview = _owned_interview(db, interview_id, user)
    recording = require_capture_epoch(db, interview_id, str(capture_segment_id) if capture_segment_id else None)
    if recording is None:
        raise HTTPException(409, 'Capture has not started')
    _require_turn_transport(recording)
    manifest = {'turn_media_ids': sorted(str(item) for item in payload.turn_media_ids),
                'missing_message_ids': sorted(set(payload.missing_message_ids))}
    previous = (recording.capture_config or {}).get('turn_finalization')
    if previous is not None:
        if previous != manifest:
            raise HTTPException(409, 'Confirmed turn manifest cannot change')
        return {'duration_ms': recording.duration_ms, 'recording_status': recording.status}
    require_capture_open(interview)
    require_no_pending_reply(interview)
    media = ordered_turn_media(db, recording.id)
    if set(manifest['turn_media_ids']) != {item.id for item in media}:
        raise HTTPException(409, 'Some originals have not been preserved')
    covered = set()
    for item in media:
        try:
            available = storage.resolve(item.storage_key).stat().st_size == item.size_bytes
        except FileNotFoundError:
            available = False
        if available and item.message_id is not None:
            covered.add(item.message_id)
    # Student messages are the capturable evidence; patient turns are TTS and are
    # never expected to carry media, so coverage is measured over student messages.
    student_messages = {item[0] for item in db.query(InterviewMessageDB.id).filter_by(
        interview_id=interview_id, sender_type="user").all()}
    declared_missing = set(payload.missing_message_ids) | set((interview.interview_metadata or {}).get('missing_evidence_message_ids', []))
    if not student_messages - covered <= declared_missing or not set(payload.missing_message_ids) <= (
            {item[0] for item in db.query(InterviewMessageDB.id).filter_by(interview_id=interview_id).all()}):
        raise HTTPException(409, 'Missing evidence must be declared explicitly')
    for segment in recording.segments:
        seal_segment(db, segment)
    ends = [item.session_clock_ms + item.duration_ms for item in media if item.duration_ms is not None]
    recording.duration_ms = max(ends) if ends else None
    recording.ended_at = datetime.now(timezone.utc)
    recording.status = 'partial' if student_messages - covered or any(
        item.duration_ms is None or item.encoded_timing.get('window_alignment') == 'unavailable' for item in media) else 'ready'
    interview.interview_metadata = {**(interview.interview_metadata or {}), 'missing_evidence_message_ids': sorted(student_messages - covered)}
    recording.capture_config = {**(recording.capture_config or {}), 'turn_finalization': manifest,
        'observation_processing': {'status': 'queued', 'stage': 'queued'}}
    stage_turn_media(db, recording)
    stage_processing_job(db, interview_id, 'pipeline', {'recording_id': recording.id})
    db.commit()
    return {'duration_ms': recording.duration_ms, 'recording_status': recording.status}


def _read_recording(db, interview_id, user):
    interview = _get_interview(db, interview_id)
    _require_replay_access(interview, user)
    if interview.user_id != user.id or getattr(interview.status, "value", interview.status) != "in_progress":
        _require_completed_for_replay(interview, allow_processing=True)
    recording = db.query(InterviewRecordingDB).filter_by(medical_interview_id=interview_id).first()
    if recording is None:
        raise HTTPException(404, "Interview recording is unavailable")
    from datetime import datetime, timezone
    if recording.failure_code == "retention_expired" or (recording.retention_expires_at and
            recording.retention_expires_at <= datetime.now(timezone.utc)):
        raise HTTPException(410, "Recording retention has expired")
    return recording


@router.get("/{interview_id}/recording/turns")
def list_turn_media(interview_id: int, user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db),
        storage: LocalMediaStorage = Depends(get_media_storage)):
    recording = _read_recording(db, interview_id, user)
    rows = db.query(InterviewTurnMediaDB).join(InterviewRecordingSegmentDB,
        InterviewRecordingSegmentDB.id == InterviewTurnMediaDB.capture_attempt_id).filter(
        InterviewTurnMediaDB.recording_id == recording.id).order_by(
        InterviewRecordingSegmentDB.sequence, InterviewTurnMediaDB.order).all()
    turns, duration = [], 0
    for media in rows:
        try:
            storage.resolve(media.storage_key)
            video = f"/medical-interviews/{interview_id}/recording/turns/{media.id}/media"
        except FileNotFoundError:
            video = None
        metadata = media.turn_metadata if media.encoded_timing.get('window_alignment') != 'unavailable' else {
            **media.turn_metadata, 'duration_ms': None}
        turns.append({**_receipt(media), "session_clock_ms": media.session_clock_ms,
            "metadata": metadata, "student_video_source": video})
        duration = max(duration, media.session_clock_ms + (media.duration_ms or 0))
    return {"interview_id": interview_id,
            "duration_ms": duration if any(m.duration_ms is not None for m in rows) else None,
            "turns": turns}


@router.get("/{interview_id}/recording/turns/{turn_media_id}/media")
def read_turn_media(interview_id: int, turn_media_id: UUID, request: Request,
        user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db),
        storage: LocalMediaStorage = Depends(get_media_storage)):
    recording = _read_recording(db, interview_id, user)
    media = db.get(InterviewTurnMediaDB, str(turn_media_id))
    if media is None or media.recording_id != recording.id:
        raise HTTPException(404, "Recording turn media is unavailable")
    try:
        path = storage.resolve(media.storage_key)
    except FileNotFoundError as error:
        raise HTTPException(404, "Turn evidence is unavailable") from error
    return _stream_private_media(storage, path, request, media.content_type)


@router.put("/{interview_id}/recording/turns/{turn_id}/video")
@threaded_capture
async def upload_turn_media(interview_id: int, turn_id: UUID,
        video: Annotated[UploadFile, File()], metadata: Annotated[str, Form(max_length=1024 * 1024)],
        capture_segment_id: Annotated[UUID | None, Header(alias="X-Capture-Segment")] = None,
        resume_attempt_id: Annotated[UUID | None, Header(alias="X-Resume-Attempt")] = None,
        user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db),
        storage: LocalMediaStorage = Depends(get_media_storage)):
    started = time.perf_counter()
    try:
        payload = TurnMediaMetadata.model_validate_json(metadata)
    except ValidationError as error:
        raise HTTPException(422, "Invalid recording turn metadata") from error
    normalized = payload.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    content_type = (video.content_type or "").split(";", 1)[0].lower()
    extension = ALLOWED_CONTENT_TYPES.get(content_type)
    if not extension or not content_type.startswith("video/"):
        raise HTTPException(415, "A camera/microphone video original is required")
    writer = str(capture_segment_id) if capture_segment_id else None
    resume = str(resume_attempt_id) if resume_attempt_id else None
    recording, segment = _authorize(db, interview_id, user, payload, writer, resume)
    _message(db, interview_id, payload)
    recording_id = recording.id
    db.rollback()
    stored = await storage.save_turn_video_upload(interview_id, recording_id, str(turn_id), video, extension)
    committed = False
    try:
        if not stored.size_bytes:
            raise HTTPException(422, "Recording turn media cannot be empty")
        try:
            timing = probe_media_timing(storage.resolve(stored.storage_key))
        except (ValueError, OSError, subprocess.SubprocessError):
            timing = {'duration_ms': None, 'window_alignment': 'unavailable', 'reason': 'encoded_timing_unavailable'}
        if timing['duration_ms'] is not None and (timing['start_pts_ms'] < -250 or abs(timing['duration_ms'] - payload.duration_ms) > 250):
            timing.update(window_alignment='unavailable', reason='encoded_clock_disagreement')
        if timing.get('max_gap_ms', 0) > 150:
            timing.update(window_alignment='unavailable', reason='encoded_packet_gap')
        recording, segment = _authorize(db, interview_id, user, payload, writer, resume)
        _message(db, interview_id, payload)
        existing = db.get(InterviewTurnMediaDB, str(turn_id))
        if existing is not None:
            same_metadata = existing.metadata_hash == digest or TurnMediaMetadata.model_validate(existing.turn_metadata).model_dump(mode='json') == normalized
            if (existing.recording_id != recording.id or not same_metadata or
                    existing.sha256 != stored.sha256 or existing.content_type != content_type):
                raise HTTPException(409, {"code": "turn_media_conflict"})
            try:
                available = storage.resolve(existing.storage_key).stat().st_size == existing.size_bytes
            except FileNotFoundError:
                available = False
            if not available:
                existing.storage_key = stored.storage_key
                db.commit()
                committed = True
            return _receipt(existing)
        if db.query(InterviewTurnMediaDB.id).filter_by(capture_attempt_id=segment.id, order=payload.order).first():
            raise HTTPException(409, {"code": "turn_media_order_conflict"})
        if db.query(InterviewTurnMediaDB.id).filter(
                InterviewTurnMediaDB.recording_id == recording.id,
                InterviewTurnMediaDB.message_id == payload.message_id).first():
            raise HTTPException(409, {'code': 'turn_media_message_conflict'})
        media = InterviewTurnMediaDB(id=str(turn_id), recording_id=recording.id,
            capture_attempt_id=segment.id, order=payload.order, duration_ms=timing["duration_ms"],
            message_id=payload.message_id, speaker=payload.speaker, session_clock_ms=payload.session_clock_ms,
            storage_key=stored.storage_key, content_type=content_type, size_bytes=stored.size_bytes,
            sha256=stored.sha256, metadata_hash=digest, turn_metadata=normalized, encoded_timing=timing)
        db.add(media)
        db.flush()
        from sqlalchemy import func
        offset = 0
        for item in sorted(recording.segments, key=lambda entry: entry.sequence):
            duration = db.query(func.max(
                InterviewTurnMediaDB.session_clock_ms + func.coalesce(InterviewTurnMediaDB.duration_ms, 0)
            )).filter_by(capture_attempt_id=item.id).scalar() or 0
            item.offset_ms = offset
            if item.sealed_at is not None:
                item.duration_ms = duration
            offset += duration
        from app.multimodal.turn_staging import stage_turn_media
        stage_turn_media(db, recording)
        db.commit()
        committed = True
        depth = db.query(TurnVideoAnalysisDB.id).filter_by(recording_id=recording.id, status='queued').count()
        logger.info("recording_turn interview_id=%s turn_media_id=%s capture_id=%s stage=preserved latency_ms=%.1f queue_depth=%s",
                    interview_id, turn_id, segment.id, (time.perf_counter() - started) * 1000, depth)
        return _receipt(media)
    finally:
        if not committed:
            db.rollback()
            _discard_saved_media(db, storage, [stored.storage_key], attempted_model=InterviewTurnMediaDB)
