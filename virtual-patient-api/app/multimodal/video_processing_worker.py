"""Single internal coordinator for all backend visual-processing requests."""

from __future__ import annotations

import asyncio
import itertools
import logging
import os
import tempfile
from concurrent.futures import Future
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, PriorityQueue
from threading import Event, Lock, Thread
from time import perf_counter
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.models.calibration import (
    CameraCalibrationMetadata,
    CalibrationCaptureMetadata,
    GazeCalibrationMetadata,
)
from app.models.medical_interview import TurnVideoAnalysisDB, TurnVideoAnalysisStatus
from app.multimodal.constants import TURN_VIDEO_WORKER_IDLE_TIMEOUT_SECONDS
from app.multimodal.turn_video_queue import _PersistentTurnVideoWorker, _mark_job_failed
from app.utils.runtime_metrics import current_rss_mb, process_id

logger = logging.getLogger(__name__)
MAX_CALIBRATION_BYTES = 100 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
TURN_JOB_POLL_SECONDS = 0.5
ADVISORY_LOCK_ID = 8_642_091_731
INTERACTIVE_PRIORITY = 0
BACKGROUND_PRIORITY = 1


@dataclass(frozen=True)
class CalibrationJob:
    request_id: str
    mode: Literal["video", "gaze", "camera"]
    media_path: Path
    metadata: dict
    future: Future[dict]
    queued_at: float


@dataclass(frozen=True)
class WarmupJob:
    request_id: str
    future: Future[None]
    queued_at: float


_jobs: PriorityQueue[tuple[int, int, CalibrationJob | WarmupJob | str | None]] = PriorityQueue()
_sequence = itertools.count()
_scheduled_turn_ids: set[str] = set()
_scheduled_lock = Lock()
_stop_event = Event()
_processor_thread: Thread | None = None
_poller_thread: Thread | None = None
_advisory_connection = None


def _enqueue(priority: int, payload: CalibrationJob | WarmupJob | str | None) -> None:
    _jobs.put((priority, next(_sequence), payload))


def _recover_jobs() -> None:
    db = SessionLocal()
    try:
        jobs = db.query(TurnVideoAnalysisDB).filter(
            TurnVideoAnalysisDB.status.in_((
                TurnVideoAnalysisStatus.QUEUED.value,
                TurnVideoAnalysisStatus.PROCESSING.value,
            ))
        ).all()
        for job in jobs:
            job.status = TurnVideoAnalysisStatus.QUEUED.value
            job.started_at = None
            job.completed_at = None
            job.error = None
        db.commit()
    finally:
        db.close()


def _poll_turn_jobs() -> None:
    while not _stop_event.is_set():
        db = SessionLocal()
        try:
            job_ids = [
                row[0]
                for row in db.query(TurnVideoAnalysisDB.id).filter(
                    TurnVideoAnalysisDB.status == TurnVideoAnalysisStatus.QUEUED.value
                ).order_by(TurnVideoAnalysisDB.queued_at).all()
            ]
        except Exception:  # noqa: BLE001 - retry transient database failures.
            logger.exception("video_processing_worker event=turn_poll_failed")
            job_ids = []
        finally:
            db.close()
        with _scheduled_lock:
            for job_id in job_ids:
                if job_id in _scheduled_turn_ids:
                    continue
                _scheduled_turn_ids.add(job_id)
                _enqueue(BACKGROUND_PRIORITY, job_id)
        _stop_event.wait(TURN_JOB_POLL_SECONDS)


