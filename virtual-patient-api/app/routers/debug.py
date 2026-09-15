"""DEV/DEBUG-ONLY endpoints for the multimodal calibration debug tool.

These endpoints expose raw, frame-level extractor output for live display in the
calibration debug UI. They are authenticated but intended for development use
only. They never write to the database, never persist media, and never touch the
interview or calibration persistence flow. Heavy extractor imports live inside
the debug helpers (lazily), so this module imports cleanly without Py-Feat,
OpenCV, or OpenSMILE installed.
"""

from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.core.auth import get_current_active_user
from app.debug.opensmile_debug import OpenSmileDebugUnavailable, process_audio_chunk
from app.debug.pyfeat_debug import PyFeatDebugBusy, PyFeatDebugUnavailable, detect_frame
from app.debug.schemas import DebugUnavailable, OpenSmileFrameDebug, PyFeatFrameDebug
from app.models.user import User


router = APIRouter(prefix="/debug/multimodal", tags=["debug"])
logger = logging.getLogger(__name__)

# Upload guards. A debug tool sends small single frames / short audio chunks, so
# a 10 MB cap is generous while still rejecting accidental large uploads.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

IMAGE_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png"}
AUDIO_CONTENT_TYPES = {
    "audio/webm",
    "video/webm",
    "audio/ogg",
    "audio/mp4",
    "video/mp4",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
}


def _base_content_type(content_type: Optional[str]) -> str:
    return (content_type or "").split(";")[0].strip().lower()


async def _read_capped(upload: UploadFile, allowed: set[str]) -> bytes:
    """Validate content type and size, returning the in-memory bytes.

    Raises 415 for a disallowed content type, 413 for oversize uploads, and 400
    for an empty body. The whole payload is kept in memory only; it is never
    written to a persistent location by this router.
    """
    base_type = _base_content_type(upload.content_type)
    if base_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {base_type or 'unknown'}",
        )
    data = await upload.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty upload",
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Upload exceeds the 10 MB debug limit",
        )
    return data


def _unavailable_response(reason: str) -> JSONResponse:
    """Return a compact 503 body instead of a 500 stack trace."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=DebugUnavailable(available=False, reason=reason).model_dump(),
    )


@router.post("/frame", response_model=PyFeatFrameDebug)
async def debug_pyfeat_frame(
    frame: Annotated[UploadFile, File(description="Single image frame (jpeg/png)")],
    frame_timestamp_ms: Annotated[Optional[float], Form()] = None,
    current_user: User = Depends(get_current_active_user),
):
    """Run single-image Py-Feat detection on one frame and return raw values.

    No database writes and no media persistence occur. On extractor
    unavailability a 503 debug-unavailable body is returned.
    """
    image_bytes = await _read_capped(frame, IMAGE_CONTENT_TYPES)
    try:
        return await run_in_threadpool(
            detect_frame,
            image_bytes,
            frame_timestamp_ms=frame_timestamp_ms,
        )
    except PyFeatDebugBusy:
        return _unavailable_response("pyfeat_busy")
    except PyFeatDebugUnavailable as error:
        logger.warning("Py-Feat debug extractor unavailable: %s", error)
        return _unavailable_response("pyfeat_unavailable")


@router.post("/audio", response_model=OpenSmileFrameDebug)
async def debug_opensmile_audio(
    audio: Annotated[UploadFile, File(description="Short audio chunk (webm/ogg/mp4/wav)")],
    frame_timestamp_ms: Annotated[Optional[float], Form()] = None,
    current_user: User = Depends(get_current_active_user),
):
    """Run OpenSMILE over one short audio chunk and return raw frame values.

    No database writes and no media persistence occur. On extractor
    unavailability a 503 debug-unavailable body is returned.
    """
    audio_bytes = await _read_capped(audio, AUDIO_CONTENT_TYPES)
    try:
        return await run_in_threadpool(
            process_audio_chunk,
            audio_bytes,
            content_type=_base_content_type(audio.content_type),
            frame_timestamp_ms=frame_timestamp_ms,
        )
    except OpenSmileDebugUnavailable as error:
        logger.warning("OpenSMILE debug extractor unavailable: %s", error)
        return _unavailable_response("opensmile_unavailable")
