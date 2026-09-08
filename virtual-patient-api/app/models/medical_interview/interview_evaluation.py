from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from sqlalchemy import Column, Integer, Float, ForeignKey, JSON, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.agents.schemas.evaluation import EvaluationResult

# SQLAlchemy Model
class InterviewEvaluationDB(Base):
    __tablename__ = "interview_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    medical_interview_id = Column(Integer, ForeignKey("medical_interviews.id"), nullable=False, index=True, unique=True)
    evaluation_results = Column(JSON, nullable=False)  # Store list of EvaluationResult objects
    overall_score = Column(Float, nullable=True)  # Calculated overall score on the 0-5 scale
    completion_timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship
    medical_interview = relationship("MedicalInterviewDB", back_populates="interview_evaluation")

# Pydantic Models
class InterviewEvaluationBase(BaseModel):
    evaluation_results: List[EvaluationResult]
    overall_score: Optional[float] = Field(None, ge=0, le=5, description="Overall score from 0 to 5")

class InterviewEvaluationCreate(InterviewEvaluationBase):
    pass

class InterviewEvaluation(InterviewEvaluationBase):
    id: int
    medical_interview_id: int
    completion_timestamp: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
