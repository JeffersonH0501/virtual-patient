"""Receipts are committed in the same transaction as capture metadata."""
from sqlalchemy import Column, ForeignKey, Integer, JSON, String, UniqueConstraint
from app.core.database import Base


class CaptureOperationDB(Base):
    __tablename__ = "capture_operations"
    id = Column(Integer, primary_key=True)
    interview_id = Column(Integer, ForeignKey("medical_interviews.id", ondelete="CASCADE"), nullable=False)
    operation_id = Column(String(36), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    result = Column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint("interview_id", "operation_id", name="uq_capture_operation"),)
