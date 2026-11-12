from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.core.database import Base


class DoctorFeedbackDB(Base):
    __tablename__ = "doctor_feedback"

    id = Column(Integer, primary_key=True, index=True)
    feedback = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Foreign keys
    medical_interview_id = Column(Integer, ForeignKey("medical_interviews.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Relationships
    medical_interview = relationship("MedicalInterviewDB", back_populates="doctor_feedback")
    doctor = relationship("UserDB")


# Pydantic Models
class DoctorFeedbackBase(BaseModel):
    feedback: str = Field(..., description="Doctor feedback content")


class DoctorFeedbackFull(DoctorFeedbackBase):
    medical_interview_id: int = Field(..., description="ID of the medical interview")
    doctor_id: int = Field(..., description="ID of the doctor giving feedback")


class DoctorFeedback(DoctorFeedbackFull):
    id: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    doctor_name: Optional[str] = None
    reviewed_by_you: Optional[bool] = Field(None, description="Whether this feedback was created by the current user")

    class Config:
        from_attributes = True
        populate_by_name = True
