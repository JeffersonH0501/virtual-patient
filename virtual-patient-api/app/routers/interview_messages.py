"""Interview message endpoints."""

import logging
import time
from uuid import UUID, uuid4
from starlette.concurrency import run_in_threadpool
from app.core.review_access import can_read_assessments
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.message_controller import MessageController
from app.controllers.virtual_patient_controller import VirtualPatientController
from app.core.auth import get_current_active_user
from app.core.database import admit_external_transaction, get_db
from app.core.async_work import cancel_and_drain
from app.models.medical_interview import InterviewMessage
from app.models.medical_interview import InterviewMessageDB, SenderType
from app.controllers.interview_lifecycle import lock_row, require_capture_open
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
    client_request_id: UUID | None = None
    segment_id: UUID | None = None


class SendMessageResponse(BaseModel):
    """Updated conversation after processing one student message."""

    messages: List[InterviewMessage]
    new_message_ids: List[int] = Field(default_factory=list)


class MessagesResponse(BaseModel):
    """Chronological interview messages."""

    messages: List[InterviewMessage]


@router.post("/{interview_id}/messages", response_model=SendMessageResponse, dependencies=[Depends(admit_external_transaction)])
async def send_message(
    interview_id: int,
    message_data: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Send a student message and return the virtual patient's response."""
    started_at = time.monotonic()
    result = None
    claim_token = None
    try:
        request_id = str(message_data.client_request_id) if message_data.client_request_id else None
        claim_token, segment_id, previous = await run_in_threadpool(
            _claim_message_request, db, interview_id, message_data, current_user.id, request_id)
        if previous is not None:
            return previous
        response_started_at = time.perf_counter()
        result = await VirtualPatientController().process_user_message(
            interview_id=interview_id,
            user_message_content=message_data.content,
            current_user=current_user,
            db=db,
            message_metadata={**{key: value for key, value in message_data.message_metadata.items() if key != "client_request_id"},
                              **({"client_request_id": request_id} if request_id else {})},
        )

        agent_message = result["agent_message_object"]
        user_message = result["user_message_object"]
        agent_metadata = dict(getattr(agent_message, "message_metadata", {}) or {})
        user_metadata = dict(getattr(user_message, "message_metadata", None) or message_data.message_metadata)
        if request_id:
            agent_metadata["client_request_id"] = request_id
            user_metadata["client_request_id"] = request_id
        for metadata in (agent_metadata, user_metadata):
            metadata.pop("capture_segment_id", None)
            if segment_id is not None:
                metadata["capture_segment_id"] = segment_id
        message_controller = MessageController(db)
        generation_elapsed = time.perf_counter() - response_started_at
        persistence_started_at = time.perf_counter()
        new_message_ids = await run_in_threadpool(_commit_claimed_exchange,
            message_controller,
            interview_id,
            current_user.id,
            str(message_data.segment_id) if message_data.segment_id else None,
            claim_token,
            result["agent_response"],
            agent_metadata,
            getattr(user_message, "content", message_data.content),
            user_metadata,
        )
        persistence_elapsed = time.perf_counter() - persistence_started_at
        response_read_started_at = time.perf_counter()
        messages = message_controller.get_interview_messages(interview_id)
        response_read_elapsed = time.perf_counter() - response_read_started_at
        if settings.patient_response_timing_logging:
            logger.info(
                "patient_response_timing interview_id=%s request_id=%s stage=request "
                "generation_ms=%.1f persistence_and_optional_tts_ms=%.1f "
                "response_read_ms=%.1f total_ms=%.1f",
                interview_id,
                request_id,
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
    except BaseException as error:
        if result is not None:
            await cancel_and_drain(result.get("workflow_result", {}).get("_background_task"))
        db.rollback()
        if claim_token is not None:
            await run_in_threadpool(_release_message_claim, db, interview_id, claim_token)
        if isinstance(error, HTTPException) or not isinstance(error, Exception):
            raise
        logger.exception("Failed to process a message for interview %s", interview_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process message",
        ) from error


@router.get("/{interview_id}/messages", response_model=MessagesResponse)
async def get_messages(
    interview_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
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
    messages = MessageController(db).get_interview_messages(interview_id, limit, offset=offset)
    if not can_read_assessments(db, db.get(MedicalInterviewDB, interview_id), current_user):
        messages = [message.model_copy(update={"message_metadata": {}}) for message in messages]
    return MessagesResponse(messages=messages)


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
    if not can_read_assessments(db, db.get(MedicalInterviewDB, interview_id), current_user):
        message = message.model_copy(update={"message_metadata": {}})
    return message


def _claim_message_request(db, interview_id, message_data, user_id, request_id):
    """Claim generation in a short transaction without starving behind fragment writes."""
    from app.controllers.recording_segments import require_active_segment
    db.info["capture_wait"] = True
    interview = lock_row(db, MedicalInterviewDB, interview_id)
    if interview is None or interview.user_id != user_id:
        raise HTTPException(404, "Interview not found")
    if interview.start_time is None:
        raise HTTPException(409, "The interview has not started")
    if request_id:
        previous = db.query(InterviewMessageDB).filter(
            InterviewMessageDB.interview_id == interview_id,
            InterviewMessageDB.message_metadata["client_request_id"].as_string() == request_id,
        ).order_by(InterviewMessageDB.id).all()
        if previous:
            if len(previous) != 2 or previous[0].sender_type != SenderType.USER or previous[0].content != message_data.content:
                raise HTTPException(409, "Message request identifier has a different or incomplete exchange")
            response = SendMessageResponse(messages=MessageController(db).get_interview_messages(interview_id),
                                           new_message_ids=[message.id for message in previous])
            db.rollback()
            return None, None, response
    require_capture_open(interview)
    segment = require_active_segment(db, interview_id, str(message_data.segment_id) if message_data.segment_id else None)
    segment_id = segment.id if segment is not None else None
    metadata = dict(interview.interview_metadata or {})
    previous_claim = metadata.get("message_request") or {}
    if previous_claim and time.time() - previous_claim.get("started_at", 0) < 120:
        logger.info("message_claim_busy interview_id=%s", interview_id)
        raise HTTPException(503, {"code": "message_in_progress"}, headers={"Retry-After": "1"})
    claim_token = str(uuid4())
    metadata["message_request"] = {"token": claim_token, "started_at": time.time()}
    interview.interview_metadata = metadata
    db.commit()
    return claim_token, segment_id, None


def _release_message_claim(db, interview_id, claim_token):
    db.info["capture_wait"] = True
    try:
        interview = lock_row(db, MedicalInterviewDB, interview_id)
        metadata = dict(interview.interview_metadata or {}) if interview else {}
        if (metadata.get("message_request") or {}).get("token") == claim_token:
            metadata.pop("message_request", None)
            interview.interview_metadata = metadata
            db.commit()
    except Exception:
        db.rollback()
        logger.warning("Message claim cleanup deferred interview_id=%s", interview_id)


def _commit_claimed_exchange(message_controller, interview_id, user_id, segment_id, claim_token, *exchange):
    db = message_controller.db
    db.info["capture_wait"] = True
    interview = lock_row(db, MedicalInterviewDB, interview_id)
    if interview is None or interview.user_id != user_id:
        raise HTTPException(404, "Interview not found")
    require_capture_open(interview)
    from app.controllers.recording_segments import require_active_segment
    require_active_segment(db, interview_id, segment_id)
    metadata = dict(interview.interview_metadata or {})
    if (metadata.get("message_request") or {}).get("token") != claim_token:
        raise HTTPException(409, {"code": "stale_message_request"})
    metadata.pop("message_request", None)
    interview.interview_metadata = metadata
    return _create_exchange_messages(message_controller, interview_id, *exchange)


def _create_exchange_messages(
    message_controller: MessageController,
    interview_id: int,
    patient_content: str,
    patient_metadata: Dict[str, Any],
    user_content: str,
    user_metadata: Dict[str, Any],
) -> List[int]:
    """Persist one student/patient exchange and optional durable patient audio."""
    user_metadata = dict(user_metadata)
    capture_turn = user_metadata.pop("capture_turn", None)
    sequence = message_controller.db.query(InterviewMessageDB).filter_by(interview_id=interview_id).count()
    user_message = message_controller.create_user_message(
        interview_id=interview_id,
        content=user_content,
        message_metadata=user_metadata,
        commit=False,
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
        commit=False,
    )
    if capture_turn is not None:
        from app.models.medical_interview import TurnUpsertRequest
        from app.routers.interview_recordings import persist_turn
        from pydantic import ValidationError
        from types import SimpleNamespace
        try:
            timing = TurnUpsertRequest.model_validate({**capture_turn, "segment_id": user_metadata.get("capture_segment_id"),
                "speaker": "student", "sequence": sequence, "transcript": user_content})
        except (ValidationError, TypeError) as error:
            raise HTTPException(422, "Invalid student capture timing") from error
        message_controller.db.flush()
        persist_turn(interview_id, user_message.id, timing, SimpleNamespace(id=interview.user_id),
                     message_controller.db, commit=False)
    message_controller.db.commit()
    return [user_message.id, patient_message.id]
