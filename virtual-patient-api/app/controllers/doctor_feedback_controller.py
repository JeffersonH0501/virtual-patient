from typing import List, Dict, Any
from sqlalchemy.orm import Session, joinedload
from app.models.doctor_feedback import DoctorFeedbackDB


class DoctorFeedbackController:
    def __init__(self, db: Session):
        self.db = db

    def get_doctor_feedbacks(self, interview_id: int, current_user_id: int) -> List[Dict[str, Any]]:
        """Get all doctor feedbacks for an interview with additional fields"""
        feedbacks = self.db.query(DoctorFeedbackDB).options(
            joinedload(DoctorFeedbackDB.doctor)
        ).filter(
            DoctorFeedbackDB.medical_interview_id == interview_id
        ).order_by(DoctorFeedbackDB.created_at.desc()).all()

        return [self._format_feedback_response(feedback, current_user_id) for feedback in feedbacks]

    def _format_feedback_response(self, feedback: DoctorFeedbackDB, current_user_id: int) -> Dict[str, Any]:
        """Format a single feedback object with additional fields"""
        return {
            "id": feedback.id,
            "feedback": feedback.feedback,
            "created_at": feedback.created_at,
            "medical_interview_id": feedback.medical_interview_id,
            "doctor_id": feedback.doctor_id,
            "doctor_name": feedback.doctor.name if feedback.doctor else None,
            "reviewed_by_you": feedback.doctor_id == current_user_id
        }
