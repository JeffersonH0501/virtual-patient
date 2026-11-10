"""Provider-neutral speech endpoints."""

import logging
from typing import Literal, Optional

from anyio import CancelScope
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
from pydantic import BaseModel
from openai import OpenAIError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse
from starlette.responses import FileResponse

from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.message_controller import MessageController
from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.models.medical_interview.enums import SenderType
from app.models.medical_interview.medical_interview import MedicalInterviewDB
from app.models.user import User
from app.media.access import _current_media_user
from app.speech.azure_openai import AzureOpenAITextToSpeechProvider
from app.speech.contracts import (
    SpeechConfigurationError,
    SpeechProviderError,
    SpeechSynthesisRequest,
    SpeechTranscriptionRequest,
)
from app.speech.service import SpeechService, create_patient_synthesis_request
from app.media.storage import get_media_storage
from app.models.medical_interview import InterviewRecordingDB


logger = logging.getLogger(__name__)
router = APIRouter(tags=["speech"])
MAX_TRANSCRIPTION_BYTES = 25 * 1024 * 1024


async def _block_patient_audio(interview_id, message_id, inputs, db):
    recording = db.query(InterviewRecordingDB).filter_by(medical_interview_id=interview_id).first()
    if recording is None or (recording.capture_config or {}).get("mediaTransport") != "reusable_blocks_v1":
        return None
    from datetime import datetime, timezone
    from app.speech.preserved_audio import preserved_patient_audio
    if recording.failure_code == "retention_expired" or (recording.retention_expires_at and
            recording.retention_expires_at <= datetime.now(timezone.utc)):
        raise HTTPException(410, "Patient audio retention has expired")
    recording_id = recording.id
    db.rollback()
    try:
        path = await run_in_threadpool(preserved_patient_audio, get_media_storage(), interview_id,
            recording_id, message_id, lambda: SpeechService().synthesize_patient_message(*inputs))
    except (SpeechConfigurationError, SpeechProviderError) as error:
        raise _speech_http_error(error) from error
    except OSError as error:
        raise HTTPException(503, "Patient audio could not be preserved") from error
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "private, no-store"})


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


def _patient_speech_inputs(interview_id: int, message_id: int, db: Session, user_id: int):
    interview_controller = MedicalInterviewController(db)
    if not interview_controller.validate_interview_access(interview_id, user_id):
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
    return message.content, personality_namespace_key, interview.patient_gender if interview else None


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
    """Synthesize one authorized patient message with Azure OpenAI."""
    inputs = _patient_speech_inputs(interview_id, message_id, db, current_user.id)

    preserved = await _block_patient_audio(interview_id, message_id, inputs, db)
    if preserved is not None:
        return preserved

    try:
        audio = await run_in_threadpool(
            SpeechService().synthesize_patient_message,
            *inputs,
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


class PatientSpeechStream(StreamingResponse):
    async def stream_response(self, send):
        try:
            await super().stream_response(send)
        finally:
            with CancelScope(shield=True):
                await self.body_iterator.aclose()


def patient_speech_stream(request: SpeechSynthesisRequest, *, context: str) -> StreamingResponse:
    chunks = AzureOpenAITextToSpeechProvider().stream(request)

    async def body():
        try:
            chunk = await run_in_threadpool(next, chunks, None)
            if not chunk:
                raise SpeechProviderError("Text-to-speech provider returned empty audio")
            while chunk is not None:
                yield chunk
                chunk = await run_in_threadpool(next, chunks, None)
        except (OpenAIError, SpeechConfigurationError, SpeechProviderError, RuntimeError):
            logger.warning("Patient speech stream failed (%s)", context)
            raise RuntimeError("Patient speech stream failed") from None
        finally:
            with CancelScope(shield=True):
                await run_in_threadpool(chunks.close)

    return PatientSpeechStream(
        body(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/medical-interviews/{interview_id}/messages/{message_id}/speech")
async def stream_patient_message(
    interview_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_current_media_user),
):
    inputs = _patient_speech_inputs(interview_id, message_id, db, current_user.id)
    preserved = await _block_patient_audio(interview_id, message_id, inputs, db)
    if preserved is not None:
        return preserved
    request = create_patient_synthesis_request(*inputs)
    return patient_speech_stream(request, context=f"interview {interview_id} message {message_id}")


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
        result = await run_in_threadpool(
            SpeechService().transcribe,
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
