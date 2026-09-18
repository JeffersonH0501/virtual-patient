"""Single-consumer FIFO for durable per-turn nonverbal video jobs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from queue import Queue
from threading import Lock, Thread
from time import perf_counter

from app.core.database import SessionLocal
from app.media.storage import get_media_storage
from app.models.calibration import CalibrationAttemptDB, CalibrationStatus
from app.models.medical_interview import InterviewRecordingDB, TurnVideoAnalysisDB
from app.nonverbal.ccdbhg import NodAnalysis, analyze_nods
from app.nonverbal.gaze import create_tracker
from app.nonverbal.video_observations import (
    TurnWindow,
    build_turn_raw_features,
    extract_nonverbal_video_observations_parallel,
)

logger = logging.getLogger(__name__)
_jobs: Queue[str | None] = Queue()
_worker: Thread | None = None
_worker_lock = Lock()


def enqueue_turn_video_analysis(job_id: str) -> None:
    """Enqueue a durable job without creating a thread per turn."""
    _ensure_worker()
    _jobs.put(job_id)


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return
        _worker = Thread(target=_worker_loop, name="turn-video-analysis-worker", daemon=False)
        _worker.start()


def start_turn_video_worker(*, recover: bool = True) -> None:
    """Start the worker and recover durable jobs left by a previous process."""
    _ensure_worker()
    if not recover:
        return
    db = SessionLocal()
    try:
        jobs = db.query(TurnVideoAnalysisDB).filter(
            TurnVideoAnalysisDB.status.in_(("queued", "processing"))
        ).all()
        for job in jobs:
            job.status = "queued"
            job.error = None
        db.commit()
        for job in jobs:
            _jobs.put(job.id)
    finally:
        db.close()


def shutdown_turn_video_worker(timeout: float = 120.0) -> None:
    """Drain accepted work and stop the single consumer during API shutdown."""
    global _worker
    with _worker_lock:
        worker = _worker
        if worker is None:
            return
        _jobs.put(None)
    worker.join(timeout=timeout)
    if worker.is_alive():
        logger.error("turn_video_analysis result=shutdown_timeout")
        return
    with _worker_lock:
        _worker = None


def _worker_loop() -> None:
    while True:
        job_id = _jobs.get()
        try:
            if job_id is None:
                return
            _process_job(job_id)
        except Exception:  # noqa: BLE001 - isolate one turn from the FIFO.
            logger.exception("turn_video_analysis job_id=%s result=worker_error", job_id)
        finally:
            _jobs.task_done()


def _process_job(job_id: str) -> None:
    processing_started = perf_counter()
    db = SessionLocal()
    storage_key: str | None = None
    try:
        job = db.query(TurnVideoAnalysisDB).filter(TurnVideoAnalysisDB.id == job_id).first()
        if job is None or job.status == "completed":
            return
        if job.status not in {"queued", "processing"}:
            return
        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        job.error = None
        db.commit()
        storage_key = job.storage_key
        if not storage_key:
            raise FileNotFoundError("Turn video segment is unavailable")

        attempt = db.query(CalibrationAttemptDB).filter(
            CalibrationAttemptDB.medical_interview_id == job.medical_interview_id,
            CalibrationAttemptDB.status == CalibrationStatus.PASSED.value,
            CalibrationAttemptDB.is_active.is_(True),
        ).first()
        profile = attempt.profile if attempt else None
        tracker = create_tracker(affine_matrix=profile.get("affine_matrix")) if profile else create_tracker()
        observations = extract_nonverbal_video_observations_parallel(
            storage.resolve(storage_key), tracker=tracker, queue_capacity=32
        )
        try:
            nod_analysis = analyze_nods([item.shared for item in observations])
        except Exception:  # noqa: BLE001 - preserve gaze and smile for this turn.
            logger.exception("turn_video_analysis job_id=%s branch=ccdbhg result=failed", job_id)
            nod_analysis = NodAnalysis((), False, "extractor_failure")

        roi = list(job.roi_snapshots or [])
        duration_ms = max(1, job.end_ms - job.start_ms)
        window = TurnWindow(job.turn_id, 0, duration_ms, job.speaker)
        raw = build_turn_raw_features(
            observations,
            window,
            nod_analysis=nod_analysis,
            calibration_profile=profile,
            patient_roi_snapshots=roi,
        )
        job.result = raw.model_dump(mode="json")
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.storage_key = None
        db.commit()
        try:
            storage.delete(storage_key)
        except Exception:  # noqa: BLE001 - persisted analysis remains valid.
            logger.exception(
                "turn_video_analysis job_id=%s result=cleanup_failed storage_key=%s",
                job.id, storage_key,
            )
        queue_wait_ms = (
            (job.started_at - job.queued_at).total_seconds() * 1000
            if job.started_at and job.queued_at else None
        )
        logger.info(
            "turn_video_analysis job_id=%s turn_id=%s result=completed queue_wait_ms=%s processing_ms=%.3f",
            job.id, job.turn_id, queue_wait_ms, (perf_counter() - processing_started) * 1000,
        )
    except Exception as error:  # noqa: BLE001 - failure is durable and later turns continue.
        db.rollback()
        job = db.query(TurnVideoAnalysisDB).filter(TurnVideoAnalysisDB.id == job_id).first()
        if job is not None:
            job.status = "failed"
            job.error = str(error)[:2000]
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
        logger.exception("turn_video_analysis job_id=%s result=failed", job_id)
    finally:
        db.close()


def queue_depth() -> int:
    return _jobs.qsize()


def fail_pending_turn_video_jobs(db, interview_id: int, reason: str) -> int:
    """Make queued jobs terminal; an already-processing native call may finish safely."""
    storage = get_media_storage()
    jobs = db.query(TurnVideoAnalysisDB).filter(
        TurnVideoAnalysisDB.medical_interview_id == interview_id,
        TurnVideoAnalysisDB.status == "queued",
    ).all()
    for job in jobs:
        if job.storage_key:
            try:
                storage.delete(job.storage_key)
            except Exception:  # noqa: BLE001 - status transition must still persist.
                logger.exception("turn_video_analysis job_id=%s result=cancel_cleanup_failed", job.id)
        job.storage_key = None
        job.status = "failed"
        job.error = reason
        job.completed_at = datetime.now(timezone.utc)
    db.commit()
    return len(jobs)
