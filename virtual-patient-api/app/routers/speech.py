"""Provider-neutral speech endpoints."""

import logging
from typing import Literal, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.message_controller import MessageController
from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.models.medical_interview.enums import SenderType
from app.models.medical_interview.medical_interview import MedicalInterviewDB
from app.models.user import User
from app.speech.contracts import (
    SpeechConfigurationError,
    SpeechProviderError,
    SpeechTranscriptionRequest,
)
from app.speech.service import SpeechService
from app.speech.vocal_style_policy import VOCAL_STYLE_POLICY_VERSION


logger = logging.getLogger(__name__)
router = APIRouter(tags=["speech"])
MAX_TRANSCRIPTION_BYTES = 25 * 1024 * 1024


class TranscriptionResponse(BaseModel):
    """Neutral server transcription response."""

    text: str
    language: Optional[str] = None
    provider: str
    model: str


def _speech_http_error(error: Exception) -> HTTPException:
    """Map speech service errors to stable HTTP responses."""
    if isinstance(error, SpeechConfigurationError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=str(error),
    )


@router.post(
    "/medical-interviews/{interview_id}/messages/{message_id}/speech",
    response_class=Response,
)
async def synthesize_patient_message(
    interview_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Synthesize one authorized patient message without requiring GCS."""
    interview_controller = MedicalInterviewController(db)
    if not interview_controller.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview",
        )

    message = MessageController(db).get_message(message_id)
    if not message or message.interview_id != interview_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient message not found",
        )
    if message.sender_type != SenderType.PATIENT.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Speech can only be generated for patient messages",
        )

    interview = db.query(MedicalInterviewDB).filter(
        MedicalInterviewDB.id == interview_id
    ).first()
    personality_namespace_key = (
        interview.personality.namespace_key
        if interview and interview.personality
        else None
    )
    gender = interview.patient_gender if interview else None

    synthesis_metadata = (getattr(message, "message_metadata", None) or {}).get(
        "speech_synthesis",
        {},
    )
    if (
        getattr(message, "audio_url", None)
        and synthesis_metadata.get("style_policy_version")
        == VOCAL_STYLE_POLICY_VERSION
    ):
        return RedirectResponse(message.audio_url, status_code=status.HTTP_303_SEE_OTHER)

    try:
        audio = SpeechService().synthesize_patient_message(
            message.content,
            personality_namespace_key,
            gender,
        )
    except (SpeechConfigurationError, SpeechProviderError) as error:
        logger.warning(
            "Speech synthesis failed for interview %s message %s: %s",
            interview_id,
            message_id,
            error,
        )
        raise _speech_http_error(error) from error

    return Response(
        content=audio.content,
        media_type=audio.content_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Speech-Provider": audio.provider,
            "X-Speech-Model": audio.model,
            "X-Speech-Style-Version": audio.style_policy_version or "unversioned",
        },
    )


@router.post("/speech/transcriptions", response_model=TranscriptionResponse)
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: Optional[Literal["en", "es"]] = Form(default=None),
    current_user: User = Depends(get_current_active_user),
):
    """Transcribe uploaded audio without storing the media payload."""
    del current_user
    content = await audio.read(MAX_TRANSCRIPTION_BYTES + 1)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file cannot be empty",
        )
    if len(content) > MAX_TRANSCRIPTION_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file exceeds the 25 MB limit",
        )

    try:
        result = SpeechService().transcribe(
            SpeechTranscriptionRequest(
                content=content,
                filename=audio.filename or "audio.webm",
                content_type=audio.content_type or "application/octet-stream",
                language=language,
            )
        )
    except (SpeechConfigurationError, SpeechProviderError) as error:
        logger.warning("Speech transcription failed: %s", error)
        raise _speech_http_error(error) from error

    return TranscriptionResponse(
        text=result.text,
        language=result.language,
        provider=result.provider,
        model=result.model,
    )
