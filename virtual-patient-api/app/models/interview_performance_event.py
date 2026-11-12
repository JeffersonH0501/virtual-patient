from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.sql import func

from app.core.database import Base


class InterviewPerformanceEventDB(Base):
    __tablename__ = "interview_performance_events"
    __table_args__ = (Index("ix_interview_performance_events_timeline", "medical_interview_id", "created_at", "id"),)

    id = Column(Integer, primary_key=True)
    medical_interview_id = Column(Integer, ForeignKey("medical_interviews.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    component = Column(String(80), nullable=False)
    operation = Column(String(100), nullable=False)
    phase = Column(String(40), nullable=False)
    status = Column(String(40), nullable=False)
    duration_ms = Column(Float, nullable=True)
    trace_id = Column(String(100), nullable=True)
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)
