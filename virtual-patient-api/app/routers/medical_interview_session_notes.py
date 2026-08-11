from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.models.user import User
from app.models.medical_interview import MedicalSessionNote, MedicalSessionNoteCreate
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.session_note_controller import SessionNoteController

router = APIRouter(
    prefix="/medical-interviews",
    tags=["medical-interview-session-notes"],
    responses={404: {"description": "Interview or session notes not found"}},
)


@router.post("/{interview_id}/session-notes", response_model=List[MedicalSessionNote])
async def update_session_notes(
    interview_id: int,
    notes_data: List[MedicalSessionNoteCreate],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update session notes for an interview.
    
    - **interview_id**: Unique identifier for the interview
    - **notes_data**: List of session notes to update (replaces all existing notes)
    
    This endpoint replaces all existing session notes for the interview with the provided notes.
    Returns the updated list of session notes.
    """
    interview_service = MedicalInterviewController(db)
    session_note_service = SessionNoteController(db)
    
    # Validate access
    if not interview_service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )
    
    # Validate interview exists
    interview = interview_service.get_interview(interview_id)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    try:
        notes = session_note_service.update_or_create_session_notes(interview_id, notes_data)
        return notes
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating session notes: {str(e)}"
        )


@router.get("/{interview_id}/session-notes", response_model=List[MedicalSessionNote])
async def get_session_notes(
    interview_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get all session notes for an interview.
    
    - **interview_id**: Unique identifier for the interview
    
    Returns the list of session notes for the interview.
    """
    interview_service = MedicalInterviewController(db)
    session_note_service = SessionNoteController(db)
    
    # Validate access
    if not interview_service.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )
    
    # Validate interview exists
    interview = interview_service.get_interview(interview_id)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    notes = session_note_service.get_session_notes(interview_id)
    return notes

