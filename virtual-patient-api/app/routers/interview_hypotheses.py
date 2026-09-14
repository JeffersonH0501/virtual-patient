from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.models.user import User
from app.models.medical_interview import (
    UserHypothesis, UserHypothesisCreate, UserHypothesisUpdate
)
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.hypothesis_controller import HypothesisController

router = APIRouter(
    prefix="/medical-interviews", 
    tags=["interview-hypotheses"],
    responses={404: {"description": "Interview or hypothesis not found"}},
)

class HypothesisStatusResponse(BaseModel):
    submitted_count: int
    required_count: int = 3
    is_complete: bool
    hypotheses: List[UserHypothesis]

@router.post("/{interview_id}/hypotheses", response_model=List[UserHypothesis])
async def submit_hypotheses(
    interview_id: int,
    hypotheses_data: List[UserHypothesisCreate],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Submit or update diagnostic hypotheses for an interview.
    
    Each interview requires exactly 3 hypotheses to be submitted.
    Hypotheses must have unique order numbers (1, 2, 3).
    If hypotheses already exist for this interview, they will be updated.
    
    - **interview_id**: Unique identifier for the interview
    - **hypotheses**: List of exactly 3 hypotheses with order and text
    
    Returns the created or updated hypotheses.
    """
    interview_service = MedicalInterviewController(db)
    hypothesis_service = HypothesisController(db)

    print(f"Submitting/updating hypotheses for interview {interview_id}")
    
    # Validate access
    if not interview_service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )

    print(f"Validating access for interview {interview_id}")
    
    # Validate interview exists and is active
    interview = interview_service.get_interview(interview_id)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )

    print(f"Interview found: {interview}")
    
    if interview.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview is not active"
        )
    if interview.start_time is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The interview has not started",
        )
    
    try:
        hypotheses = hypothesis_service.create_hypotheses_batch(
            interview_id=interview_id,
            hypotheses_data=hypotheses_data
        )
        return hypotheses
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/{interview_id}/hypotheses", response_model=List[UserHypothesis])
async def get_hypotheses(
    interview_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get all hypotheses for an interview.
    
    - **interview_id**: Unique identifier for the interview
    
    Returns a list of all submitted hypotheses.
    """
    interview_service = MedicalInterviewController(db)
    hypothesis_service = HypothesisController(db)
    
    # Validate access
    if not interview_service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )
    
    # Validate interview exists
    if not interview_service.get_interview(interview_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    hypotheses = hypothesis_service.get_interview_hypotheses(interview_id)
    return hypotheses

@router.get("/{interview_id}/hypotheses/{hypothesis_id}", response_model=UserHypothesis)
async def get_hypothesis(
    interview_id: int,
    hypothesis_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific hypothesis by ID.
    
    - **interview_id**: Unique identifier for the interview
    - **hypothesis_id**: Unique identifier for the hypothesis
    
    Returns the specific hypothesis if it belongs to the interview.
    """
    interview_service = MedicalInterviewController(db)
    hypothesis_service = HypothesisController(db)
    
    # Validate access
    if not interview_service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )
    
    hypothesis = hypothesis_service.get_hypothesis(hypothesis_id)
    if not hypothesis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hypothesis not found"
        )
    
    # Validate hypothesis belongs to this interview
    if hypothesis.interview_id != interview_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hypothesis does not belong to this interview"
        )
    
    return hypothesis

@router.post("/{interview_id}/hypotheses/{hypothesis_id}", response_model=UserHypothesis)
async def update_hypothesis(
    interview_id: int,
    hypothesis_id: int,
    update_data: UserHypothesisUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update a specific hypothesis.
    
    - **interview_id**: Unique identifier for the interview
    - **hypothesis_id**: Unique identifier for the hypothesis
    - **update_data**: Fields to update (hypothesis_text, confidence_level, reasoning)
    
    Returns the updated hypothesis.
    """
    interview_service = MedicalInterviewController(db)
    hypothesis_service = HypothesisController(db)
    
    # Validate access
    if not interview_service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )
    
    # Validate hypothesis exists and belongs to interview
    hypothesis = hypothesis_service.get_hypothesis(hypothesis_id)
    if not hypothesis or hypothesis.interview_id != interview_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hypothesis not found"
        )
    
    updated_hypothesis = hypothesis_service.update_hypothesis(hypothesis_id, update_data)
    if not updated_hypothesis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hypothesis not found"
        )
    
    return updated_hypothesis

@router.delete("/{interview_id}/hypotheses/{hypothesis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hypothesis(
    interview_id: int,
    hypothesis_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete a specific hypothesis.
    
    - **interview_id**: Unique identifier for the interview
    - **hypothesis_id**: Unique identifier for the hypothesis
    
    Permanently deletes the hypothesis from the interview.
    """
    interview_service = MedicalInterviewController(db)
    hypothesis_service = HypothesisController(db)
    
    # Validate access
    if not interview_service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )
    
    # Validate hypothesis exists and belongs to interview
    hypothesis = hypothesis_service.get_hypothesis(hypothesis_id)
    if not hypothesis or hypothesis.interview_id != interview_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hypothesis not found"
        )
    
    success = hypothesis_service.delete_hypothesis(hypothesis_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hypothesis not found"
        )
    
    return None

@router.get("/{interview_id}/hypotheses/status", response_model=HypothesisStatusResponse)
async def get_hypothesis_status(
    interview_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get the status of hypothesis submission for an interview.
    
    - **interview_id**: Unique identifier for the interview
    
    Returns the count of submitted hypotheses and completion status.
    """
    interview_service = MedicalInterviewController(db)
    hypothesis_service = HypothesisController(db)
    
    # Validate access
    if not interview_service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )
    
    # Validate interview exists
    if not interview_service.get_interview(interview_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    hypotheses = hypothesis_service.get_interview_hypotheses(interview_id)
    submitted_count = len(hypotheses)
    is_complete = submitted_count >= 3
    
    return HypothesisStatusResponse(
        submitted_count=submitted_count,
        required_count=3,
        is_complete=is_complete,
        hypotheses=hypotheses
    )
