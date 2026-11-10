"""Private calibration captures retained as interview reference material."""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base


class CalibrationCaptureDB(Base):
    __tablename__ = "calibration_captures"
    __table_args__ = (UniqueConstraint("medical_interview_id", "fingerprint"),)

    id = Column(String(36), primary_key=True)
    medical_interview_id = Column(Integer, ForeignKey("medical_interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    fingerprint = Column(String(64), nullable=False)
    stage = Column(String(16), nullable=False)
    storage_key = Column(String, nullable=False)
    content_type = Column(String(32), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    duration_ms = Column(BigInteger, nullable=False)
    capture_metadata = Column(JSON, nullable=False)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    retention_expires_at = Column(DateTime(timezone=True), nullable=False)
    medical_interview = relationship("MedicalInterviewDB", back_populates="calibration_captures")
