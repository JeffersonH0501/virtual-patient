"""Launch crash-prone native analysis outside the API worker process."""

from __future__ import annotations

import asyncio
import logging
import sys
from time import perf_counter

from app.core.database import SessionLocal
from app.models.medical_interview import InterviewRecordingDB
from app.utils.runtime_metrics import current_rss_mb, process_id

logger = logging.getLogger(__name__)


async def process_multimodal_interview_isolated(
    interview_id: int,
    recording_id: str,
) -> None:
    """Run the full pipeline in a child process so native aborts cannot kill the API."""
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
    )
    try:
        return_code = await asyncio.wait_for(process.wait(), timeout=1800)
    except TimeoutError:
        process.kill()
        await process.wait()
        return_code = -1
        logger.error(
            "multimodal_pipeline interview_id=%s recording_id=%s result=worker_timeout",
            interview_id,
            recording_id,
        )
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
