from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.medical_interview import (
    InterviewEvaluationDB, InterviewEvaluation, InterviewEvaluationCreate
)
from app.agents.schemas.evaluation import EvaluationResult
from app.models.medical_interview.interview_evaluation import EvaluationCondition

class InterviewEvaluationController:
    def __init__(self, db: Session):
        self.db = db
    
    def create_evaluation(self, interview_id: int, evaluation_data: InterviewEvaluationCreate, *, commit: bool = True) -> InterviewEvaluation:
        """Create a new interview evaluation"""
        evaluation = InterviewEvaluationDB(
            medical_interview_id=interview_id,
            evaluation_condition=evaluation_data.evaluation_condition.value,
            evaluation_results=[result.model_dump() for result in evaluation_data.evaluation_results],
            overall_score=evaluation_data.overall_score
        )
        
        self.db.add(evaluation)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        self.db.refresh(evaluation)
        
        return InterviewEvaluation.from_orm(evaluation)
    
    def get_evaluation_by_interview_id(self, interview_id: int, condition: EvaluationCondition = EvaluationCondition.TEXT_ONLY) -> Optional[InterviewEvaluation]:
        """Get evaluation for a specific interview"""
        evaluation = self.db.query(InterviewEvaluationDB).filter(
            InterviewEvaluationDB.medical_interview_id == interview_id,
            InterviewEvaluationDB.evaluation_condition == condition.value,
        ).first()
        
        return InterviewEvaluation.from_orm(evaluation) if evaluation else None
    
    def update_evaluation(self, interview_id: int, evaluation_data: InterviewEvaluationCreate, *, commit: bool = True) -> Optional[InterviewEvaluation]:
        """Update existing evaluation"""
        evaluation = self.db.query(InterviewEvaluationDB).filter(
            InterviewEvaluationDB.medical_interview_id == interview_id,
            InterviewEvaluationDB.evaluation_condition == evaluation_data.evaluation_condition.value,
        ).first()
        
        if not evaluation:
            return None
        
        evaluation.evaluation_results = [result.model_dump() for result in evaluation_data.evaluation_results]
        evaluation.overall_score = evaluation_data.overall_score
        
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        self.db.refresh(evaluation)
        
        return InterviewEvaluation.from_orm(evaluation)
    
    def delete_evaluation(self, interview_id: int, condition: EvaluationCondition = EvaluationCondition.TEXT_ONLY) -> bool:
        """Delete evaluation for an interview"""
        evaluation = self.db.query(InterviewEvaluationDB).filter(
            InterviewEvaluationDB.medical_interview_id == interview_id,
            InterviewEvaluationDB.evaluation_condition == condition.value,
        ).first()
        
        if not evaluation:
            return False
        
        self.db.delete(evaluation)
        self.db.commit()
        return True
    
    def calculate_overall_score(self, evaluation_results: List[EvaluationResult]) -> float:
        """Calculate overall score from individual evaluation results"""
        if not evaluation_results:
            return 0
        
        total_score = sum(result.score for result in evaluation_results)
        return round(total_score / len(evaluation_results), 1)
