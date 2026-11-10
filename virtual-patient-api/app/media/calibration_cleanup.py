"""Erase abandoned calibration references and unregistered private files."""
import logging
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import func
from app.controllers.interview_lifecycle import lock_row
from app.media.calibration import discard_capture_references
from app.media.storage import get_media_storage
from app.models.calibration_capture import CalibrationCaptureDB
from app.models.medical_interview import MedicalInterviewDB
from app.models.medical_interview import InterviewStatus, TurnVideoAnalysisDB
from app.models.processing_job import InterviewProcessingJobDB
from app.models.teacher_grading import TeacherAssignmentDB

logger = logging.getLogger(__name__)
CALIBRATION_DRAFT_TTL = timedelta(hours=1)
ORPHAN_FILE_GRACE = timedelta(minutes=5)


def cleanup_abandoned_interview_drafts(db, *, dry_run=True, now=None):
    """Remove empty, discarded or expired preparation drafts under the interview lock."""
    from app.controllers.administrative_deletion import delete_parent

    now = now or datetime.now(timezone.utc)
    removed = 0
    identifiers = [identifier for (identifier,) in db.query(MedicalInterviewDB.id).filter(
        MedicalInterviewDB.start_time.is_(None), MedicalInterviewDB.status == InterviewStatus.IN_PROGRESS)]
    for identifier in identifiers:
        try:
            interview = lock_row(db, MedicalInterviewDB, identifier)
            if (interview is None or interview.start_time is not None or interview.status != InterviewStatus.IN_PROGRESS
                    or interview.recording is not None or interview.messages or interview.turns or interview.hypotheses
                    or interview.session_notes or interview.interview_evaluations or interview.progress_summary is not None
                    or interview.teacher_feedback):
                continue
            metadata = interview.interview_metadata or {}
            if metadata.get("calibration_test") is True or interview.created_at is None:
                continue
            if (db.query(TeacherAssignmentDB).filter_by(interview_id=identifier).first()
                    or db.query(InterviewProcessingJobDB).filter_by(medical_interview_id=identifier).first()
                    or db.query(TurnVideoAnalysisDB).filter_by(medical_interview_id=identifier).first()):
                continue
            last_capture = db.query(func.max(CalibrationCaptureDB.created_at)).filter_by(medical_interview_id=identifier).scalar()
            activity = max(interview.created_at, last_capture or interview.created_at)
            try:
                value = metadata.get("calibration_activity_at")
                if value:
                    activity = max(activity, datetime.fromisoformat(value))
            except (ValueError, TypeError):
                continue
            if metadata.get("calibration_discarded") is not True and now - activity < CALIBRATION_DRAFT_TTL:
                continue
            if not dry_run:
                discard_capture_references(db, interview)
                interview = lock_row(db, MedicalInterviewDB, identifier)
                if (interview is None or interview.start_time is not None or interview.recording is not None
                        or interview.messages or interview.turns or interview.hypotheses or interview.session_notes
                        or interview.interview_evaluations or interview.progress_summary is not None or interview.teacher_feedback):
                    continue
                delete_parent(db, interview, "interview")
            removed += 1
        except HTTPException as error:
            if error.status_code not in (409, 503):
                raise
            logger.info("Abandoned interview draft cleanup deferred interview_id=%s", identifier)
        finally:
            db.rollback()
    return removed


def cleanup_calibration_references(db, *, dry_run=True, now=None):
    now = now or datetime.now(timezone.utc)
    storage = get_media_storage()
    counts = {"calibrations": 0, "orphan_files": 0}
    identifiers = [identifier for (identifier,) in db.query(MedicalInterviewDB.id).filter(MedicalInterviewDB.start_time.is_(None))]
    for identifier in identifiers:
        try:
            interview = lock_row(db, MedicalInterviewDB, identifier)
            if interview is None or interview.start_time is not None or interview.recording is not None or interview.messages:
                continue
            metadata = interview.interview_metadata or {}
            if metadata.get("calibration_test") is True:
                continue
            last_capture = db.query(func.max(CalibrationCaptureDB.created_at)).filter_by(medical_interview_id=identifier).scalar()
            discarded = metadata.get("calibration_discarded") is True
            has_files = (storage.root/"interviews"/str(identifier)/"calibration").exists()
            if not last_capture and not metadata.get("calibration") and not (discarded and has_files):
                continue
            activity = max(interview.created_at, last_capture or interview.created_at)
            try:
                reported = datetime.fromisoformat(metadata.get("calibration_activity_at", ""))
                if activity <= reported <= now:
                    activity = reported
            except (ValueError, TypeError):
                pass
            if not discarded and interview.status == "in_progress" and now - activity < CALIBRATION_DRAFT_TTL:
                continue
            if not dry_run:
                discard_capture_references(db, interview)
            counts["calibrations"] += 1
        except HTTPException as error:
            if error.status_code not in (409, 503):
                raise
            logger.info("Calibration draft cleanup deferred interview_id=%s", identifier)
        finally:
            db.rollback()

    root = storage.root / "interviews"
    for directory in root.glob("*/calibration"):
        if not directory.parent.name.isdecimal() or directory.is_symlink():
            continue
        identifier = int(directory.parent.name)
        try:
            # Writers hold this same lock until both file publication and DB commit.
            lock_row(db, MedicalInterviewDB, identifier)
            referenced = {key for (key,) in db.query(CalibrationCaptureDB.storage_key).filter_by(medical_interview_id=identifier)}
            for path in directory.iterdir():
                if not path.is_file():
                    continue
                key = path.relative_to(storage.root).as_posix()
                if key in referenced or now.timestamp() - path.stat().st_mtime < ORPHAN_FILE_GRACE.total_seconds():
                    continue
                if not dry_run:
                    storage.delete(key)
                counts["orphan_files"] += 1
        except FileNotFoundError:
            pass
        except HTTPException as error:
            if error.status_code != 409:
                raise
        except (OSError, ValueError):
            logger.warning("Calibration orphan cleanup deferred interview_id=%s", identifier, exc_info=True)
        finally:
            db.rollback()
    return counts
