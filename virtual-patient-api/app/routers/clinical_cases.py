"""Read-only catalog of the default clinical cases supplied with the application."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.controllers.clinical_case_controller import ClinicalCaseController
from app.core.auth import get_current_active_user, require_admin
from app.core.database import get_db
from app.models.clinical_case import (
    CaseType, ClinicalCaseDB, ClinicalCaseSimplified, ClinicalCase,
)
from app.models.user import User, UserRole
from app.utils.language import get_supported_language_codes

router = APIRouter(prefix="/clinical-cases", tags=["clinical-cases"])


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


@router.get("/{case_id}", response_model=ClinicalCase)
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
    if current_user.role != UserRole.ADMIN:
        case = ClinicalCaseSimplified.model_validate(case)
    return case


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
