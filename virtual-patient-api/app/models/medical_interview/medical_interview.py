from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, JSON, Integer
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.clinical_case import (ClinicalCaseSimplified)
from app.models.personality import PersonalitySimplified
from .enums import InterviewStatus
import uuid

# SQLAlchemy Model
class MedicalInterviewDB(Base):
    __tablename__ = "medical_interviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    clinical_case_id = Column(Integer, ForeignKey("clinical_cases.id"), nullable=False, index=True)
    start_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(InterviewStatus, name='interview_status'), nullable=False, default=InterviewStatus.ACTIVE)
    interview_metadata = Column(JSON, nullable=True)  # Additional interview-level information
    total_duration = Column(Integer, nullable=True)
    patient_name = Column(String, nullable=True)
    patient_photo = Column(String, nullable=True)
    patient_gender = Column(String, nullable=True)
    personality_id = Column(Integer, ForeignKey("personalities.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("UserDB", back_populates="medical_interviews")
    clinical_case = relationship("ClinicalCaseDB")
    personality = relationship("PersonalityDB")
    messages = relationship("InterviewMessageDB", back_populates="medical_interview", cascade="all, delete-orphan", order_by="InterviewMessageDB.created_at")
    hypotheses = relationship("UserHypothesisDB", back_populates="medical_interview", cascade="all, delete-orphan")
    session_notes = relationship("MedicalSessionNoteDB", back_populates="medical_interview", cascade="all, delete-orphan")
    progress_summary = relationship("ProgressSummaryDB", back_populates="medical_interview", uselist=False, cascade="all, delete-orphan")
    interview_evaluation = relationship("InterviewEvaluationDB", back_populates="medical_interview", uselist=False, cascade="all, delete-orphan")
    teacher_feedback = relationship("TeacherFeedbackDB", back_populates="medical_interview", cascade="all, delete-orphan")

# Pydantic Models
class MedicalInterviewBase(BaseModel):
    clinical_case_id: int = Field(..., description="ID of the clinical case for this interview")
    status: InterviewStatus = InterviewStatus.ACTIVE
    interview_metadata: Optional[Dict[str, Any]] = None
    patient_name: Optional[str] = None
    patient_photo: Optional[str] = None
    patient_gender: Optional[str] = None
    personality_id: Optional[int] = None

class MedicalInterviewCreate(MedicalInterviewBase):
    patient_response_language: Literal["en", "es"] = "en"

class MedicalInterviewUpdate(BaseModel):
    status: Optional[InterviewStatus] = None
    end_time: Optional[datetime] = None
    interview_metadata: Optional[Dict[str, Any]] = None
    patient_name: Optional[str] = None
    patient_photo: Optional[str] = None
    patient_gender: Optional[str] = None
    personality_id: Optional[int] = None

class MedicalInterview(MedicalInterviewBase):
    id: int
    user_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    total_duration: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    clinical_case: ClinicalCaseSimplified
    personality: Optional[PersonalitySimplified] = None

    class Config:
        from_attributes = True
        populate_by_name = True

class MedicalInterviewWithScore(MedicalInterview):
    evaluation_score: Optional[int] = Field(None, ge=1, le=10, description="Overall evaluation score from 1 to 10")
