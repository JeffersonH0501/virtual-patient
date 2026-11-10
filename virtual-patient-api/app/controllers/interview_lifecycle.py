"""Transaction-held lifecycle locks shared by interview writers."""
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError
from sqlalchemy import text
from functools import wraps
import asyncio
import time


def interview_lifecycle(interview, *, owner):
    """Project durable state without exposing assessment content or new authority."""
    status = getattr(interview.status, "value", interview.status)
    metadata = interview.interview_metadata or {}
    recording = interview.recording
    config = (recording.capture_config or {}) if recording else {}
    failure = metadata.get("completion_processing", {})
    frozen = bool(recording and recording.status in {"ready", "partial"} and recording.ended_at)
    if status == "completed":
        phase = "completed"
    elif failure.get("status") == "failed" and status in {"processing", "interrupted"}:
        phase = "completion_failed"
    elif status == "processing":
        phase = "processing"
    elif status == "interrupted":
        phase = "interrupted"
    elif interview.start_time is None:
        phase = "preparing"
    elif frozen:
        phase = "capture_finalized"
    elif config.get("resume_attempt"):
        phase = "resume_required"
    else:
        phase = "active"
    return {"phase": phase, "can_resume_capture": owner and phase in {"active", "resume_required"},
            "can_complete": owner and phase == "capture_finalized",
            "can_retry_completion": owner and phase == "completion_failed",
            "error_code": failure.get("error_code") if owner and phase == "completion_failed" else None,
            "recording_transport": metadata.get("recording_transport")}


def require_no_pending_reply(interview):
    claim = (interview.interview_metadata or {}).get("message_request") or {}
    if claim and time.time() - claim.get("started_at", 0) < 120:
        raise HTTPException(409, {"code": "patient_response_pending"})


def threaded_capture(operation):
    """Keep blocking database work off the ASGI event loop."""
    from starlette.concurrency import run_in_threadpool
    @wraps(operation)
    async def execute(*args, **kwargs):
        def run():
            kwargs["db"].info["capture_wait"] = True
            return asyncio.run(operation(*args, **kwargs))
        return await run_in_threadpool(run)
    return execute


def lock_row(db, model, identifier):
    """Bound lock waits in capture threads; never wait on the ASGI event loop."""
    try:
        wait = db.info.get("capture_wait", False)
        if wait and db.bind.dialect.name == "postgresql":
            db.execute(text("SET LOCAL lock_timeout = '2s'"))
        return db.query(model).filter(model.id == identifier).populate_existing().with_for_update(nowait=not wait).first()
    except OperationalError as error:
        if getattr(error.orig, "pgcode", None) != "55P03":
            raise
        db.rollback()
        raise HTTPException(status_code=503, detail={"code": "capture_busy"}, headers={"Retry-After": "1"}) from error


def require_capture_open(interview):
    recording = getattr(interview, "recording", None)
    if getattr(interview.status, "value", interview.status) != "in_progress" or (
        recording is not None and recording.status in {"ready", "partial"}
    ):
        raise HTTPException(status_code=409, detail={"code": "capture_closed"})
