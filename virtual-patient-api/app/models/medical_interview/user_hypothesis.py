from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy import Column, Text, ForeignKey, Integer, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base

# SQLAlchemy Model
class UserHypothesisDB(Base):
    __tablename__ = "user_hypotheses"

    id = Column(Integer, primary_key=True, index=True)
    interview_id = Column(Integer, ForeignKey("medical_interviews.id"), nullable=False, index=True)
    hypothesis_text = Column(Text, nullable=False)
    hypothesis_order = Column(Integer, nullable=False)

    # Relationship
    medical_interview = relationship("MedicalInterviewDB", back_populates="hypotheses")

    # Constraints
    __table_args__ = (
        CheckConstraint('hypothesis_order >= 1 AND hypothesis_order <= 3', name='chk_hypothesis_order'),
        UniqueConstraint('interview_id', 'hypothesis_order', name='uq_interview_hypothesis_order'),
    )

# Pydantic Models
class UserHypothesisBase(BaseModel):
    hypothesis_text: str
    hypothesis_order: int = Field(..., ge=1, le=3)

class UserHypothesisCreate(UserHypothesisBase):
    pass

class UserHypothesisUpdate(BaseModel):
    hypothesis_text: Optional[str] = None
    hypothesis_order: Optional[int] = None
    # Add other updatable fields if needed (e.g., confidence_level, reasoning)

class UserHypothesis(UserHypothesisBase):
    id: int
    interview_id: int

    class Config:
        from_attributes = True 