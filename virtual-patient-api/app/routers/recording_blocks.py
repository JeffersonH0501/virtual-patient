"""Immutable whole-block upload; transfer and probing never hold conversation locks."""
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
from app.models.recording_block import InterviewRecordingBlockDB
from app.models.user import UserDB
from app.media.access import (ALLOWED_CONTENT_TYPES, _current_media_user, _discard_saved_media,
    _get_interview, _require_replay_access, _require_completed_for_replay, _stream_private_media)
from app.controllers.recording_segments import owned_interview as _owned_interview, recording_segment as _segment

router = APIRouter(prefix="/medical-interviews", tags=["interview-recordings"], route_class=RecordingUploadRoute)
logger = logging.getLogger(__name__)


def _require_block_transport(recording):
    if recording is None or (recording.capture_config or {}).get('mediaTransport') != 'reusable_blocks_v1':
        raise HTTPException(409, {'code': 'recording_transport_conflict'})


class BlockFinalization(BaseModel):
    block_ids: list[UUID] = Field(default_factory=list, max_length=10000)
    missing_message_ids: list[int] = Field(default_factory=list, max_length=10000)


@router.post('/{interview_id}/recording/blocks/recovery')
def record_recovery_gap(interview_id: int, payload: BlockFinalization,
        resume_attempt_id: Annotated[UUID, Header(alias='X-Resume-Attempt')],
        user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db)):
    db.info['capture_wait'] = True
    interview = _owned_interview(db, interview_id, user)
    recording = lock_recording(db, interview_id)
    _require_block_transport(recording)
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


@router.post('/{interview_id}/recording/blocks/finalize')
def finalize_blocks(interview_id: int, payload: BlockFinalization,
        capture_segment_id: Annotated[UUID | None, Header(alias='X-Capture-Segment')] = None,
        user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db),
        storage: LocalMediaStorage = Depends(get_media_storage)):
    from datetime import datetime, timezone
    from app.controllers.recording_segments import require_capture_epoch, seal_segment
    from app.multimodal.block_turns import ordered_blocks, stage_block_turns
    from app.multimodal.processing_jobs import stage_processing_job
    db.info['capture_wait'] = True
    interview = _owned_interview(db, interview_id, user)
    recording = require_capture_epoch(db, interview_id, str(capture_segment_id) if capture_segment_id else None)
    if recording is None:
        raise HTTPException(409, 'Capture has not started')
    _require_block_transport(recording)
    manifest = {'block_ids': sorted(str(item) for item in payload.block_ids),
                'missing_message_ids': sorted(set(payload.missing_message_ids))}
    previous = (recording.capture_config or {}).get('block_finalization')
    if previous is not None:
        if previous != manifest:
            raise HTTPException(409, 'Confirmed block manifest cannot change')
        return {'duration_ms': recording.duration_ms, 'recording_status': recording.status}
    require_capture_open(interview)
    require_no_pending_reply(interview)
    blocks = ordered_blocks(db, recording.id)
    if set(manifest['block_ids']) != {block.id for block in blocks}:
        raise HTTPException(409, 'Some originals have not been preserved')
    covered = set()
    for block in blocks:
        try:
            available = storage.resolve(block.storage_key).stat().st_size == block.size_bytes
        except FileNotFoundError:
            available = False
        if available:
            covered.update(value for key in ('student_message_id', 'patient_message_id')
                           if (value := block.block_metadata.get(key)) is not None)
    messages = {item[0] for item in db.query(InterviewMessageDB.id).filter_by(interview_id=interview_id).all()}
    declared_missing = set(payload.missing_message_ids) | set((interview.interview_metadata or {}).get('missing_evidence_message_ids', []))
    if not messages - covered <= declared_missing or not set(payload.missing_message_ids) <= messages:
        raise HTTPException(409, 'Missing evidence must be declared explicitly')
    for segment in recording.segments:
        seal_segment(db, segment)
    confirmed = [block.duration_ms for block in blocks if block.duration_ms is not None]
    recording.duration_ms = sum(confirmed) if confirmed else None
    recording.ended_at = datetime.now(timezone.utc)
    recording.status = 'partial' if messages - covered or any(b.block_metadata.get('patient_audio_missing') or b.encoded_timing.get('window_alignment') == 'unavailable' for b in blocks) else 'ready'
    interview.interview_metadata = {**(interview.interview_metadata or {}), 'missing_evidence_message_ids': sorted(messages - covered)}
    recording.capture_config = {**(recording.capture_config or {}), 'block_finalization': manifest,
        'observation_processing': {'status': 'queued', 'stage': 'queued'}}
    stage_block_turns(db, recording)
    stage_processing_job(db, interview_id, 'pipeline', {'recording_id': recording.id})
    db.commit()
    return {'duration_ms': recording.duration_ms, 'recording_status': recording.status}


class BlockWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end_ms < self.start_ms:
            raise ValueError("Window end precedes its start")
        return self


class BlockMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capture_attempt_id: UUID
    order: int = Field(ge=0, le=100000)
    duration_ms: int = Field(gt=0, le=3_600_000)
    student_message_id: int | None = Field(default=None, gt=0)
    patient_message_id: int = Field(gt=0)
    student_speech: BlockWindow | None = None
    student_speech_complete: bool = True
    patient_playback: BlockWindow | None = None
    patient_audio_missing: bool = False
    recovery: bool = False
    patient_playback_complete: bool = True
    patient_roi_snapshots: list[dict] = Field(default_factory=list, max_length=10000)
    interaction_area_snapshots: list[dict] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def coherent_windows(self):
        for window in (self.student_speech, self.patient_playback):
            if window and window.end_ms > self.duration_ms:
                raise ValueError("Window exceeds block duration")
        if self.student_message_id is not None and self.student_speech is None and self.student_speech_complete:
            raise ValueError("Student speech timing is required")
        if self.student_message_id is None and self.student_speech is not None:
            raise ValueError("Student timing requires a confirmed student message")
        if self.student_speech and self.patient_playback and self.student_speech.end_ms > self.patient_playback.start_ms:
            raise ValueError("Student speech overlaps patient playback")
        if self.patient_playback is None and not self.patient_audio_missing:
            raise ValueError("Patient playback or explicit missing evidence is required")
        if self.recovery and self.student_message_id is not None:
            raise ValueError("Recovery blocks cannot duplicate a student message")
        from app.media.patient_roi import validate_patient_roi as _validate_patient_roi
        _validate_patient_roi(self.patient_roi_snapshots)
        _validate_patient_roi(self.interaction_area_snapshots)
        return self


def _receipt(block):
    return {"block_id": block.id, "capture_attempt_id": block.capture_attempt_id,
            "order": block.order, "duration_ms": block.duration_ms,
            "sha256": block.sha256, "metadata_hash": block.metadata_hash, "preserved": True}


def _authorize(db, interview_id, user, payload, writer, resume_attempt):
    interview = _owned_interview(db, interview_id, user)
    recording = lock_recording(db, interview_id)
    segment = _segment(db, recording, payload.capture_attempt_id)
    _require_block_transport(recording)
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


def _messages(db, interview_id, payload):
    for identifier, sender in ((payload.student_message_id, "user"), (payload.patient_message_id, "patient")):
        if identifier is None:
            continue
        message = db.get(InterviewMessageDB, identifier)
        if message is None or message.interview_id != interview_id or message.sender_type != sender:
            raise HTTPException(422, "Block messages must belong to this interview and speaker")


def _read_recording(db, interview_id, user):
    interview = _get_interview(db, interview_id)
    _require_replay_access(interview, user)
    if interview.user_id != user.id or getattr(interview.status, "value", interview.status) != "in_progress":
        _require_completed_for_replay(interview, allow_processing=True)
    recording = db.query(InterviewRecordingDB).filter_by(
        medical_interview_id=interview_id).first()
    if recording is None:
        raise HTTPException(404, "Interview recording is unavailable")
    from datetime import datetime, timezone
    if recording.failure_code == "retention_expired" or (recording.retention_expires_at and
            recording.retention_expires_at <= datetime.now(timezone.utc)):
        raise HTTPException(410, "Recording retention has expired")
    return recording


