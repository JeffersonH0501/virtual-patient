"""One participant-owned perception survey independent of interviews."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func
from app.core.database import Base


class PerceptionSurveyDB(Base):
    __tablename__ = "perception_surveys"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    status = Column(String(16), nullable=False, default="DRAFT")
    answers = Column(JSON, nullable=False, default=dict)
    comments = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    submitted_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
