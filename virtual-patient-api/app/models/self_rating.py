"""Owner-authored self-assessments, independent of assigned teacher ratings."""
from sqlalchemy import Column, Integer, ForeignKey, DateTime, JSON, Float, String
from sqlalchemy.sql import func
from app.core.database import Base


class SelfRatingDB(Base):
    __tablename__ = "self_ratings"
    interview_id = Column(Integer, ForeignKey("medical_interviews.id", ondelete="CASCADE"), primary_key=True)
    rubric_version = Column(String(80), nullable=False)
    rubric_snapshot = Column(JSON, nullable=False)
    results = Column(JSON, nullable=False, default=list)
    overall_score = Column(Float)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    submitted_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