def _delete_temp(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("video_processing_worker event=calibration_temp_delete_failed")


def _processor_loop() -> None:
    native_worker: _PersistentTurnVideoWorker | None = None
    while True:
        try:
            priority, _, payload = _jobs.get(
                timeout=TURN_VIDEO_WORKER_IDLE_TIMEOUT_SECONDS
            )
        except Empty:
            if native_worker is not None:
                native_worker.close()
                native_worker = None
                logger.info(
                    "performance_event component=video_processing_worker "
                    "operation=native_process phase=idle_release idle_seconds=%s rss_mb=%s",
                    TURN_VIDEO_WORKER_IDLE_TIMEOUT_SECONDS,
                    current_rss_mb(),
                )
            continue

        try:
            if payload is None:
                return
            reused_worker = native_worker is not None
            if native_worker is None:
                native_worker = _PersistentTurnVideoWorker()

            started_at = perf_counter()
            if isinstance(payload, WarmupJob):
                native_worker.warmup(payload.request_id)
                payload.future.set_result(None)
                logger.info(
                    "performance_event component=video_processing_worker "
                    "operation=warmup phase=complete request_id=%s priority=%s "
                    "queue_wait_ms=%.3f duration_ms=%.3f reused_worker=%s "
                    "worker_pid=%s rss_mb=%s",
                    payload.request_id,
                    priority,
                    (started_at - payload.queued_at) * 1000,
                    (perf_counter() - started_at) * 1000,
                    reused_worker,
                    process_id(),
                    current_rss_mb(),
                )
            elif isinstance(payload, CalibrationJob):
                result = native_worker.process_calibration(
                    payload.request_id,
                    payload.mode,
                    payload.media_path,
                    payload.metadata,
                )
                payload.future.set_result(result)
                logger.info(
                    "performance_event component=video_processing_worker "
                    "operation=calibration phase=complete request_id=%s mode=%s "
                    "priority=%s queue_wait_ms=%.3f processing_ms=%.3f reused_worker=%s "
                    "worker_pid=%s rss_mb=%s",
                    payload.request_id,
                    payload.mode,
                    priority,
                    (started_at - payload.queued_at) * 1000,
                    (perf_counter() - started_at) * 1000,
                    reused_worker,
                    process_id(),
                    current_rss_mb(),
                )
            else:
                status = native_worker.process_job(payload)
                logger.info(
                    "performance_event component=video_processing_worker "
                    "operation=turn_video phase=complete job_id=%s priority=%s "
                    "processing_ms=%.3f status=%s reused_worker=%s worker_pid=%s rss_mb=%s",
                    payload,
                    priority,
                    (perf_counter() - started_at) * 1000,
                    status,
                    reused_worker,
                    process_id(),
                    current_rss_mb(),
                )
        except Exception as error:  # noqa: BLE001 - isolate one job from the queue.
            logger.exception("video_processing_worker event=job_failed")
            if isinstance(payload, (CalibrationJob, WarmupJob)) and not payload.future.done():
                payload.future.set_exception(error)
            elif isinstance(payload, str):
                _mark_job_failed(payload, str(error))
            if native_worker is not None:
                native_worker.close()
                native_worker = None
        finally:
            if isinstance(payload, CalibrationJob):
                _delete_temp(payload.media_path)
            elif isinstance(payload, str):
                with _scheduled_lock:
                    _scheduled_turn_ids.discard(payload)
            _jobs.task_done()
            if payload is None and native_worker is not None:
                native_worker.close()


def _start() -> None:
    global _advisory_connection, _processor_thread, _poller_thread
    _stop_event.clear()
    _advisory_connection = engine.connect()
    try:
        acquired = bool(
            _advisory_connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": ADVISORY_LOCK_ID},
            )
        )
        if not acquired:
            raise RuntimeError(
                "Another video-processing worker already owns the singleton lock"
            )
        _recover_jobs()
    except Exception:
        _advisory_connection.close()
        _advisory_connection = None
        raise
    _processor_thread = Thread(
        target=_processor_loop,
        name="video-processing-scheduler",
        daemon=False,
    )
    _poller_thread = Thread(
        target=_poll_turn_jobs,
        name="video-processing-db-poller",
        daemon=False,
    )
    _processor_thread.start()
    _poller_thread.start()


def _shutdown() -> None:
    global _advisory_connection, _processor_thread, _poller_thread
    _stop_event.set()
    if _poller_thread is not None:
        _poller_thread.join(timeout=5)
    _jobs.join()
    _enqueue(99, None)
    if _processor_thread is not None:
        _processor_thread.join(timeout=120)
    _poller_thread = None
    _processor_thread = None
    if _advisory_connection is not None:
        _advisory_connection.close()
        _advisory_connection = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    _start()
    try:
        yield
    finally:
        await asyncio.to_thread(_shutdown)


