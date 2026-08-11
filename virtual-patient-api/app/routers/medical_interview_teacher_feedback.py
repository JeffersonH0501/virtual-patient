from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.models.user import User, UserRole
from app.models.teacher_feedback import TeacherFeedback, TeacherFeedbackCreate, TeacherFeedbackUpdate
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.teacher_feedback_controller import TeacherFeedbackController

router = APIRouter(
    prefix="/medical-interviews",
    tags=["medical-interview-teacher-feedback"],
    responses={404: {"description": "Interview or teacher feedback not found"}},
)


@router.get("/{interview_id}/teacher-feedback", response_model=List[TeacherFeedback])
async def get_teacher_feedbacks(
    interview_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get all teacher feedbacks for an interview.
    
    - **interview_id**: Unique identifier for the interview
    
    Returns the list of teacher feedbacks for the interview.
    - Teachers can access feedback for any interview
    - Students can only access feedback for their own interviews
    """
    interview_service = MedicalInterviewController(db)
    teacher_feedback_service = TeacherFeedbackController(db)
    
    # Validate interview exists
    interview = interview_service.get_interview(interview_id)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    # Check access permissions
    # Teachers and superusers can access any interview feedback
    # Students can only access feedback for their own interviews
    if current_user.role != UserRole.TEACHER.value and current_user.role != UserRole.SUPERUSER.value:
        if interview.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only access teacher feedback for your own interviews"
            )
    
    feedbacks = teacher_feedback_service.get_teacher_feedbacks(interview_id, current_user.id)
    return feedbacks


@router.post("/{interview_id}/teacher-feedback", response_model=TeacherFeedback)
async def create_teacher_feedback(
    interview_id: int,
    feedback_data: TeacherFeedbackCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new teacher feedback for an interview.
    
    - **interview_id**: Unique identifier for the interview
    - **feedback_data**: Teacher feedback content
    
    Only teachers can create feedback.
    Returns the created teacher feedback.
    """
    # Check if user is a teacher or superuser
    if current_user.role != UserRole.TEACHER.value and current_user.role != UserRole.SUPERUSER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers and superusers can create teacher feedback"
        )
    
    interview_service = MedicalInterviewController(db)
    teacher_feedback_service = TeacherFeedbackController(db)
    
    # Validate interview exists
    interview = interview_service.get_interview(interview_id)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    try:
        feedback = teacher_feedback_service.create_teacher_feedback(
            interview_id=interview_id,
            teacher_id=current_user.id,
            feedback_data=feedback_data
        )
        return teacher_feedback_service.get_teacher_feedback_formatted(feedback.id, current_user.id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating teacher feedback: {str(e)}"
        )


@router.post("/{interview_id}/teacher-feedback/{feedback_id}", response_model=TeacherFeedback)
async def update_teacher_feedback(
    interview_id: int,
    feedback_id: int,
    feedback_data: TeacherFeedbackUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update an existing teacher feedback for an interview.
    
    - **interview_id**: Unique identifier for the interview
    - **feedback_id**: Unique identifier for the teacher feedback
    - **feedback_data**: Updated teacher feedback content
    
    Only the teacher who created the feedback can update it.
    Returns the updated teacher feedback.
    """
    # Check if user is a teacher or superuser
    if current_user.role != UserRole.TEACHER.value and current_user.role != UserRole.SUPERUSER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers and superusers can update teacher feedback"
        )
    
    interview_service = MedicalInterviewController(db)
    teacher_feedback_service = TeacherFeedbackController(db)
    
    # Validate interview exists
    interview = interview_service.get_interview(interview_id)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    # Validate feedback exists and belongs to the teacher
    existing_feedback = teacher_feedback_service.get_teacher_feedback_by_id(feedback_id)
    if not existing_feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher feedback not found"
        )
    
    if existing_feedback.medical_interview_id != interview_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feedback does not belong to this interview"
        )
    
    try:
        updated_feedback = teacher_feedback_service.update_teacher_feedback(
            feedback_id=feedback_id,
            teacher_id=current_user.id,
            feedback_data=feedback_data
        )
        
        if not updated_feedback:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own feedback"
            )
        
        return teacher_feedback_service.get_teacher_feedback_formatted(feedback_id, current_user.id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating teacher feedback: {str(e)}"
        )
