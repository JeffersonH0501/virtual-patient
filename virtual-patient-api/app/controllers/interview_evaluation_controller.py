from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.medical_interview import (
    InterviewEvaluationDB, InterviewEvaluation, InterviewEvaluationCreate
)
from app.agents.schemas.evaluation import EvaluationResult

class InterviewEvaluationController:
    def __init__(self, db: Session):
        self.db = db
    
    def create_evaluation(self, interview_id: int, evaluation_data: InterviewEvaluationCreate) -> InterviewEvaluation:
        """Create a new interview evaluation"""
        evaluation = InterviewEvaluationDB(
            medical_interview_id=interview_id,
            evaluation_results=[result.model_dump() for result in evaluation_data.evaluation_results],
            overall_score=evaluation_data.overall_score
        )
        
        self.db.add(evaluation)
        self.db.commit()
        self.db.refresh(evaluation)
        
        return InterviewEvaluation.from_orm(evaluation)
    
    def get_evaluation_by_interview_id(self, interview_id: int) -> Optional[InterviewEvaluation]:
        """Get evaluation for a specific interview"""
        evaluation = self.db.query(InterviewEvaluationDB).filter(
            InterviewEvaluationDB.medical_interview_id == interview_id
        ).first()
        
        return InterviewEvaluation.from_orm(evaluation) if evaluation else None
    
    def update_evaluation(self, interview_id: int, evaluation_data: InterviewEvaluationCreate) -> Optional[InterviewEvaluation]:
        """Update existing evaluation"""
        evaluation = self.db.query(InterviewEvaluationDB).filter(
            InterviewEvaluationDB.medical_interview_id == interview_id
        ).first()
        
        if not evaluation:
            return None
        
        evaluation.evaluation_results = [result.model_dump() for result in evaluation_data.evaluation_results]
        evaluation.overall_score = evaluation_data.overall_score
        
        self.db.commit()
        self.db.refresh(evaluation)
        
        return InterviewEvaluation.from_orm(evaluation)
    
    def delete_evaluation(self, interview_id: int) -> bool:
        """Delete evaluation for an interview"""
        evaluation = self.db.query(InterviewEvaluationDB).filter(
            InterviewEvaluationDB.medical_interview_id == interview_id
        ).first()
        
        if not evaluation:
            return False
        
        self.db.delete(evaluation)
        self.db.commit()
        return True
    
    def calculate_overall_score(self, evaluation_results: List[EvaluationResult]) -> int:
        """Calculate overall score from individual evaluation results"""
        if not evaluation_results:
            return 0
        
        total_score = sum(result.score for result in evaluation_results)
        return round(total_score / len(evaluation_results))
