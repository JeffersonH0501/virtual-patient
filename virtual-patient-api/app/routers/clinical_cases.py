"""Read-only catalog of the default clinical cases supplied with the application."""
from typing import Annotated, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.agents.virtual_patient_workflow import VirtualPatientWorkflow
from app.agents.schemas.progress_summary import ProgressSummarySchema
from app.agents.summary_workflow import create_summary_workflow
from app.controllers.clinical_case_controller import ClinicalCaseController
from app.core.auth import get_current_active_user, require_superuser
from app.core.database import get_db
from app.models.clinical_case import (
    CaseType, ClinicalCaseDB, ClinicalCaseSimplified, ClinicalCaseWithOrganization,
)
from app.models.user import User, UserRole
from app.models.personality import PersonalityDB
from app.speech.contracts import SpeechConfigurationError, SpeechProviderError
from app.speech.service import SpeechService, create_patient_synthesis_request
from app.routers.speech import patient_speech_stream
from app.utils.language import convert_language_code_to_name, get_supported_language_codes

router = APIRouter(prefix="/clinical-cases", tags=["clinical-cases"])


class PreviewExchange(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=16000)


class PatientPreviewRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    language: Literal["en", "es"]
    gender: Literal["male", "female"]
    personality_id: Annotated[int, Field(gt=0)]
    history: list[PreviewExchange] = Field(default_factory=list, max_length=12)

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, question):
        return question.strip() if isinstance(question, str) else question


@router.post("/{case_id}/patient-preview")
async def preview_patient_response(
    case_id: int,
    request: PatientPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
) -> dict[str, str]:
    case = require_default_case(db, case_id)
    personality = db.get(PersonalityDB, request.personality_id)
    if personality is None:
        raise HTTPException(404, "Personality not found")
    workflow = VirtualPatientWorkflow(
        store=InMemoryStore(),
        checkpointer=InMemorySaver(),
        interview_id=f"preview-{uuid4()}",
        current_language=convert_language_code_to_name(request.language),
        personality=personality.namespace_key,
        patient_gender=request.gender,
        patient_name=case.female_name if request.gender == "female" else case.male_name,
        persist_background_memory=False,
    )
    result = await workflow.process_interview_message(
        question={"role": "user", "content": request.question},
        clinical_case=case,
        history=[
            AIMessage(content="Hola, mucho gusto." if request.language == "es" else "Hello, nice to meet you."),
            *[
            message
            for exchange in request.history
            for message in (HumanMessage(content=exchange.question), AIMessage(content=exchange.answer))
            ],
        ],
    )
    messages = (result.get("interview_result") or {}).get("messages", [])
    answer = result.get("translated_patient_response")
    if not answer and messages:
        last_message = messages[-1]
        answer = last_message.get("content") if isinstance(last_message, dict) else last_message.content
    if not isinstance(answer, str) or not answer.strip():
        raise HTTPException(502, "Patient preview returned no text")
    return {"answer": answer}


class PreviewSummaryRequest(BaseModel):
    language: Literal["en", "es"]
    history: list[PreviewExchange] = Field(min_length=1, max_length=100)


@router.post("/{case_id}/patient-preview/summary", response_model=ProgressSummarySchema | None)
async def preview_patient_summary(
    case_id: int,
    request: PreviewSummaryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    case = require_default_case(db, case_id)
    workflow = create_summary_workflow(
        store=InMemoryStore(),
        checkpointer=InMemorySaver(),
        interview_id=f"preview-{uuid4()}",
        current_language=convert_language_code_to_name(request.language),
    )
    result = await workflow.process_summary(
        messages=[
            message
            for exchange in request.history
            for message in (
                {"role": "user", "content": exchange.question},
                {"role": "assistant", "content": exchange.answer},
            )
        ],
        clinical_case=case,
    )
    return result.get("translated_summary") or result.get("summary_result")


class PreviewSpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=16000)
    gender: Literal["male", "female"]
    personality_id: Annotated[int, Field(gt=0)]


@router.post("/{case_id}/patient-preview/speech")
async def preview_patient_speech(
    case_id: int,
    request: PreviewSpeechRequest,
    progressive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    require_default_case(db, case_id)
    personality = db.get(PersonalityDB, request.personality_id)
    if personality is None:
        raise HTTPException(404, "Personality not found")
    if progressive:
        synthesis = create_patient_synthesis_request(request.text, personality.namespace_key, request.gender)
        return patient_speech_stream(synthesis, context="preview")
    try:
        audio = await run_in_threadpool(
            SpeechService().synthesize_patient_message,
            request.text,
            personality.namespace_key,
            request.gender,
        )
    except (SpeechConfigurationError, SpeechProviderError) as error:
        raise HTTPException(502, "Patient preview audio is unavailable") from error
    return Response(audio.content, media_type=audio.content_type, headers={"Cache-Control": "no-store"})


def require_default_case(db: Session, case_id: int) -> ClinicalCaseDB:
    """Restrict catalog access without removing cases referenced by old interviews."""
    case = db.get(ClinicalCaseDB, case_id)
    if case is None or case.case_type != CaseType.DEFAULT or not case.active:
        raise HTTPException(404, "Clinical case not found")
    return case


def case_language(language: Optional[str], user: User) -> str:
    requested = language or user.preferred_language or "en"
    return requested if requested in get_supported_language_codes() else "en"


@router.get("", response_model=list[ClinicalCaseSimplified])
@router.get("/default", response_model=list[ClinicalCaseSimplified])
async def get_default_cases(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    language: Optional[str] = None,
    case_type: Optional[CaseType] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List active default cases in the requested interface language."""
    if case_type is not None and case_type != CaseType.DEFAULT:
        return []
    cases = ClinicalCaseController(db).get_all_clinical_cases_in_language(
        case_language(language, current_user)
    )
    return cases[skip:skip + limit]


@router.get("/{case_id}", response_model=ClinicalCaseWithOrganization)
async def get_clinical_case(
    case_id: int,
    language: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Read an active default case; custom cases are not part of the catalog."""
    require_default_case(db, case_id)
    case = ClinicalCaseController(db).get_clinical_case_in_language(
        case_id, case_language(language, current_user)
    )
    if case is None:
        raise HTTPException(404, "Clinical case not found")
    if current_user.role != UserRole.SUPERUSER:
        case = ClinicalCaseSimplified.model_validate(case)
    return ClinicalCaseWithOrganization(**case.model_dump(), organization=None)


@router.get("/{case_id}/languages")
async def get_available_languages(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_default_case(db, case_id)
    return {
        "case_id": case_id,
        "available_languages": ClinicalCaseController(db).get_available_languages(case_id),
    }


@router.get("/{case_id}/translation-status")
async def get_translation_status(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_default_case(db, case_id)
    return ClinicalCaseController(db).get_translation_status(case_id)
