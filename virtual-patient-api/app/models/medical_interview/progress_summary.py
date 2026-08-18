from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Integer, JSON, Float, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

# SQLAlchemy Model
class ProgressSummaryDB(Base):
    __tablename__ = "progress_summaries"
    __table_args__ = (
        Index(
            "ix_progress_summaries_localized_versions",
            "localized_versions",
            postgresql_using="gin",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    medical_interview_id = Column(Integer, ForeignKey("medical_interviews.id"), nullable=False, unique=True, index=True)
    
    # Patient Demographics
    age = Column(Integer, nullable=True)
    weight_in_kg = Column(Float, nullable=True)
    
    # Medical Information (stored as JSON for flexibility)
    current_symptoms = Column(JSON, nullable=True)  # List of symptoms with details
    allergies = Column(JSON, nullable=True)  # List of allergies as strings
    medications = Column(JSON, nullable=True)  # List of medications with details
    diet_information = Column(Text, nullable=True)  # Dietary restrictions, meals, supplements as text
    current_illnesses = Column(JSON, nullable=True)  # Current conditions
    family_history = Column(JSON, nullable=True)  # List of family history entries
    habits = Column(JSON, nullable=True)  # List of habits with details (habit, duration, frequency)
    medical_history = Column(JSON, nullable=True)  # List of medical history events (type, date)
    
    # Work Information
    work_information = Column(Text, nullable=True)  # Short description of the patient's work
    
    # Summary Text
    summary_text = Column(Text, nullable=True)

    # The base fields remain canonical English. Localized copies are cached by
    # interface language and invalidated whenever the canonical summary changes.
    source_language = Column(String(8), nullable=False, default="en")
    localized_versions = Column(JSONB, nullable=False, default=dict)
    
    # Summary Change Tracking
    last_updated_message_id = Column(
        Integer,
        ForeignKey("interview_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    update_count = Column(Integer, default=0)
    confidence_score = Column(Float, default=0.0)  # How confident we are in the summary
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship
    medical_interview = relationship("MedicalInterviewDB", back_populates="progress_summary")

# Pydantic Models
class ProgressSummaryBase(BaseModel):
    age: Optional[int] = None
    weight_in_kg: Optional[float] = None
    current_symptoms: Optional[List[Dict[str, Any]]] = None
    allergies: Optional[List[str]] = None
    medications: Optional[List[Dict[str, Any]]] = None
    diet_information: Optional[str] = None
    current_illnesses: Optional[List[Dict[str, Any]]] = None
    family_history: Optional[List[Dict[str, Any]]] = None
    habits: Optional[List[Dict[str, Any]]] = None
    medical_history: Optional[List[Dict[str, Any]]] = None
    work_information: Optional[str] = None
    summary_text: Optional[str] = None

class ProgressSummaryCreate(ProgressSummaryBase):
    pass

class ProgressSummaryUpdate(BaseModel):
    age: Optional[int] = None
    weight_in_kg: Optional[float] = None
    current_symptoms: Optional[List[Dict[str, Any]]] = None
    allergies: Optional[List[str]] = None
    medications: Optional[List[Dict[str, Any]]] = None
    diet_information: Optional[str] = None
    current_illnesses: Optional[List[Dict[str, Any]]] = None
    family_history: Optional[List[Dict[str, Any]]] = None
    habits: Optional[List[Dict[str, Any]]] = None
    medical_history: Optional[List[Dict[str, Any]]] = None
    work_information: Optional[str] = None
    summary_text: Optional[str] = None

class ProgressSummary(ProgressSummaryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    medical_interview_id: int
    last_updated_message_id: Optional[int] = None
    update_count: int = 0
    confidence_score: float = 0.0
    source_language: str = "en"
    localized_versions: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
