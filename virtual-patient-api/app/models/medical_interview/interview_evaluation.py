from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from sqlalchemy import Column, Integer, Float, ForeignKey, JSON, DateTime, String, UniqueConstraint, CheckConstraint, event
import uuid
from enum import Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.agents.schemas.evaluation import EvaluationResult
from app.agents.schemas.multimodal_evaluation import MultimodalEvaluationResult


class EvaluationCondition(str, Enum):
    TEXT_ONLY = "TEXT_ONLY"
    TEXT_PLUS_MULTIMODAL = "TEXT_PLUS_MULTIMODAL"


class InterviewEvaluationRunDB(Base):
    """Append-only snapshots; interview erasure cascades at the database level."""

    __tablename__ = "interview_evaluation_runs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    medical_interview_id = Column(Integer, ForeignKey("medical_interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    evaluation_condition = Column(String(32), nullable=False)
    snapshot = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


@event.listens_for(InterviewEvaluationRunDB, "before_update")
def reject_run_update(mapper, connection, target):
    raise ValueError("Evaluation run snapshots cannot be updated")

# SQLAlchemy Model
class InterviewEvaluationDB(Base):
    __tablename__ = "interview_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    medical_interview_id = Column(Integer, ForeignKey("medical_interviews.id"), nullable=False, index=True)
    evaluation_condition = Column(String(32), nullable=False, default=EvaluationCondition.TEXT_ONLY.value, server_default="TEXT_ONLY")
    evaluation_results = Column(JSON, nullable=False)  # Store list of EvaluationResult objects
    overall_score = Column(Float, nullable=True)  # Calculated overall score on the 0-5 scale
    completion_timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship
    medical_interview = relationship("MedicalInterviewDB", back_populates="interview_evaluations")
    __table_args__ = (
        UniqueConstraint("medical_interview_id", "evaluation_condition", name="uq_interview_evaluation_condition"),
        CheckConstraint("evaluation_condition IN ('TEXT_ONLY', 'TEXT_PLUS_MULTIMODAL')", name="ck_interview_evaluation_condition"),
    )

# Pydantic Models
class InterviewEvaluationBase(BaseModel):
    evaluation_condition: EvaluationCondition = EvaluationCondition.TEXT_ONLY
    evaluation_results: List[EvaluationResult | MultimodalEvaluationResult]
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
