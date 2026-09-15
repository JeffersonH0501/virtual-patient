from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.medical_interview import (
    UserHypothesisDB, UserHypothesis, UserHypothesisCreate, UserHypothesisUpdate,
    MedicalInterviewDB, InterviewStatus
)

class HypothesisController:
    def __init__(self, db: Session):
        self.db = db
    
    def create_hypothesis(self, interview_id: int, hypothesis_data: UserHypothesisCreate) -> UserHypothesis:
        """Create a new hypothesis"""
        hypothesis = UserHypothesisDB(
            interview_id=interview_id,
            hypothesis_text=hypothesis_data.hypothesis_text,
            hypothesis_order=hypothesis_data.hypothesis_order
        )
        
        self.db.add(hypothesis)
        self.db.commit()
        self.db.refresh(hypothesis)
        
        return UserHypothesis.from_orm(hypothesis)
    
    def create_hypotheses_batch(self, interview_id: int, hypotheses_data: List[UserHypothesisCreate]) -> List[UserHypothesis]:
        """Create or update multiple hypotheses at once.

        Up to three hypotheses may be submitted. The student is not required to
        fill all three, so between one and three are accepted. Each hypothesis
        must have a distinct order within 1..3.
        """
        if not 1 <= len(hypotheses_data) <= 3:
            raise ValueError("Between 1 and 3 hypotheses are required")

        # Validate hypothesis orders: distinct values within the 1..3 range.
        orders = [h.hypothesis_order for h in hypotheses_data]
        if len(set(orders)) != len(orders):
            raise ValueError("Hypothesis orders must be distinct")
        if any(order < 1 or order > 3 for order in orders):
            raise ValueError("Hypothesis orders must be between 1 and 3")
        
        # Check if hypotheses already exist
        existing_hypotheses = self.get_interview_hypotheses(interview_id)
        
        if existing_hypotheses:
            # Update existing hypotheses
            return self.update_hypotheses_batch(interview_id, hypotheses_data)
        else:
            # Create new hypotheses
            hypotheses = []
            for hypothesis_data in hypotheses_data:
                hypothesis = self.create_hypothesis(interview_id, hypothesis_data)
                hypotheses.append(hypothesis)
            return hypotheses
    
    def update_hypotheses_batch(self, interview_id: int, hypotheses_data: List[UserHypothesisCreate]) -> List[UserHypothesis]:
        """Update existing hypotheses for an interview"""
        updated_hypotheses = []
        
        for hypothesis_data in hypotheses_data:
            # Find existing hypothesis by interview_id and order
            existing_hypothesis = self.db.query(UserHypothesisDB).filter(
                and_(
                    UserHypothesisDB.interview_id == interview_id,
                    UserHypothesisDB.hypothesis_order == hypothesis_data.hypothesis_order
                )
            ).first()
            
            if existing_hypothesis:
                # Update existing hypothesis
                existing_hypothesis.hypothesis_text = hypothesis_data.hypothesis_text
                self.db.commit()
                self.db.refresh(existing_hypothesis)
                updated_hypotheses.append(UserHypothesis.from_orm(existing_hypothesis))
            else:
                # Create new hypothesis if it doesn't exist for this order
                new_hypothesis = self.create_hypothesis(interview_id, hypothesis_data)
                updated_hypotheses.append(new_hypothesis)
        
        return updated_hypotheses
    
    def get_interview_hypotheses(self, interview_id: int) -> List[UserHypothesis]:
        """Get all hypotheses for an interview"""
        hypotheses = self.db.query(UserHypothesisDB).filter(
            UserHypothesisDB.interview_id == interview_id
        ).order_by(UserHypothesisDB.hypothesis_order).all()
        
        return [UserHypothesis.from_orm(hypothesis) for hypothesis in hypotheses]
    
    def get_hypothesis(self, hypothesis_id: int) -> Optional[UserHypothesis]:
        """Get a specific hypothesis by ID"""
        hypothesis = self.db.query(UserHypothesisDB).filter(UserHypothesisDB.id == hypothesis_id).first()
        return UserHypothesis.from_orm(hypothesis) if hypothesis else None
    
    def update_hypothesis(self, hypothesis_id: int, update_data: UserHypothesisUpdate) -> Optional[UserHypothesis]:
        """Update hypothesis"""
        hypothesis = self.db.query(UserHypothesisDB).filter(UserHypothesisDB.id == hypothesis_id).first()
        if not hypothesis:
            return None
        
        if update_data.hypothesis_text is not None:
            hypothesis.hypothesis_text = update_data.hypothesis_text
        if update_data.hypothesis_order is not None:
            hypothesis.hypothesis_order = update_data.hypothesis_order
            
        self.db.commit()
        self.db.refresh(hypothesis)
        
        return UserHypothesis.from_orm(hypothesis)
    
    def delete_hypothesis(self, hypothesis_id: int) -> bool:
        """Delete a hypothesis"""
        hypothesis = self.db.query(UserHypothesisDB).filter(UserHypothesisDB.id == hypothesis_id).first()
        if not hypothesis:
            return False
        
        self.db.delete(hypothesis)
        self.db.commit()
        return True
    
    def validate_hypotheses_complete(self, interview_id: int) -> bool:
        """Validate that exactly 3 hypotheses exist for an interview"""
        hypotheses = self.get_interview_hypotheses(interview_id)
        return len(hypotheses) == 3
    
    def can_complete_interview(self, interview_id: int) -> Dict[str, Any]:
        """Check if interview can be completed (has 3 hypotheses)"""
        hypotheses = self.get_interview_hypotheses(interview_id)
        
        return {
            "can_complete": len(hypotheses) == 3,
            "hypothesis_count": len(hypotheses),
            "required_count": 3,
            "missing_count": max(0, 3 - len(hypotheses))
        }
    
    def get_hypothesis_by_order(self, interview_id: int, order: int) -> Optional[UserHypothesis]:
        """Get hypothesis by order (1, 2, or 3)"""
        hypothesis = self.db.query(UserHypothesisDB).filter(
            and_(
                UserHypothesisDB.interview_id == interview_id,
                UserHypothesisDB.hypothesis_order == order
            )
        ).first()
        
        return UserHypothesis.from_orm(hypothesis) if hypothesis else None
    
    def validate_interview_exists(self, interview_id: int) -> bool:
        """Validate that the interview exists"""
        interview = self.db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == interview_id).first()
        return interview is not None
    
    def validate_interview_active(self, interview_id: int) -> bool:
        """Validate that the interview is still active"""
        interview = self.db.query(MedicalInterviewDB).filter(
            and_(
                MedicalInterviewDB.id == interview_id,
                MedicalInterviewDB.status == InterviewStatus.IN_PROGRESS
            )
        ).first()
        return interview is not None 