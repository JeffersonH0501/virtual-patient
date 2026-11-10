"""Durable interview work in the existing API runtime."""
import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, text
from sqlalchemy.sql import func
from app.core.database import Base


class InterviewProcessingJobDB(Base):
    __tablename__ = "interview_processing_jobs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    medical_interview_id = Column(Integer, ForeignKey("medical_interviews.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(32), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="queued")
    attempts = Column(Integer, nullable=False, default=0)
    error_code = Column(String(80), nullable=True)
    queued_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index("uq_active_interview_processing_job", "medical_interview_id", "kind", unique=True,
        postgresql_where=text("status IN ('queued', 'processing')"),
        sqlite_where=text("status IN ('queued', 'processing')")),)
