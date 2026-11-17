"""Bounded durable scheduling with PostgreSQL session locks across API workers."""
import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from sqlalchemy import case, text, tuple_, or_
from sqlalchemy.orm import aliased
from app.core.database import SessionLocal, engine
from app.models.processing_job import InterviewProcessingJobDB

logger = logging.getLogger(__name__)
JOB_KINDS = {"completion", "pipeline", "observations", "evaluation", "learning_moments", "replay_preview"}
CANDIDATE_BATCH_SIZE = 32
BACKGROUND_SLOT_LOCK = 846217320
# A transient failure (OOM-killed child, timeout, dropped DB connection) must not
# permanently lose a participant's analysis. Reschedule the job until this many
# attempts have been made, then mark it terminally failed.
MAX_JOB_ATTEMPTS = 3
SUCCESSFUL_PHASES = {"complete", "partial", "unavailable"}
PROCESSING_PHASES = {
    "pipeline": ("observation_processing",),
    "observations": ("observation_processing", "evaluation_processing"),
    "evaluation": ("evaluation_processing",),
}


def _expire_media():
    from app.media.retention import purge_expired_media, purge_expired_calibration_media
    from app.controllers.administrative_deletion import recover_staged_media
    with SessionLocal() as db:
        recover_staged_media(db)
        return purge_expired_media(db, dry_run=False) + purge_expired_calibration_media(db, dry_run=False)


def _clean_calibration():
    from app.media.calibration_cleanup import cleanup_calibration_references, cleanup_abandoned_interview_drafts
    with SessionLocal() as db:
        result = cleanup_calibration_references(db, dry_run=False)
        result["interview_drafts"] = cleanup_abandoned_interview_drafts(db, dry_run=False)
        return result


def stage_processing_job(db, interview_id, kind, payload):
    if kind not in JOB_KINDS:
        raise ValueError("Unsupported interview processing job")
    job = InterviewProcessingJobDB(medical_interview_id=interview_id, kind=kind, payload=payload)
    db.add(job)
    return job


async def _dispatch(kind, interview_id, payload):
    if kind == "completion":
        from app.routers.medical_interviews import _evaluate_and_complete_interview
        await _evaluate_and_complete_interview(interview_id, payload["language"], payload.get("patient_gender"))
    elif kind == "pipeline":
        from app.multimodal.process_isolation import process_multimodal_interview_isolated
        await process_multimodal_interview_isolated(interview_id, payload["recording_id"])
    elif kind == "replay_preview":
        from app.media.replay_preview import build_replay_preview
        await asyncio.to_thread(build_replay_preview, interview_id, payload["recording_id"])
    elif kind == "learning_moments":
        from app.multimodal.learning_moments import generate_learning_moments
        await generate_learning_moments(interview_id, payload["recording_id"], payload.get("force", False))
    else:
        from app.multimodal.reprocess import reprocess_interview_observations, reprocess_interview_evaluation
        operation = reprocess_interview_observations if kind == "observations" else reprocess_interview_evaluation
        await operation(interview_id, payload["recording_id"])


def _succeeded(db, job):
    from app.models.medical_interview import MedicalInterviewDB, InterviewRecordingDB
    if job.kind == "completion":
        interview = db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == job.medical_interview_id).first()
        return bool(interview and getattr(interview.status, "value", interview.status) == "completed")
    recording = db.query(InterviewRecordingDB).filter(InterviewRecordingDB.id == job.payload["recording_id"]).first()
    if not recording:
        return False
    capture = recording.capture_config or {}
    if job.kind == "learning_moments":
        return capture.get("learning_moments", {}).get("status") == "completed"
    if job.kind == "replay_preview":
        return capture.get("replay_preview", {}).get("status") in {"ready", "unavailable"}
    if job.kind != "evaluation" and capture.get("observation_processing", {}).get("status") not in SUCCESSFUL_PHASES:
        return False
    return job.kind == "pipeline" or capture.get("evaluation_processing", {}).get("status") in SUCCESSFUL_PHASES


def _close_failed_phases(db, job):
    from app.models.medical_interview import InterviewRecordingDB

    phases = PROCESSING_PHASES.get(job.kind)
    if not phases and job.kind != "replay_preview":
        return
    recording = db.get(InterviewRecordingDB, job.payload["recording_id"], with_for_update=True)
    if recording is None:
        return
    capture = dict(recording.capture_config or {})
    if job.kind == "replay_preview":
        capture["replay_preview"] = {**capture.get("replay_preview", {}), "status": "failed"}
        recording.capture_config = capture
        return
    for phase in phases:
        if capture.get(phase, {}).get("status") in {"queued", "processing"}:
            capture[phase] = {"status": "failed", "stage": "finished", "reason": "technical_processing_failure"}
    recording.capture_config = capture


