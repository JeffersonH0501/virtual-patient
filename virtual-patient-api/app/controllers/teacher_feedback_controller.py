from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from app.models.teacher_feedback import TeacherFeedbackDB, TeacherFeedbackCreate, TeacherFeedbackUpdate
from app.models.user import UserDB


class TeacherFeedbackController:
    def __init__(self, db: Session):
        self.db = db

    def create_teacher_feedback(
        self, 
        interview_id: int, 
        teacher_id: int, 
        feedback_data: TeacherFeedbackCreate
    ) -> TeacherFeedbackDB:
        """Create a new teacher feedback for an interview"""
        teacher_feedback = TeacherFeedbackDB(
            medical_interview_id=interview_id,
            teacher_id=teacher_id,
            feedback=feedback_data.feedback
        )
        self.db.add(teacher_feedback)
        self.db.commit()
        self.db.refresh(teacher_feedback)
        return teacher_feedback

    def get_teacher_feedbacks(self, interview_id: int, current_user_id: int) -> List[Dict[str, Any]]:
        """Get all teacher feedbacks for an interview with additional fields"""
        feedbacks = self.db.query(TeacherFeedbackDB).options(
            joinedload(TeacherFeedbackDB.teacher)
        ).filter(
            TeacherFeedbackDB.medical_interview_id == interview_id
        ).order_by(TeacherFeedbackDB.created_at.desc()).all()
        
        result = []
        for feedback in feedbacks:
            result.append(self._format_feedback_response(feedback, current_user_id))
        
        return result
    def get_teacher_feedback_formatted(self, feedback_id: int, current_user_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific teacher feedback by ID with additional fields"""
        feedback = self.db.query(TeacherFeedbackDB).options(
            joinedload(TeacherFeedbackDB.teacher)
        ).filter(TeacherFeedbackDB.id == feedback_id).first()
        
        if not feedback:
            return None
            
        return self._format_feedback_response(feedback, current_user_id)
        
    def _format_feedback_response(self, feedback: TeacherFeedbackDB, current_user_id: int) -> Dict[str, Any]:
        """Format a single feedback object with additional fields"""
        return {
            "id": feedback.id,
            "feedback": feedback.feedback,
            "created_at": feedback.created_at,
            "medical_interview_id": feedback.medical_interview_id,
            "teacher_id": feedback.teacher_id,
            "teacher_name": feedback.teacher.name if feedback.teacher else None,
            "reviewed_by_you": feedback.teacher_id == current_user_id
        }

    def get_teacher_feedback_by_id(self, feedback_id: int) -> Optional[TeacherFeedbackDB]:
        """Get a specific teacher feedback by ID"""
        return self.db.query(TeacherFeedbackDB).filter(
            TeacherFeedbackDB.id == feedback_id
        ).first()

    def update_teacher_feedback(
        self, 
        feedback_id: int, 
        teacher_id: int, 
        feedback_data: TeacherFeedbackUpdate
    ) -> Optional[TeacherFeedbackDB]:
        """Update an existing teacher feedback"""
        teacher_feedback = self.db.query(TeacherFeedbackDB).filter(
            and_(
                TeacherFeedbackDB.id == feedback_id,
                TeacherFeedbackDB.teacher_id == teacher_id
            )
        ).first()
        
        if not teacher_feedback:
            return None
            
        if feedback_data.feedback is not None:
            teacher_feedback.feedback = feedback_data.feedback
            
        self.db.commit()
        self.db.refresh(teacher_feedback)
        return teacher_feedback

    def delete_teacher_feedback(self, feedback_id: int, teacher_id: int) -> bool:
        """Delete a teacher feedback"""
        teacher_feedback = self.db.query(TeacherFeedbackDB).filter(
            and_(
                TeacherFeedbackDB.id == feedback_id,
                TeacherFeedbackDB.teacher_id == teacher_id
            )
        ).first()
        
        if not teacher_feedback:
            return False
            
        self.db.delete(teacher_feedback)
        self.db.commit()
        return True