@router.get("/{interview_id}/recording/blocks")
def list_blocks(interview_id: int, user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db),
        storage: LocalMediaStorage = Depends(get_media_storage)):
    recording = _read_recording(db, interview_id, user)
    rows = db.query(InterviewRecordingBlockDB).join(InterviewRecordingSegmentDB,
        InterviewRecordingSegmentDB.id == InterviewRecordingBlockDB.capture_attempt_id).filter(
        InterviewRecordingBlockDB.recording_id == recording.id).order_by(
        InterviewRecordingSegmentDB.sequence, InterviewRecordingBlockDB.order).all()
    blocks, offset = [], 0
    for block in rows:
        try:
            storage.resolve(block.storage_key)
            video = f"/medical-interviews/{interview_id}/recording/blocks/{block.id}/media"
        except FileNotFoundError:
            video = None
        patient_id = block.block_metadata["patient_message_id"]
        speech = f"interviews/{interview_id}/{recording.id}/patient-speech/{patient_id}.mp3"
        try:
            storage.resolve(speech)
            audio = f"/medical-interviews/{interview_id}/recording/blocks/{block.id}/patient-audio"
        except FileNotFoundError:
            audio = None
        metadata = block.block_metadata if block.encoded_timing.get('window_alignment') != 'unavailable' else {
            **block.block_metadata, 'student_speech': None, 'patient_playback': None}
        blocks.append({**_receipt(block), "offset_ms": offset, "metadata": metadata,
            "student_video_source": video, "patient_audio_source": audio})
        offset += block.duration_ms or 0
    return {"interview_id": interview_id, "duration_ms": offset if any(b.duration_ms is not None for b in rows) else None, "blocks": blocks}


@router.get("/{interview_id}/recording/blocks/{block_id}/media")
@router.get("/{interview_id}/recording/blocks/{block_id}/patient-audio")
def read_block_media(interview_id: int, block_id: UUID, request: Request,
        user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db),
        storage: LocalMediaStorage = Depends(get_media_storage)):
    recording = _read_recording(db, interview_id, user)
    block = db.get(InterviewRecordingBlockDB, str(block_id))
    if block is None or block.recording_id != recording.id:
        raise HTTPException(404, "Recording block is unavailable")
    patient = request.url.path.endswith('/patient-audio')
    key = (f"interviews/{interview_id}/{recording.id}/patient-speech/{block.block_metadata['patient_message_id']}.mp3"
           if patient else block.storage_key)
    try:
        path = storage.resolve(key)
    except FileNotFoundError as error:
        raise HTTPException(404, "Block evidence is unavailable") from error
    return _stream_private_media(storage, path, request, "audio/mpeg" if patient else block.content_type)


