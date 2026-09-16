from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from typing import List, Optional, Dict
from app.models.clinical_case import (
    ClinicalCase, ClinicalCaseCreate, ClinicalCaseUpdate, ClinicalCaseDB, 
    ClinicalCaseWithOrganization, ClinicalCaseSimplified, CaseType, CreatedByUser
)
from app.models.organization import OrganizationDB
from app.models.user import User
from app.core.auth import get_current_active_user
from app.core.database import get_db
from app.controllers.clinical_case_controller import ClinicalCaseController
from app.utils.language import get_supported_language_codes

router = APIRouter(
    prefix="/clinical-cases",
    tags=["clinical-cases"]
)

@router.post("", response_model=ClinicalCase, status_code=status.HTTP_201_CREATED)
async def create_clinical_case(
    clinical_case: ClinicalCaseCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # If custom case, validate organization exists
    if clinical_case.case_type == CaseType.CUSTOM and clinical_case.organization_id:
        organization = db.query(OrganizationDB).filter(
            OrganizationDB.id == clinical_case.organization_id,
            OrganizationDB.active == True
        ).first()
        if not organization:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization not found"
            )
    
    # Create clinical case with translations using controller
    controller = ClinicalCaseController(db)
    # Pass user ID for custom cases
    user_id = current_user.id if clinical_case.case_type == CaseType.CUSTOM else None
    try:
        db_case = await controller.create_clinical_case_with_translations(clinical_case, user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # Load creator relationship if exists
    if db_case.created_by:
        db.refresh(db_case, ['creator'])
    
    # Convert to Pydantic model with created_by_user
    case_dict = {
        **{k: v for k, v in db_case.__dict__.items() if not k.startswith('_')},
        'created_by_user': CreatedByUser(id=db_case.creator.id, name=db_case.creator.name) if db_case.creator else None
    }
    return ClinicalCase(**case_dict)

@router.get("", response_model=List[ClinicalCaseSimplified])
async def get_clinical_cases(
    skip: int = 0,
    limit: int = 100,
    case_type: Optional[CaseType] = None,
    organization_id: Optional[str] = None,
    language: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get clinical cases in the user's preferred language or specified language
    """
    # Use specified language or fall back to user's preferred language
    target_language = language or current_user.preferred_language or "en"
    
    # Validate language code
    if target_language not in get_supported_language_codes():
        target_language = "en"
    
    controller = ClinicalCaseController(db)
    
    if organization_id:
        # Get cases for specific organization
        cases = controller.get_clinical_cases_by_organization_in_language(
            int(organization_id), target_language
        )
    else:
        # Get all cases
        cases = controller.get_all_clinical_cases_in_language(target_language)
    
    # Apply filters
    if case_type:
        cases = [case for case in cases if case.case_type == case_type]
    
    # Apply pagination
    return cases[skip:skip + limit]

@router.get("/default", response_model=List[ClinicalCaseSimplified])
async def get_default_cases(
    skip: int = 0,
    limit: int = 100,
    language: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all default clinical cases in the user's preferred language"""
    # Use specified language or fall back to user's preferred language
    target_language = language or current_user.preferred_language or "en"
    
    # Validate language code
    if target_language not in get_supported_language_codes():
        target_language = "en"
    
    controller = ClinicalCaseController(db)
    cases = controller.get_all_clinical_cases_in_language(target_language)
    
    # Filter for default cases only
    default_cases = [case for case in cases if case.case_type == CaseType.DEFAULT]
    
    # Apply pagination
    return default_cases[skip:skip + limit]

@router.get("/organization/{organization_id}", response_model=List[ClinicalCaseSimplified])
async def get_organization_cases(
    organization_id: str,
    skip: int = 0,
    limit: int = 100,
    language: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all custom cases for a specific organization in the user's preferred language"""
    # Use specified language or fall back to user's preferred language
    target_language = language or current_user.preferred_language or "en"
    
    # Validate language code
    if target_language not in get_supported_language_codes():
        target_language = "en"
    
    controller = ClinicalCaseController(db)
    cases = controller.get_clinical_cases_by_organization_in_language(
        int(organization_id), target_language, current_user.id
    )
    
    # Filter for custom cases only
    custom_cases = [case for case in cases if case.case_type == CaseType.CUSTOM]
    
    # Apply pagination
    return custom_cases[skip:skip + limit]

@router.get("/{case_id}", response_model=ClinicalCaseWithOrganization)
async def get_clinical_case(
    case_id: int,
    language: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific clinical case in the user's preferred language"""
    # Use specified language or fall back to user's preferred language
    target_language = language or current_user.preferred_language or "en"
    
    # Validate language code
    if target_language not in get_supported_language_codes():
        target_language = "en"
    
    # Get the clinical case with creator relationship
    db_case = db.query(ClinicalCaseDB).options(
        selectinload(ClinicalCaseDB.creator)
    ).filter(ClinicalCaseDB.id == case_id).first()
    
    if db_case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical case not found"
        )
    
    controller = ClinicalCaseController(db)
    case_data = controller.get_clinical_case_in_language(case_id, target_language)
    
    if case_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical case not found"
        )
    
    # Add created_by_user if creator exists
    case_dict = case_data.dict()
    if db_case.creator:
        case_dict['created_by_user'] = CreatedByUser(
            id=db_case.creator.id,
            name=db_case.creator.name
        )
    else:
        case_dict['created_by_user'] = None
    
    # Get organization data if exists
    if case_data.organization_id:
        organization = db.query(OrganizationDB).filter(
            OrganizationDB.id == case_data.organization_id
        ).first()
        if organization:
            # Create the response with organization data
            from app.models.organization import Organization
            org_data = Organization(
                id=organization.id,
                name=organization.name,
                active=organization.active
            )
            return ClinicalCaseWithOrganization(
                **case_dict,
                organization=org_data
            )
    
    return ClinicalCase(**case_dict)

@router.post("/{case_id}", response_model=ClinicalCase)
async def update_clinical_case(
    case_id: int,
    case_update: ClinicalCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    controller = ClinicalCaseController(db)
    
    # Check if case exists
    db_case = controller.get_clinical_case(case_id)
    if db_case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical case not found"
        )
    
    # If updating to custom case with organization, validate organization exists
    update_data = case_update.dict(exclude_unset=True)
    if ("case_type" in update_data and update_data["case_type"] == CaseType.CUSTOM and 
        "organization_id" in update_data and update_data["organization_id"]):
        organization = db.query(OrganizationDB).filter(
            OrganizationDB.id == update_data["organization_id"],
            OrganizationDB.active == True
        ).first()
        if not organization:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization not found"
            )
    
    # Update clinical case with translations using controller
    try:
        updated_case = await controller.update_clinical_case_with_translations(case_id, case_update)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    if updated_case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical case not found"
        )
    
    # Load creator relationship if exists
    if updated_case.created_by:
        db.refresh(updated_case, ['creator'])
    
    # Convert to Pydantic model with created_by_user
    case_dict = {
        **{k: v for k, v in updated_case.__dict__.items() if not k.startswith('_')},
        'created_by_user': CreatedByUser(id=updated_case.creator.id, name=updated_case.creator.name) if updated_case.creator else None
    }
    return ClinicalCase(**case_dict)

