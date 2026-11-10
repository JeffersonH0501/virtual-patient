"""Preserve calibration uploads before analysis, with content-based retries."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import HTTPException, UploadFile
from app.controllers.interview_lifecycle import lock_row
from app.core.config import settings
from app.media.retention import media_retention_deadline
from app.media.storage import get_media_storage
from app.models.calibration_capture import CalibrationCaptureDB
from app.models.medical_interview import InterviewRecordingDB, MedicalInterviewDB


def require_pending_resume(db, interview, attempt_id):
    recording = db.query(InterviewRecordingDB).filter_by(medical_interview_id=interview.id).with_for_update().first()
    attempt = (recording.capture_config or {}).get("resume_attempt") if recording else None
    if interview.status != "in_progress" or not attempt or attempt.get("id") != attempt_id:
        raise HTTPException(409, "Resume attempt is no longer active")
    return recording, attempt


def discard_capture_references(db, interview):
    """Invalidate temporary calibration first; physical erasure remains retryable."""
    if (interview.interview_metadata or {}).get("calibration_test") is True:
        raise HTTPException(409, "Saved calibration tests cannot be discarded as temporary preparation")
    if interview.start_time is not None:
        raise HTTPException(409, "Started interview calibration cannot be discarded")
    metadata = dict(interview.interview_metadata or {})
    metadata.pop("calibration", None)
    metadata.pop("calibration_activity_at", None)
    metadata["calibration_discarded"] = True
    interview.interview_metadata = metadata
    for capture in db.query(CalibrationCaptureDB).filter_by(medical_interview_id=interview.id):
        db.delete(capture)
    identifier = interview.id
    # Commit invalidation before erasure so late uploads/results cannot restore it.
    db.commit()
    try:
        get_media_storage().delete_recording(identifier, "calibration")
    except (OSError, ValueError) as error:
        raise HTTPException(503, "Calibration erasure is pending; retry") from error


async def preserve_capture(db, user_id, interview_id, stage, path, content_type, duration_ms, metadata, resume_attempt_id=None):
    interview = lock_row(db, MedicalInterviewDB, interview_id)
    if interview is None or interview.user_id != user_id:
        raise HTTPException(404, "Interview not found")
    if resume_attempt_id is not None:
        require_pending_resume(db, interview, resume_attempt_id)
        metadata = {**metadata, "resume_attempt_id": resume_attempt_id}
    elif interview.start_time is not None or interview.status != "in_progress":
        raise HTTPException(409, "Calibration capture requires an unstarted interview")
    if (interview.interview_metadata or {}).get("calibration_discarded"):
        raise HTTPException(410, "Calibration preparation was discarded")
    now = datetime.now(timezone.utc)
    interview.interview_metadata = {**(interview.interview_metadata or {}), "calibration_activity_at": now.isoformat()}
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    identity = json.dumps([stage, duration_ms, content_type, metadata, digest], sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(identity.encode()).hexdigest()
    capture = db.query(CalibrationCaptureDB).filter_by(medical_interview_id=interview_id, fingerprint=fingerprint).first()
    if capture is not None:
        db.commit()
        return capture
    identifier = str(uuid4())
    storage = get_media_storage()
    stored = await storage.save_upload(interview_id, "calibration", "student_video", UploadFile(file=path.open("rb")), path.suffix)
    capture = CalibrationCaptureDB(id=identifier, medical_interview_id=interview_id, fingerprint=fingerprint,
        stage=stage, storage_key=stored.storage_key, content_type=content_type,
        size_bytes=stored.size_bytes, sha256=stored.sha256, duration_ms=duration_ms,
        capture_metadata=metadata, created_at=now,
        retention_expires_at=media_retention_deadline(now, settings.media_retention_months))
    try:
        db.add(capture)
        db.commit()
        db.refresh(capture)
    except BaseException:
        db.rollback()
        storage.delete(stored.storage_key)
        raise
    return capture
