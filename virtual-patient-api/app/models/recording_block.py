"""One immutable camera/microphone original per conversation exchange."""
from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base


class InterviewRecordingBlockDB(Base):
    __tablename__ = "interview_recording_blocks"
    id = Column(String(36), primary_key=True)
    recording_id = Column(String(36), ForeignKey("interview_recordings.id", ondelete="CASCADE"), nullable=False, index=True)
    capture_attempt_id = Column(String(36), ForeignKey("interview_recording_segments.id", ondelete="CASCADE"), nullable=False)
    order = Column(Integer, nullable=False)
    duration_ms = Column(BigInteger, nullable=True)
    storage_key = Column(String(500), nullable=False, unique=True)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    metadata_hash = Column(String(64), nullable=False)
    block_metadata = Column(JSON, nullable=False)
    encoded_timing = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        UniqueConstraint("capture_attempt_id", "order", name="uq_recording_block_order"),
        CheckConstraint('"order" >= 0 AND (duration_ms IS NULL OR duration_ms > 0) AND size_bytes > 0', name="ck_recording_block_extent"),
    )
