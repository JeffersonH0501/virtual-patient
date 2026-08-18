"""Interview message endpoints."""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.message_controller import MessageController
from app.controllers.virtual_patient_controller import VirtualPatientController
from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.models.medical_interview import InterviewMessage, InterviewStatus
from app.models.medical_interview.medical_interview import MedicalInterviewDB
from app.models.user import User
from app.speech.storage import persist_patient_audio
from app.core.config import settings


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/medical-interviews",
    tags=["interview-messages"],
    responses={404: {"description": "Interview or message not found"}},
)


class SendMessageRequest(BaseModel):
    """Message sent by the student."""

    content: str
    message_metadata: Dict[str, Any] = Field(default_factory=dict)


class SendMessageResponse(BaseModel):
    """Updated conversation after processing one student message."""

    messages: List[InterviewMessage]
    new_message_ids: List[int] = Field(default_factory=list)


class MessagesResponse(BaseModel):
    """Chronological interview messages."""

    messages: List[InterviewMessage]


@router.post("/{interview_id}/messages", response_model=SendMessageResponse)
async def send_message(
    interview_id: int,
    message_data: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Send a student message and return the virtual patient's response."""
    started_at = time.monotonic()
    try:
        interview = db.query(MedicalInterviewDB).filter(
            MedicalInterviewDB.id == interview_id,
            MedicalInterviewDB.user_id == current_user.id,
        ).first()
        if not interview:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found",
            )
        elapsed_seconds = (datetime.now(timezone.utc) - interview.start_time).total_seconds()
        if elapsed_seconds >= 3600:
            metadata = dict(interview.interview_metadata or {})
            metadata.update({
                "completion_reason": "duration_limit_exceeded",
                "hypotheses_status": "not_consolidated_duration_limit",
                "duration_limit_seconds": 3600,
            })
            interview.interview_metadata = metadata
            interview.status = InterviewStatus.COMPLETED
            interview.end_time = datetime.now(timezone.utc)
            interview.total_duration = 3600
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Interview duration limit exceeded",
            )
        response_started_at = time.perf_counter()
        result = await VirtualPatientController().process_user_message(
            interview_id=interview_id,
            user_message_content=message_data.content,
            current_user=current_user,
            db=db,
            message_metadata=message_data.message_metadata,
        )

        agent_message = result["agent_message_object"]
        user_message = result["user_message_object"]
        message_controller = MessageController(db)
        generation_elapsed = time.perf_counter() - response_started_at
        persistence_started_at = time.perf_counter()
        new_message_ids = _create_exchange_messages(
            message_controller,
            interview_id,
            result["agent_response"],
            getattr(agent_message, "message_metadata", {}) or {},
            getattr(user_message, "content", message_data.content),
            getattr(user_message, "message_metadata", None)
            or message_data.message_metadata,
        )
        persistence_elapsed = time.perf_counter() - persistence_started_at
        response_read_started_at = time.perf_counter()
        messages = message_controller.get_interview_messages(interview_id)
        response_read_elapsed = time.perf_counter() - response_read_started_at
        if settings.patient_response_timing_logging:
            logger.info(
                "patient_response_timing interview_id=%s stage=request "
                "generation_ms=%.1f persistence_and_optional_tts_ms=%.1f "
                "response_read_ms=%.1f total_ms=%.1f",
                interview_id,
                generation_elapsed * 1000,
                persistence_elapsed * 1000,
                response_read_elapsed * 1000,
                (time.monotonic() - started_at) * 1000,
            )
        logger.info(
            "Processed interview %s message in %.3f seconds",
            interview_id,
            time.monotonic() - started_at,
        )
        return SendMessageResponse(
            messages=messages,
            new_message_ids=new_message_ids,
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Failed to process a message for interview %s", interview_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {error}",
        ) from error


@router.get("/{interview_id}/messages", response_model=MessagesResponse)
async def get_messages(
    interview_id: int,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Return the chronological message history for an authorized interview."""
    interview_controller = MedicalInterviewController(db)
    if not interview_controller.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview",
        )
    if not interview_controller.get_interview(interview_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )
    return MessagesResponse(
        messages=MessageController(db).get_interview_messages(interview_id, limit)
    )


@router.get("/{interview_id}/messages/{message_id}", response_model=InterviewMessage)
async def get_message(
    interview_id: int,
    message_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Return one message after validating interview access and ownership."""
    interview_controller = MedicalInterviewController(db)
    if not interview_controller.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview",
        )

    message = MessageController(db).get_message(message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )
    if message.interview_id != interview_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Message does not belong to this interview",
        )
    return message


def _create_exchange_messages(
    message_controller: MessageController,
    interview_id: int,
    patient_content: str,
    patient_metadata: Dict[str, Any],
    user_content: str,
    user_metadata: Dict[str, Any],
) -> List[int]:
    """Persist one student/patient exchange and optional durable patient audio."""
    user_message = message_controller.create_user_message(
        interview_id=interview_id,
        content=user_content,
        message_metadata=user_metadata,
    )

    interview = message_controller.db.query(MedicalInterviewDB).filter(
        MedicalInterviewDB.id == interview_id
    ).first()
    personality_namespace_key: Optional[str] = None
    gender: Optional[str] = None
    if interview:
        gender = interview.patient_gender
        if interview.personality:
            personality_namespace_key = interview.personality.namespace_key

    persisted_audio = persist_patient_audio(
        interview_id,
        patient_content,
        personality_namespace_key,
        gender,
    )
    patient_metadata = dict(patient_metadata)
    patient_metadata["speech_synthesis"] = persisted_audio.synthesis_metadata
    patient_message = message_controller.create_patient_message(
        interview_id=interview_id,
        content=patient_content,
        message_metadata=patient_metadata,
        audio_url=persisted_audio.audio_url,
    )
    return [user_message.id, patient_message.id]
