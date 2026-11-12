"""One immutable camera/microphone original per student turn.

Replaces the former per-exchange block model: each student turn owns its own
durable media file instead of referencing a window inside a shared block. The
patient turn is text-to-speech and keeps its served audio, so it has no captured
media row here.
"""
from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base


class InterviewTurnMediaDB(Base):
    __tablename__ = "interview_turn_media"

    id = Column(String(36), primary_key=True)
    recording_id = Column(
        String(36), ForeignKey("interview_recordings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    capture_attempt_id = Column(
        String(36), ForeignKey("interview_recording_segments.id", ondelete="CASCADE"), nullable=False
    )
    # The conversation message this turn media captures. Nullable only transiently
    # while a turn is being reconciled; the finalize manifest requires coverage.
    message_id = Column(Integer, ForeignKey("interview_messages.id", ondelete="SET NULL"), nullable=True, index=True)
    speaker = Column(String(20), nullable=False)
    order = Column(Integer, nullable=False)
    # Start of this turn on the common session clock, so global ordering never
    # depends on summing per-exchange durations.
    session_clock_ms = Column(BigInteger, nullable=False)
    duration_ms = Column(BigInteger, nullable=True)
    storage_key = Column(String(500), nullable=False, unique=True)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    metadata_hash = Column(String(64), nullable=False)
    turn_metadata = Column(JSON, nullable=False)
    encoded_timing = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("capture_attempt_id", "order", name="uq_turn_media_order"),
        UniqueConstraint("recording_id", "message_id", name="uq_turn_media_message"),
        CheckConstraint(
            '"order" >= 0 AND session_clock_ms >= 0 AND '
            "(duration_ms IS NULL OR duration_ms > 0) AND size_bytes > 0",
            name="ck_turn_media_extent",
        ),
    )
