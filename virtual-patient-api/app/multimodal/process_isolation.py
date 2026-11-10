"""Launch crash-prone native analysis outside the API worker process."""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from time import perf_counter
from weakref import WeakKeyDictionary

from app.core.database import SessionLocal, engine
from sqlalchemy import text
from app.models.medical_interview import InterviewRecordingDB
from app.utils.runtime_metrics import current_rss_mb, process_id

logger = logging.getLogger(__name__)
PIPELINE_LOCK_BASE = 846217310
PIPELINE_CAPACITY = 2
_local_slots = WeakKeyDictionary()


@asynccontextmanager
async def pipeline_slot():
    """Share the existing two-pipeline bound across all API processes."""
    loop = asyncio.get_running_loop()
    semaphore = _local_slots.setdefault(loop, asyncio.Semaphore(PIPELINE_CAPACITY))
    async with semaphore:
        async with _database_pipeline_slot():
            yield


@asynccontextmanager
async def _database_pipeline_slot():
    """Only local holders consume SQL connections while awaiting global capacity."""
    key = None
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        try:
            while key is None:
                for candidate in range(PIPELINE_LOCK_BASE, PIPELINE_LOCK_BASE + PIPELINE_CAPACITY):
                    if connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": candidate}).scalar():
                        key = candidate
                        break
                if key is None:
                    await asyncio.sleep(.05)
            yield
        finally:
            if key is not None:
                try:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                except Exception:
                    connection.invalidate()
                    raise


async def process_multimodal_interview_isolated(
    interview_id: int,
    recording_id: str,
    *,
    use_full_video: bool = True,
) -> None:
    """Run the full pipeline in a child process so native aborts cannot kill the API."""
    async with pipeline_slot():
        await _process_multimodal_interview_isolated(interview_id, recording_id, use_full_video=use_full_video)


async def _process_multimodal_interview_isolated(interview_id, recording_id, *, use_full_video):
    started_at = perf_counter()
    logger.info(
        "performance_event component=multimodal_pipeline operation=isolated_process phase=start "
        "interview_id=%s recording_id=%s parent_pid=%s parent_rss_mb=%s",
        interview_id, recording_id, process_id(), current_rss_mb(),
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.multimodal.isolated_worker",
        "pipeline",
        str(interview_id),
        recording_id,
        *(["--full-video"] if use_full_video else []),
    )
    try:
        return_code = await asyncio.wait_for(process.wait(), timeout=22200)
    except TimeoutError:
        process.kill()
        await process.wait()
        return_code = -1
        logger.error(
            "multimodal_pipeline interview_id=%s recording_id=%s result=worker_timeout",
            interview_id,
            recording_id,
        )
    except asyncio.CancelledError:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    if return_code == 0:
        logger.info(
            "performance_event component=multimodal_pipeline operation=isolated_process phase=complete "
            "interview_id=%s recording_id=%s duration_ms=%.3f return_code=0 parent_rss_mb=%s",
            interview_id, recording_id, (perf_counter() - started_at) * 1000, current_rss_mb(),
        )
        return

    logger.error(
        "multimodal_pipeline interview_id=%s recording_id=%s result=worker_crashed "
        "return_code=%s duration_ms=%.3f parent_rss_mb=%s",
        interview_id,
        recording_id,
        return_code,
        (perf_counter() - started_at) * 1000,
        current_rss_mb(),
    )
    db = SessionLocal()
    try:
        recording = db.query(InterviewRecordingDB).filter(
            InterviewRecordingDB.id == recording_id,
        ).first()
        if recording is not None:
            capture_config = dict(recording.capture_config or {})
            capture_config["observation_processing"] = {
                "status": "failed",
                "stage": "finished",
                "reason": "native_worker_failed",
            }
            recording.capture_config = capture_config
            db.commit()
    finally:
        db.close()
