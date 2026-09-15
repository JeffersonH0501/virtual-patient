"""FastAPI router for Azure AI Speech Avatar Validation Pilot and telemetry."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.controllers.medical_interview_controller import MedicalInterviewController
from app.core.auth import get_current_active_user
from app.core.config import settings
from app.core.database import get_db
from app.models.medical_interview.medical_interview import MedicalInterviewDB
from app.models.user import User
from app.speech.azure_avatar_pilot_service import AzureAvatarPilotService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/medical-interviews/{interview_id}/avatar-pilot",
    tags=["avatar-pilot"],
)


class StartSessionRequest(BaseModel):
    character_override: Optional[str] = None


class StartSessionResponse(BaseModel):
    speech_token: str
    ice_servers: list = Field(default_factory=list)
    character: str
    voice: str
    style: str
    region: str


class TurnTelemetryRequest(BaseModel):
    ttff_ms: float
    rtt_ms: float = 0.0
    jitter_ms: float = 0.0
    packet_loss_pct: float = 0.0
    frame_rate: float = 30.0
    resolution: str = "1280x720"
    active_duration_seconds: float = 0.0


def _validate_access(interview_id: int, user_id: int, db: Session) -> MedicalInterviewDB:
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


@router.post("/session", response_model=StartSessionResponse)
async def start_avatar_session(
    interview_id: int,
    request: StartSessionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return ephemeral credentials required by the Azure Speech browser SDK."""
    interview = _validate_access(interview_id, current_user.id, db)
    service = AzureAvatarPilotService()

    try:
        session_info = service.get_client_configuration(
            gender=interview.patient_gender,
            character_override=request.character_override,
        )
        return StartSessionResponse(
            speech_token=session_info["speech_token"],
            ice_servers=session_info.get("ice_servers", []),
            character=session_info["character"],
            voice=session_info["voice"],
            style=session_info["style"],
            region=session_info["region"],
        )
    except Exception as error:
        logger.exception("Failed to start avatar session for interview %s", interview_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error


@router.post("/telemetry")
async def record_telemetry_turn(
    interview_id: int,
    telemetry: TurnTelemetryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Record turn metrics (TTFF, WebRTC stats) for Section 4.4 protocol audit."""
    _validate_access(interview_id, current_user.id, db)
    service = AzureAvatarPilotService()
    service.save_turn_telemetry(interview_id, telemetry.model_dump())
    return {"status": "recorded", "interview_id": interview_id}


@router.get("/telemetry-report")
async def get_telemetry_report(
    interview_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Retrieve aggregated empirical validation report for Section 4.4 analysis."""
    _validate_access(interview_id, current_user.id, db)
    service = AzureAvatarPilotService()
    return service.get_telemetry_summary(interview_id)