@router.delete("/{case_id}")
async def delete_clinical_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    db_case = db.query(ClinicalCaseDB).filter(ClinicalCaseDB.id == case_id).first()
    if db_case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical case not found"
        )
    
    # Soft delete - set active to False
    db_case.active = False
    db.commit()
    
    return {"message": "Clinical case deleted successfully"}

# Translation management endpoints
@router.post("/{case_id}/translations/{field_name}")
async def update_field_translation(
    case_id: int,
    field_name: str,
    language: str,
    translation_data: Dict[str, str],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update a specific field translation for a clinical case"""
    # Validate language code
    if language not in get_supported_language_codes():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported language: {language}"
        )
    
    controller = ClinicalCaseController(db)
    translated_text = translation_data.get("text", "")
    
    updated_case = controller.update_field_translation(case_id, field_name, language, translated_text)
    if not updated_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical case not found"
        )
    
    return {"message": f"Translation updated for {field_name} in {language}"}

@router.get("/{case_id}/languages")
async def get_available_languages(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get available languages for a clinical case"""
    controller = ClinicalCaseController(db)
    available_languages = controller.get_available_languages(case_id)
    
    if not available_languages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical case not found"
        )
    
    return {"case_id": case_id, "available_languages": available_languages}

@router.get("/{case_id}/translation-status")
async def get_translation_status(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get translation status for a clinical case"""
    controller = ClinicalCaseController(db)
    status = controller.get_translation_status(case_id)
    
    if not status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical case not found"
        )
    
    return status 