app = FastAPI(title="Video Processing Worker", lifespan=lifespan)


def _authorize(token: str | None) -> None:
    if not token or token != settings.video_processing_worker_token:
        raise HTTPException(status_code=403, detail="Invalid internal worker token")


@app.get("/health")
async def health() -> dict:
    processor_alive = bool(_processor_thread and _processor_thread.is_alive())
    poller_alive = bool(_poller_thread and _poller_thread.is_alive())
    lock_held = _advisory_connection is not None
    payload = {
        "status": "healthy" if processor_alive and poller_alive and lock_held else "unhealthy",
        "service": "video-processing-worker",
        "queue_depth": _jobs.qsize(),
        "processor_alive": processor_alive,
        "poller_alive": poller_alive,
        "singleton_lock_held": lock_held,
    }
    if payload["status"] != "healthy":
        raise HTTPException(status_code=503, detail=payload)
    return payload


@app.post("/internal/calibration/{mode}")
async def process_calibration(
    mode: Literal["video", "gaze", "camera"],
    media: Annotated[UploadFile, File()],
    metadata_json: Annotated[str, Form()],
    worker_token: Annotated[str | None, Header(alias="X-Video-Worker-Token")] = None,
) -> dict:
    _authorize(worker_token)
    metadata_type = {
        "video": CalibrationCaptureMetadata,
        "gaze": GazeCalibrationMetadata,
        "camera": CameraCalibrationMetadata,
    }[mode]
    try:
        metadata = metadata_type.model_validate_json(metadata_json)
    except Exception as error:
        raise HTTPException(status_code=422, detail="Invalid calibration metadata") from error

    suffix = Path(media.filename or "calibration.webm").suffix or ".webm"
    handle = tempfile.NamedTemporaryFile(
        delete=False,
        prefix="video-processing-calibration-",
        suffix=suffix,
    )
    path = Path(handle.name)
    total_bytes = 0
    try:
        while True:
            chunk = await media.read(UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_CALIBRATION_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Calibration media exceeds the maximum allowed size",
                )
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())
    except Exception:
        handle.close()
        _delete_temp(path)
        raise
    finally:
        if not handle.closed:
            handle.close()
        await media.close()

    if total_bytes <= 0:
        _delete_temp(path)
        raise HTTPException(status_code=400, detail="Calibration media upload is empty")

    request_id = os.urandom(16).hex()
    future: Future[dict] = Future()
    _enqueue(
        INTERACTIVE_PRIORITY,
        CalibrationJob(
            request_id=request_id,
            mode=mode,
            media_path=path,
            metadata=metadata.model_dump(mode="json"),
            future=future,
            queued_at=perf_counter(),
        ),
    )
    try:
        result = await asyncio.wait_for(
            asyncio.shield(asyncio.wrap_future(future)),
            timeout=settings.video_processing_worker_timeout_seconds,
        )
    except TimeoutError as error:
        raise HTTPException(status_code=504, detail="Visual calibration timed out") from error
    return {"request_id": request_id, "result": result}


@app.post("/internal/warmup")
async def warmup(
    worker_token: Annotated[str | None, Header(alias="X-Video-Worker-Token")] = None,
) -> dict[str, str]:
    """Load the isolated visual stack before calibration media arrives."""
    _authorize(worker_token)
    future: Future[None] = Future()
    _enqueue(
        INTERACTIVE_PRIORITY,
        WarmupJob(
            request_id=os.urandom(12).hex(),
            future=future,
            queued_at=perf_counter(),
        ),
    )
    try:
        await asyncio.wait_for(
            asyncio.shield(asyncio.wrap_future(future)),
            timeout=settings.video_processing_worker_timeout_seconds,
        )
    except TimeoutError as error:
        raise HTTPException(status_code=504, detail="Visual worker warmup timed out") from error
    return {"status": "ready"}
