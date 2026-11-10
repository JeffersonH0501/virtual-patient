"""Transactional boundaries for an interview's independently captured segments."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func

from app.controllers.interview_lifecycle import lock_row
from app.models.medical_interview import (
    InterviewMessageDB,
    InterviewRecordingDB,
    InterviewRecordingSegmentDB,
    InterviewTurnDB,
    MedicalInterviewDB,
    SenderType,
)


def owned_interview(db, interview_id, user):
    from app.media.access import _require_owner
    interview = lock_row(db, MedicalInterviewDB, interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    _require_owner(interview, user)
    return interview


def recording_segment(db, recording, segment_id):
    segment = db.query(InterviewRecordingSegmentDB).filter_by(id=str(segment_id)).populate_existing().first() if recording is not None else None
    if segment is None or segment.recording_id != recording.id:
        raise HTTPException(status_code=404, detail="Recording segment not found")
    return segment


def lock_recording(db, interview_id):
    """Lock after the interview row, which also serializes first creation."""
    recording = db.query(InterviewRecordingDB).filter_by(medical_interview_id=interview_id).first()
    return lock_row(db, InterviewRecordingDB, recording.id) if recording is not None else None


def latest_segment(db, recording):
    return db.query(InterviewRecordingSegmentDB).filter_by(recording_id=recording.id).order_by(
        InterviewRecordingSegmentDB.sequence.desc()
    ).populate_existing().first()


def require_active_segment(db, interview_id, segment_id, *, recording=None):
    """Fence stale writers after the caller acquires the interview lock."""
    recording = recording if recording is not None else lock_recording(db, interview_id)
    current = latest_segment(db, recording) if recording is not None else None
    if current is None and segment_id is None and not (
        recording is not None and (recording.capture_config or {}).get("resume_attempt")
    ):
        return None
    if current is None or current.id != segment_id or current.sealed_at is not None:
        raise HTTPException(status_code=409, detail={"code": "stale_capture"})
    return current


def require_capture_epoch(db, interview_id, segment_id, resume_attempt_id=None, *, allow_resume=False):
    """Fence lifecycle writes as well as media writes under the interview lock."""
    recording = lock_recording(db, interview_id)
    current = latest_segment(db, recording) if recording is not None else None
    attempt = (recording.capture_config or {}).get("resume_attempt") if recording is not None else None
    if attempt:
        if not allow_resume or attempt["id"] != resume_attempt_id:
            raise HTTPException(status_code=409, detail={"code": "stale_capture"})
    elif current is not None and current.id != segment_id:
        raise HTTPException(status_code=409, detail={"code": "stale_capture"})
    return recording


def pending_patient_message(db, interview_id):
    message = db.query(InterviewMessageDB).filter_by(interview_id=interview_id).order_by(
        InterviewMessageDB.id.desc()
    ).first()
    if message is None or message.sender_type != SenderType.PATIENT.value:
        return None
    if (message.message_metadata or {}).get('playback_confirmed'):
        return None
    turn = db.query(InterviewTurnDB).filter_by(medical_interview_id=interview_id, message_id=message.id).first()
    if turn is None or (turn.timing_quality != "measured" and turn.timing_source != "tts_written"):
        return message.id
    return None


def seal_segment(db, segment, pending_patient_message_id=None):
    if segment.sealed_at is None:
        if (segment.capture_config or {}).get('mediaTransport') == 'reusable_blocks_v1':
            from app.models.recording_block import InterviewRecordingBlockDB
            segment.duration_ms = db.query(func.sum(InterviewRecordingBlockDB.duration_ms)).filter_by(capture_attempt_id=segment.id).scalar() or 0
            segment.sealed_at = datetime.now(timezone.utc)
            return segment.duration_ms
        end = db.query(func.max(InterviewTurnDB.end_ms)).filter_by(segment_id=segment.id)
        if pending_patient_message_id is not None:
            end = end.filter(InterviewTurnDB.message_id.is_distinct_from(pending_patient_message_id))
        segment.duration_ms = max(0, (end.scalar() or 0) - segment.offset_ms)
        segment.sealed_at = datetime.now(timezone.utc)
    return segment.duration_ms


