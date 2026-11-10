"""Teacher assignments and author-editable completed ratings."""
from sqlalchemy import Column, Integer, ForeignKey, DateTime, JSON, Float, String, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base


class TeacherAssignmentDB(Base):
    __tablename__ = "teacher_assignments"
    id = Column(Integer, primary_key=True)
    interview_id = Column(Integer, ForeignKey("medical_interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("interview_id", "teacher_id", name="uq_teacher_assignment"),)


class TeacherRatingDB(Base):
    __tablename__ = "teacher_ratings"
    id = Column(Integer, primary_key=True)
    assignment_id = Column(Integer, ForeignKey("teacher_assignments.id", ondelete="CASCADE"), nullable=False, unique=True)
    rubric_version = Column(String(80), nullable=False)
    rubric_snapshot = Column(JSON, nullable=False)
    results = Column(JSON, nullable=False, default=list)
    overall_score = Column(Float)
    submitted_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
