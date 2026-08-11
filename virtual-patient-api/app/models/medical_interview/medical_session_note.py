from __future__ import annotations
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

# SQLAlchemy Model
class MedicalSessionNoteDB(Base):
    __tablename__ = "session_notes"

    id = Column(Integer, primary_key=True, index=True)
    interview_id = Column(Integer, ForeignKey("medical_interviews.id"), nullable=False, index=True)
    notes_content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship
    medical_interview = relationship("MedicalInterviewDB", back_populates="session_notes")

# Pydantic Models
class MedicalSessionNoteBase(BaseModel):
    notes_content: str

class MedicalSessionNoteCreate(MedicalSessionNoteBase):
    pass

class MedicalSessionNote(MedicalSessionNoteBase):
    id: int
    interview_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True 