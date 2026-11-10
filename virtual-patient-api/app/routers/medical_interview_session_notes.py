from app.core.review_access import require_assessments
from app.models.medical_interview import MedicalInterviewDB
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.models.user import User
from app.models.medical_interview import MedicalSessionNote
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.session_note_controller import SessionNoteController

router = APIRouter(
    prefix="/medical-interviews",
    tags=["medical-interview-session-notes"],
    responses={404: {"description": "Interview or session notes not found"}},
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
    
    require_assessments(db, db.get(MedicalInterviewDB, interview_id), current_user)
    notes = session_note_service.get_session_notes(interview_id)
    return notes

