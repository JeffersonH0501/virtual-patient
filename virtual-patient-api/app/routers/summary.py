"""Language-aware progress summary endpoints."""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.schemas.progress_summary import ProgressSummarySchema
from app.agents.translator_agent import TranslatorAgent
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.message_controller import MessageController
from app.controllers.progress_summary_controller import ProgressSummaryController
from app.controllers.summary_controller import SummaryController
from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.models.medical_interview.progress_summary import ProgressSummary
from app.models.user import User
from app.utils.language import convert_language_code_to_name, resolve_ui_language


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/medical-interviews", tags=["summary"])


class ProcessSummaryResponse(BaseModel):
    """Response returned after resolving a localized progress summary."""

    summary_result: Optional[ProgressSummarySchema] = None


class GetSummaryResponse(BaseModel):
    """Response returned when reading the current localized summary."""

    summary: Optional[ProgressSummarySchema] = None


async def _resolve_localized_summary(
    interview_id: int,
    stored_summary: ProgressSummary,
    language: str,
    controller: ProgressSummaryController,
) -> ProgressSummarySchema:
    """Return a cached translation or create it from the canonical summary."""
    canonical_summary = controller.to_schema(stored_summary)
    if language == stored_summary.source_language or language == "en":
        return canonical_summary

    cached_version = (stored_summary.localized_versions or {}).get(language)
    if cached_version:
        return ProgressSummarySchema(**cached_version)

    translator = TranslatorAgent()
    translated_summary = await translator.translate_progress_summary(
        canonical_summary,
        convert_language_code_to_name(language),
    )
    controller.cache_localized_summary(
        interview_id,
        language,
        translated_summary,
    )
    return translated_summary


@router.post("/{interview_id}/summary", response_model=ProcessSummaryResponse)
async def process_summary(
    interview_id: int,
    language: Optional[Literal["en", "es"]] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Generate or return the progress summary in the interface language."""
    interview_controller = MedicalInterviewController(db)
    message_controller = MessageController(db)
    progress_summary_controller = ProgressSummaryController(db)
    target_language = resolve_ui_language(
        language,
        current_user.preferred_language,
    )

    try:
        _, clinical_case = interview_controller.validate_interview_access_with_case(
            interview_id,
            current_user,
        )
        existing_summary = progress_summary_controller.get_progress_summary(interview_id)
        interview_messages = message_controller.get_interview_messages(interview_id)

        summary_is_current = bool(existing_summary) and (
            not interview_messages
            or existing_summary.updated_at >= interview_messages[-1].created_at
        )
        if existing_summary and summary_is_current:
            localized_summary = await _resolve_localized_summary(
                interview_id,
                existing_summary,
                target_language,
                progress_summary_controller,
            )
            return ProcessSummaryResponse(summary_result=localized_summary)

        formatted_messages = [
            {
                "role": "user" if message.sender_type == "user" else "assistant",
                "content": message.content,
            }
            for message in interview_messages
        ]
        workflow_result = await SummaryController().process_summary(
            interview_id=interview_id,
            messages=formatted_messages,
            clinical_case=clinical_case,
            user_preferred_language=convert_language_code_to_name(target_language),
        )

        canonical_summary = workflow_result.get("summary_result")
        if not canonical_summary:
            return ProcessSummaryResponse(summary_result=None)
        if not isinstance(canonical_summary, ProgressSummarySchema):
            canonical_summary = ProgressSummarySchema(**canonical_summary)

        localized_summary = workflow_result.get("translated_summary") or canonical_summary
        if not isinstance(localized_summary, ProgressSummarySchema):
            localized_summary = ProgressSummarySchema(**localized_summary)

        localized_versions = {"en": canonical_summary.model_dump()}
        if target_language != "en":
            localized_versions[target_language] = localized_summary.model_dump()

        last_message_id = interview_messages[-1].id if interview_messages else None
        if existing_summary:
            progress_summary_controller.update_progress_summary(
                interview_id,
                canonical_summary,
                last_message_id,
                source_language="en",
                localized_versions=localized_versions,
            )
        else:
            progress_summary_controller.create_progress_summary(
                interview_id,
                canonical_summary,
                last_message_id,
                source_language="en",
                localized_versions=localized_versions,
            )

        return ProcessSummaryResponse(summary_result=localized_summary)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Failed to process summary for interview %s", interview_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process interview summary: {error}",
        ) from error


@router.get("/{interview_id}/summary", response_model=GetSummaryResponse)
async def get_summary(
    interview_id: int,
    language: Optional[Literal["en", "es"]] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Read an existing progress summary in the interface language."""
    interview_controller = MedicalInterviewController(db)
    if not interview_controller.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview",
        )

    controller = ProgressSummaryController(db)
    stored_summary = controller.get_progress_summary(interview_id)
    if not stored_summary:
        return GetSummaryResponse(summary=None)

    target_language = resolve_ui_language(language, current_user.preferred_language)
    localized_summary = await _resolve_localized_summary(
        interview_id,
        stored_summary,
        target_language,
        controller,
    )
    return GetSummaryResponse(summary=localized_summary)