async def _run(job_id):
    key = int.from_bytes(hashlib.sha256(job_id.encode()).digest()[:8], "big", signed=True)
    with engine.connect() as connection:
        locked = connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar()
        if not locked:
            return False
        try:
            with SessionLocal() as db:
                job = db.query(InterviewProcessingJobDB).filter(InterviewProcessingJobDB.id == job_id).first()
                if not job or job.status not in {"queued", "processing"}:
                    return False
                job.status = "processing"
                job.attempts += 1
                kind, interview_id, payload = job.kind, job.medical_interview_id, dict(job.payload)
                db.commit()
            failed = False
            operation = asyncio.create_task(_dispatch(kind, interview_id, payload))
            try:
                while not operation.done():
                    await asyncio.wait({operation}, timeout=1)
                    try:
                        connection.execute(text("SELECT 1"))
                    except Exception:
                        # A transient keepalive error (recycle, network blip) must
                        # not fail an otherwise-healthy job; the advisory lock is
                        # reasserted on the next poll and the work keeps running.
                        logger.warning("Interview processing keepalive hiccup job_id=%s kind=%s", job_id, kind)
                await operation
            except asyncio.CancelledError:
                raise  # Leave recoverable work pending after shutdown.
            except Exception:
                logger.error("Interview processing job failed job_id=%s kind=%s", job_id, kind)
                failed = True
            finally:
                if not operation.done():
                    operation.cancel()
                    await asyncio.gather(operation, return_exceptions=True)
            with SessionLocal() as db:
                job = db.query(InterviewProcessingJobDB).filter(InterviewProcessingJobDB.id == job_id).first()
                if job:
                    if not failed and _succeeded(db, job):
                        job.status = "completed"
                        job.error_code = None
                        job.completed_at = datetime.now(timezone.utc)
                    elif job.attempts < MAX_JOB_ATTEMPTS:
                        # Recoverable: requeue the same row and leave the interview
                        # phases open so a retry can still complete the analysis.
                        job.status = "queued"
                        job.error_code = None
                    else:
                        job.status = "failed"
                        job.error_code = "technical_processing_failure"
                        job.completed_at = datetime.now(timezone.utc)
                        _close_failed_phases(db, job)
                    db.commit()
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
    return True


def _select_job_batch(cursor):
    """One page of runnable jobs, taken under the shared slot lock only."""
    job = InterviewProcessingJobDB
    with engine.connect() as connection:
        params = {"key": BACKGROUND_SLOT_LOCK}
        if not connection.execute(text("SELECT pg_try_advisory_lock(:key)"), params).scalar():
            return None
        try:
            with SessionLocal() as db:
                # The replay preview goes first: the student watches its progress while self-assessing.
                priority = case((job.kind == "replay_preview", 0), else_=1)
                candidates = db.query(priority.label("priority"), job.queued_at, job.id).filter(job.status.in_(["queued", "processing"]))
                dependency = aliased(InterviewProcessingJobDB)
                unfinished_media = db.query(dependency.id).filter(
                    dependency.medical_interview_id == job.medical_interview_id,
                    dependency.kind == "pipeline",
                    dependency.status.in_(["queued", "processing"]),
                ).exists()
                candidates = candidates.filter(or_(job.kind != "completion", ~unfinished_media))
                if cursor is not None:
                    candidates = candidates.filter(tuple_(priority, job.queued_at, job.id) > tuple_(*cursor))
                return candidates.order_by(priority, job.queued_at, job.id).limit(CANDIDATE_BATCH_SIZE).all()
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), params)


async def _run_next():
    """Start one runnable job, not blocking other processes while it runs.

    The shared slot lock guards only candidate selection; job exclusivity is
    enforced by the per-job advisory lock inside ``_run``. Releasing the slot
    lock before running means a slow job (e.g. a long pipeline) no longer blocks
    replay-preview, evaluation or learning-moments jobs for other interviews.
    """
    cursor = None
    while True:
        batch = await asyncio.to_thread(_select_job_batch, cursor)
        if not batch:
            return
        for _, _, identifier in batch:
            if await _run(identifier):
                return
        if len(batch) < CANDIDATE_BATCH_SIZE:
            return
        cursor = tuple(batch[-1])
        await asyncio.sleep(0)


async def run_processing_jobs():
    running = set()
    next_retention_check = 0
    next_calibration_cleanup = 0
    try:
        while True:
            from app.core.config import settings
            if asyncio.get_running_loop().time() >= next_calibration_cleanup:
                try:
                    await asyncio.to_thread(_clean_calibration)
                except Exception:
                    logger.error("Calibration cleanup failed; retrying at the next scheduled check", exc_info=True)
                next_calibration_cleanup = asyncio.get_running_loop().time() + 300
            if settings.media_retention_months and asyncio.get_running_loop().time() >= next_retention_check:
                try:
                    await asyncio.to_thread(_expire_media)
                except Exception:
                    logger.error("Media expiry failed; retrying at the next scheduled check")
                next_retention_check = asyncio.get_running_loop().time() + 3600
            for task in {task for task in running if task.done()}:
                if not task.cancelled() and task.exception():
                    logger.error("Interview processing runner failed; retrying", exc_info=task.exception())
                running.remove(task)
            if not running:
                running.add(asyncio.create_task(_run_next()))
            await asyncio.sleep(1)
    finally:
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)