@router.put("/{interview_id}/recording/blocks/{block_id}")
@threaded_capture
async def upload_block(interview_id: int, block_id: UUID,
        file: Annotated[UploadFile, File()], metadata: Annotated[str, Form(max_length=1024 * 1024)],
        capture_segment_id: Annotated[UUID | None, Header(alias="X-Capture-Segment")] = None,
        resume_attempt_id: Annotated[UUID | None, Header(alias="X-Resume-Attempt")] = None,
        user: UserDB = Depends(_current_media_user), db: Session = Depends(get_db),
        storage: LocalMediaStorage = Depends(get_media_storage)):
    started = time.perf_counter()
    try:
        payload = BlockMetadata.model_validate_json(metadata)
    except ValidationError as error:
        raise HTTPException(422, "Invalid recording block metadata") from error
    normalized = payload.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    content_type = (file.content_type or "").split(";", 1)[0].lower()
    extension = ALLOWED_CONTENT_TYPES.get(content_type)
    if not extension or not content_type.startswith("video/"):
        raise HTTPException(415, "A camera/microphone video original is required")
    writer = str(capture_segment_id) if capture_segment_id else None
    resume = str(resume_attempt_id) if resume_attempt_id else None
    recording, segment = _authorize(db, interview_id, user, payload, writer, resume)
    _messages(db, interview_id, payload)
    recording_id = recording.id
    db.rollback()
    stored = await storage.save_upload(interview_id, recording_id, "student_video", file, extension)
    committed = False
    try:
        if not stored.size_bytes:
            raise HTTPException(422, "Recording block cannot be empty")
        try:
            timing = probe_media_timing(storage.resolve(stored.storage_key))
        except (ValueError, OSError, subprocess.SubprocessError):
            timing = {'duration_ms': None, 'window_alignment': 'unavailable', 'reason': 'encoded_timing_unavailable'}
        if timing['duration_ms'] is not None and (timing['start_pts_ms'] < -250 or abs(timing['duration_ms'] - payload.duration_ms) > 250):
            timing.update(window_alignment='unavailable', reason='encoded_clock_disagreement')
        if timing.get('max_gap_ms', 0) > 150:
            timing.update(window_alignment='unavailable', reason='encoded_packet_gap')
        for window in (payload.student_speech, payload.patient_playback):
            if window and timing['duration_ms'] is not None and window.end_ms > timing['duration_ms'] + 150:
                timing.update(window_alignment='unavailable', reason='window_outside_encoded_media')
        recording, segment = _authorize(db, interview_id, user, payload, writer, resume)
        _messages(db, interview_id, payload)
        existing = db.get(InterviewRecordingBlockDB, str(block_id))
        if existing is not None:
            same_metadata = existing.metadata_hash == digest or BlockMetadata.model_validate(existing.block_metadata).model_dump(mode='json') == normalized
            if (existing.recording_id != recording.id or not same_metadata or
                    existing.sha256 != stored.sha256 or existing.content_type != content_type):
                raise HTTPException(409, {"code": "block_content_conflict"})
            try:
                available = storage.resolve(existing.storage_key).stat().st_size == existing.size_bytes
            except FileNotFoundError:
                available = False
            if not available:
                existing.storage_key = stored.storage_key
                db.commit()
                committed = True
            return _receipt(existing)
        if db.query(InterviewRecordingBlockDB.id).filter_by(capture_attempt_id=segment.id, order=payload.order).first():
            raise HTTPException(409, {"code": "block_order_conflict"})
        for field, identifier in (('student_message_id', payload.student_message_id), ('patient_message_id', payload.patient_message_id if not payload.recovery else None)):
            if identifier is not None and db.query(InterviewRecordingBlockDB.id).filter(
                    InterviewRecordingBlockDB.recording_id == recording.id,
                    InterviewRecordingBlockDB.block_metadata[field].as_integer() == identifier).first():
                raise HTTPException(409, {'code': 'block_message_conflict'})
        block = InterviewRecordingBlockDB(id=str(block_id), recording_id=recording.id,
            capture_attempt_id=segment.id, order=payload.order, duration_ms=timing["duration_ms"],
            storage_key=stored.storage_key, content_type=content_type, size_bytes=stored.size_bytes,
            sha256=stored.sha256, metadata_hash=digest, block_metadata=normalized, encoded_timing=timing)
        db.add(block)
        db.flush()
        from sqlalchemy import func
        offset = 0
        for item in sorted(recording.segments, key=lambda entry: entry.sequence):
            duration = db.query(func.sum(InterviewRecordingBlockDB.duration_ms)).filter_by(capture_attempt_id=item.id).scalar() or 0
            item.offset_ms = offset
            if item.sealed_at is not None:
                item.duration_ms = duration
            offset += duration
        from app.multimodal.block_turns import stage_block_turns
        stage_block_turns(db, recording)
        db.commit()
        committed = True
        depth = db.query(TurnVideoAnalysisDB.id).filter_by(recording_id=recording.id, status='queued').count()
        logger.info("recording_block interview_id=%s block_id=%s capture_id=%s stage=preserved latency_ms=%.1f queue_depth=%s", interview_id, block_id,
                    segment.id, (time.perf_counter() - started) * 1000, depth)
        return _receipt(block)
    finally:
        if not committed:
            db.rollback()
            _discard_saved_media(db, storage, [stored.storage_key], attempted_model=InterviewRecordingBlockDB)
