"""Idempotent media expiry; research record erasure requires a separate policy."""
from datetime import datetime, timezone
import calendar
import logging
from app.models.medical_interview import InterviewRecordingDB, RecordingStatus
from app.media.storage import get_media_storage

logger = logging.getLogger(__name__)


def media_retention_deadline(started_at, months=12):
    if not 1 <= months <= 12:
        raise ValueError("Media retention cannot exceed 12 calendar months")
    total_months = started_at.year * 12 + started_at.month - 1 + months
    year, month_index = divmod(total_months, 12)
    month = month_index + 1
    return started_at.replace(year=year, month=month,
                              day=min(started_at.day, calendar.monthrange(year, month)[1]))


def purge_expired_media(db, *, dry_run=True, now=None):
    now = now or datetime.now(timezone.utc)
    from app.core.config import settings
    recordings = []
    for recording in db.query(InterviewRecordingDB).yield_per(100):
        deadline = media_retention_deadline(recording.started_at, settings.media_retention_months)
        expiration = recording.retention_expires_at
        if expiration is None or expiration > deadline:
            expiration = deadline
            if not dry_run:
                recording.retention_expires_at = deadline
        if expiration <= now:
            recordings.append(recording)
    if dry_run:
        return len(recordings)
    db.commit()
    storage = get_media_storage()
    for recording in recordings:
        # Hide replay first; failed erasure is retried on the next run.
        recording.status = RecordingStatus.UNAVAILABLE.value
        recording.failure_code = "retention_expired"
        for asset in recording.assets:
            asset.status = "unavailable"
        db.commit()
        try:
            storage.delete_recording(recording.medical_interview_id, recording.id)
        except (OSError, ValueError):
            logger.warning("Expired media removal failed recording_id=%s; will retry", recording.id, exc_info=True)
    return len(recordings)


def purge_expired_calibration_media(db, *, dry_run=True, now=None):
    from app.models.calibration_capture import CalibrationCaptureDB
    from app.core.config import settings
    now = now or datetime.now(timezone.utc)
    expired = []
    for capture in db.query(CalibrationCaptureDB).yield_per(100):
        deadline = min(capture.retention_expires_at, media_retention_deadline(capture.created_at, settings.media_retention_months))
        if deadline <= now:
            expired.append(capture)
    if not dry_run:
        storage = get_media_storage()
        for capture in expired:
            try:
                storage.delete(capture.storage_key)
            except (OSError, ValueError):
                logger.warning("Expired calibration media removal failed capture_id=%s; will retry", capture.id, exc_info=True)
    return len(expired)


if __name__ == "__main__":
    import argparse
    from app.core.database import SessionLocal
    parser = argparse.ArgumentParser(description="Preview expired media; --apply performs erasure")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        count = purge_expired_media(db, dry_run=not args.apply)
        calibration_count = purge_expired_calibration_media(db, dry_run=not args.apply)
    print(f"Expired recording count: {count}; expired calibration count: {calibration_count}; erasure applied: {args.apply}")
