"""FastAPI router for Simli Avatar session negotiation and telemetry."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.controllers.medical_interview_controller import MedicalInterviewController
from app.core.auth import get_current_active_user
from app.core.config import settings
from app.core.database import get_db
from app.models.medical_interview.medical_interview import MedicalInterviewDB
from app.models.user import User
from app.speech.simli_avatar_service import (
    SimliAvatarService,
    SimliConfigurationError,
    SimliProviderError,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/medical-interviews/{interview_id}/avatar",
    tags=["avatar"],
)


class StartAvatarSessionRequest(BaseModel):
    character_override: Optional[str] = None


class StartAvatarSessionResponse(BaseModel):
    session_token: str
    ice_servers: List[Dict[str, Any]] = Field(default_factory=list)
    face_id: str
    max_session_length: int
    max_idle_time: int
    enabled: bool = True


class AvatarStatusResponse(BaseModel):
    enabled: bool
    provider: str = "simli"


class AvatarTelemetryRequest(BaseModel):
    ttff_ms: float
    rtt_ms: float = 0.0
    jitter_ms: float = 0.0
    packet_loss_pct: float = 0.0
    frame_rate: float = 30.0
    resolution: str = "1280x720"
    active_duration_seconds: float = 0.0


def _validate_access(
    interview_id: int,
    user_id: int,
    db: Session,
) -> MedicalInterviewDB:
    controller = MedicalInterviewController(db)
    if not controller.validate_interview_access(interview_id, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview",
        )
    interview = (
        db.query(MedicalInterviewDB)
        .filter(MedicalInterviewDB.id == interview_id)
        .first()
    )
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )
    return interview


@router.get("/status", response_model=AvatarStatusResponse)
async def get_avatar_status(
    interview_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Report whether Simli Avatar is enabled for this interview."""
    _validate_access(interview_id, current_user.id, db)
    service = SimliAvatarService(configuration=settings)
    return AvatarStatusResponse(
        enabled=service.is_enabled,
        provider="simli",
    )


@router.post("/session", response_model=StartAvatarSessionResponse)
async def start_avatar_session(
    interview_id: int,
    request: StartAvatarSessionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Negotiate ephemeral session token and ICE servers for the Simli client."""
    interview = _validate_access(interview_id, current_user.id, db)
    service = SimliAvatarService(configuration=settings)

    if not service.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Simli Avatar service is not enabled or configured",
        )

    try:
        config = service.get_session_configuration(
            gender=interview.patient_gender,
            character_override=request.character_override,
        )
        return StartAvatarSessionResponse(
            session_token=config.session_token,
            ice_servers=config.ice_servers,
            face_id=config.face_id,
            max_session_length=config.max_session_length,
            max_idle_time=config.max_idle_time,
            enabled=True,
        )
    except SimliConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except SimliProviderError as exc:
        logger.warning(
            "Simli avatar session negotiation failed for interview %s: %s",
            interview_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post("/telemetry", status_code=status.HTTP_200_OK)
async def record_avatar_telemetry(
    interview_id: int,
    telemetry: AvatarTelemetryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Collect WebRTC performance and TTFF metrics per the evaluation methodology."""
    _validate_access(interview_id, current_user.id, db)
    logger.info(
        "Avatar telemetry recorded for interview %s: TTFF=%.2fms, RTT=%.2fms, FPS=%.1f, loss=%.2f%%, duration=%.2fs",
        interview_id,
        telemetry.ttff_ms,
        telemetry.rtt_ms,
        telemetry.frame_rate,
        telemetry.packet_loss_pct,
        telemetry.active_duration_seconds,
    )
    return {"status": "recorded"}

