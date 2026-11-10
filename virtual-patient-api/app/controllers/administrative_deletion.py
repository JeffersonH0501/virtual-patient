"""Transactional administrative erasure with recoverable local media staging."""
import hashlib
import json
import logging
import os
import shutil
import uuid
from sqlalchemy import text
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError
from app.media.storage import get_media_storage
from app.models.medical_interview import MedicalInterviewDB, InterviewRecordingDB, TurnVideoAnalysisDB, InterviewStatus
from app.models.processing_job import InterviewProcessingJobDB
from app.models.user import UserDB
from app.models.clinical_case import ClinicalCaseDB
from app.models.teacher_feedback import TeacherFeedbackDB

logger = logging.getLogger(__name__)


def operation_lock(db, operation_id, wait):
    key = int.from_bytes(hashlib.sha256(operation_id.encode()).digest()[:8], "big", signed=True)
    statement = "SELECT pg_advisory_xact_lock(:key)" if wait else "SELECT pg_try_advisory_xact_lock(:key)"
    return db.execute(text(statement), {"key": key}).scalar()


def delete_interview_graph(db, interview):
    if interview.progress_summary is not None:
        interview.progress_summary = None
        db.flush()
    db.delete(interview)


def recover_staged_media(db):
    storage = get_media_storage()
    staging = storage.root / ".deletions"
    if not staging.exists():
        return
    for folder in staging.iterdir():
        if not folder.is_dir() or not operation_lock(db, folder.name, False):
            continue
        manifest = folder / "manifest.json"
        if not manifest.exists():
            continue
        try:
            for interview_id in json.loads(manifest.read_text()):
                source = folder / str(int(interview_id))
                destination = storage.root / "interviews" / str(int(interview_id))
                if source.exists() and db.get(MedicalInterviewDB, interview_id):
                    if destination.exists():
                        raise RuntimeError("Media restoration destination already exists")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    source.rename(destination)
            shutil.rmtree(folder)
        except Exception:
            logger.exception("Administrative media recovery failed operation_id=%s", folder.name)


def delete_parent(db, parent, kind):
    query = db.query(MedicalInterviewDB).filter(
        MedicalInterviewDB.user_id == parent.id if kind == "user" else MedicalInterviewDB.id == parent.id if kind == "interview" else MedicalInterviewDB.clinical_case_id == parent.id,
    )
    try:
        interviews = query.order_by(MedicalInterviewDB.id).with_for_update(nowait=True).all()
    except OperationalError as error:
        if getattr(error.orig, "pgcode", None) != "55P03":
            raise
        db.rollback()
        raise HTTPException(409, "Another interview operation is in progress; retry") from error
    identifiers = [item.id for item in interviews]
    if kind == "case" and any(item.user.organization_id != parent.organization_id for item in interviews):
        raise HTTPException(409, "Case has interviews outside the permitted organization")
    if any(
        item.status == InterviewStatus.PROCESSING or (
            item.status == InterviewStatus.IN_PROGRESS and not (
                item.start_time is None and item.recording is None and not item.messages
                and (item.interview_metadata or {}).get("calibration_discarded") is True
            )
        )
        for item in interviews
    ):
        raise HTTPException(409, "Wait for active interviews to finish")
    if identifiers:
        pending = db.query(InterviewProcessingJobDB).filter(InterviewProcessingJobDB.medical_interview_id.in_(identifiers), InterviewProcessingJobDB.status.in_(["queued", "processing"])).first()
        video = db.query(TurnVideoAnalysisDB).filter(TurnVideoAnalysisDB.medical_interview_id.in_(identifiers), TurnVideoAnalysisDB.status.in_(["queued", "processing"])).first()
        recordings = db.query(InterviewRecordingDB).filter(InterviewRecordingDB.medical_interview_id.in_(identifiers)).all()
        if pending or video or any((item.capture_config or {}).get(key, {}).get("status") in ("queued", "processing") for item in recordings for key in ("observation_processing", "evaluation_processing")):
            raise HTTPException(409, "Wait for interview processing to finish")
    storage = get_media_storage()
    operation_id = uuid.uuid4().hex
    operation_lock(db, operation_id, True)
    folder = storage.root / ".deletions" / operation_id
    folder.mkdir(parents=True)
    manifest = folder / "manifest.json"
    with manifest.open("w") as stream:
        json.dump(identifiers, stream)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        for interview in interviews:
            source = storage.root / "interviews" / str(interview.id)
            if source.exists():
                source.rename(folder / str(interview.id))
            delete_interview_graph(db, interview)
        if kind == "user":
            db.query(ClinicalCaseDB).filter(ClinicalCaseDB.created_by == parent.id).update({"created_by": None}, synchronize_session=False)
            db.query(TeacherFeedbackDB).filter(TeacherFeedbackDB.teacher_id == parent.id).delete(synchronize_session=False)
        db.flush()
        if kind != "interview":
            db.delete(parent)
        db.commit()
    except Exception as error:
        db.rollback()
        recover_staged_media(db)
        raise HTTPException(500, "Deletion failed; the operation can be retried") from error
    try:
        shutil.rmtree(folder)
    except OSError:
        logger.exception("Media purge deferred for recovery operation_id=%s", operation_id)
