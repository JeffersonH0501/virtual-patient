from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.models.user import User, UserRole
from app.models.doctor_feedback import DoctorFeedback
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.doctor_feedback_controller import DoctorFeedbackController


def require_admin_feedback_access(actor: User = Depends(get_current_active_user)):
    """Historical free-text feedback is read-only and restricted to administrators."""
    if actor.role != UserRole.ADMIN:
        raise HTTPException(403, "Historical comments are restricted to administrators")


router = APIRouter(
    prefix="/medical-interviews",
    dependencies=[Depends(require_admin_feedback_access)],
    tags=["medical-interview-doctor-feedback"],
    responses={404: {"description": "Interview or doctor feedback not found"}},
)


@router.get("/{interview_id}/doctor-feedback", response_model=List[DoctorFeedback])
async def get_doctor_feedbacks(
    interview_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List the historical free-text feedback stored for an interview.

    - **interview_id**: Unique identifier for the interview

    Returns the list of historical doctor feedback entries. Restricted to
    administrators; free-text feedback is no longer writable.
    """
    interview_service = MedicalInterviewController(db)
    doctor_feedback_service = DoctorFeedbackController(db)

    interview = interview_service.get_interview(interview_id)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )

    return doctor_feedback_service.get_doctor_feedbacks(interview_id, current_user.id)
