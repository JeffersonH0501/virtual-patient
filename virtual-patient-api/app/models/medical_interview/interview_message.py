from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum, Integer, JSON, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
from .enums import SenderType

# SQLAlchemy Model
class InterviewMessageDB(Base):
    __tablename__ = "interview_messages"

    id = Column(Integer, primary_key=True, index=True)
    interview_id = Column(Integer, ForeignKey("medical_interviews.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    sender_type = Column(String(20), nullable=False)
    message_metadata = Column(JSON, nullable=True)  # Additional message-specific data (tone, intent, etc.)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    audio_url = Column(String, nullable=True)

    # Relationship
    medical_interview = relationship("MedicalInterviewDB", back_populates="messages")

# Pydantic Models
class InterviewMessageBase(BaseModel):
    content: str
    sender_type: str
    message_metadata: Optional[Dict[str, Any]]
    audio_url: Optional[str] = None

class InterviewMessageCreate(InterviewMessageBase):
    pass

class InterviewMessage(InterviewMessageBase):
    id: int
    interview_id: int
    created_at: datetime
    audio_url: Optional[str] = None

    class Config:
        from_attributes = True
        populate_by_name = True 