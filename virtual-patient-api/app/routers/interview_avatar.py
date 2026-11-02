"""Optional Tavus avatar session lifecycle for an in-progress interview."""

import logging
import threading
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.avatar import (
    AvatarConfigurationError,
    AvatarProviderError,
    TavusClient,
)
from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.models.medical_interview.medical_interview import MedicalInterviewDB
from app.models.user import User


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/medical-interviews",
    tags=["interview-avatar"],
    responses={404: {"description": "Interview not found"}},
)

# Conversation ids are tracked per interview so a client can only end the
# session this API created for it, never an arbitrary provider conversation.
_active_conversations: Dict[int, str] = {}
_active_lock = threading.Lock()


class AvatarSessionResponse(BaseModel):
    """Private room credentials for the browser."""

    provider: str = "tavus"
    conversation_id: str
    conversation_url: str
    meeting_token: Optional[str] = None


def get_avatar_client() -> TavusClient:
    return TavusClient()


def _get_owned_interview(
    db: Session, interview_id: int, user: User
) -> MedicalInterviewDB:
    interview = db.query(MedicalInterviewDB).filter(
        MedicalInterviewDB.id == interview_id,
        MedicalInterviewDB.user_id == user.id,
    ).first()
    if interview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found"
        )
    return interview


@router.post("/{interview_id}/avatar/session", response_model=AvatarSessionResponse)
def start_avatar_session(
    interview_id: int,
    client: TavusClient = Depends(get_avatar_client),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a private Tavus conversation for an in-progress interview."""
    interview = _get_owned_interview(db, interview_id, current_user)
    if getattr(interview.status, "value", interview.status) != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only in-progress interviews can start an avatar session",
        )
    if not client.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Avatar provider is not configured",
        )

    with _active_lock:
        previous = _active_conversations.pop(interview_id, None)
    if previous:
        try:
            client.end_session(previous)
        except (AvatarConfigurationError, AvatarProviderError):
            logger.warning("Could not end the previous avatar session for %s", interview_id)

    try:
        session = client.create_session(interview_id)
    except (AvatarConfigurationError, AvatarProviderError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Avatar provider is unavailable",
        ) from error

    with _active_lock:
        _active_conversations[interview_id] = session.conversation_id
    logger.info(
        "avatar_session_started interview_id=%s conversation_id=%s",
        interview_id,
        session.conversation_id,
    )
    return AvatarSessionResponse(
        conversation_id=session.conversation_id,
        conversation_url=session.conversation_url,
        meeting_token=session.meeting_token,
    )


@router.delete(
    "/{interview_id}/avatar/session", status_code=status.HTTP_204_NO_CONTENT
)
def end_avatar_session(
    interview_id: int,
    client: TavusClient = Depends(get_avatar_client),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """End the Tavus conversation created for this interview, if any."""
    _get_owned_interview(db, interview_id, current_user)
    with _active_lock:
        conversation_id = _active_conversations.pop(interview_id, None)
    if conversation_id and client.configured:
        try:
            client.end_session(conversation_id)
        except (AvatarConfigurationError, AvatarProviderError):
            # Tavus also ends idle rooms through its participant-left timeout.
            logger.warning(
                "avatar_session_end_failed interview_id=%s conversation_id=%s",
                interview_id,
                conversation_id,
            )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
