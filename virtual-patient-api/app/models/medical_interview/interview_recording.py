"""Persistence and API schemas for synchronized interview recordings."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class RecordingStatus(str, enum.Enum):
    RECORDING = "recording"
    PAUSED = "paused"
    FINALIZING = "finalizing"
    READY = "ready"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class TurnVideoAnalysisStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MediaAssetKind(str, enum.Enum):
    STUDENT_AUDIO = "student_audio"
    STUDENT_VIDEO = "student_video"
    PATIENT_AUDIO = "patient_audio"
    PATIENT_VIDEO = "patient_video"


class InterviewRecordingDB(Base):
    __tablename__ = "interview_recordings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    medical_interview_id = Column(
        Integer,
        ForeignKey("medical_interviews.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status = Column(String(20), nullable=False, default=RecordingStatus.RECORDING.value)
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(BigInteger, nullable=True)
    capture_config = Column(JSON, nullable=False, default=dict)
    consent_basis = Column(String(30), nullable=False, default="managed-externally")
    consent_policy_version = Column(String(80), nullable=False, default="not-recorded")
    retention_expires_at = Column(DateTime(timezone=True), nullable=True)
    failure_code = Column(String(80), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    medical_interview = relationship("MedicalInterviewDB", back_populates="recording")
    assets = relationship(
        "InterviewMediaAssetDB",
        back_populates="recording",
        cascade="all, delete-orphan",
    )
    segments = relationship(
        "InterviewRecordingSegmentDB", cascade="all, delete-orphan",
        order_by="InterviewRecordingSegmentDB.sequence",
    )

    __table_args__ = (
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_recording_duration"),
    )


class InterviewRecordingSegmentDB(Base):
    __tablename__ = "interview_recording_segments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recording_id = Column(
        String(36), ForeignKey("interview_recordings.id", ondelete="CASCADE"), nullable=False,
    )
    sequence = Column(Integer, nullable=False)
    offset_ms = Column(BigInteger, nullable=False)
    duration_ms = Column(BigInteger, nullable=True)
    capture_config = Column(JSON, nullable=False, default=dict)
    calibration = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sealed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("recording_id", "sequence", name="uq_recording_segment_sequence"),
        Index("uq_recording_active_segment", "recording_id", unique=True,
              postgresql_where=text("sealed_at IS NULL"), sqlite_where=text("sealed_at IS NULL")),
        CheckConstraint("sequence >= 0 AND offset_ms >= 0", name="ck_recording_segment_position"),
        CheckConstraint("(duration_ms IS NULL AND sealed_at IS NULL) OR "
                        "(duration_ms >= 0 AND duration_ms IS NOT NULL AND sealed_at IS NOT NULL)",
                        name="ck_recording_segment_seal"),
    )


class InterviewMediaAssetDB(Base):
    __tablename__ = "interview_media_assets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recording_id = Column(
        String(36),
        ForeignKey("interview_recordings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind = Column(String(30), nullable=False)
    segment_id = Column(String(36), ForeignKey("interview_recording_segments.id", ondelete="CASCADE"), nullable=True)
    storage_key = Column(String(500), nullable=False, unique=True)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    duration_ms = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="ready")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    recording = relationship("InterviewRecordingDB", back_populates="assets")

    __table_args__ = (
        Index("uq_recording_legacy_media_kind", "recording_id", "kind", unique=True,
              postgresql_where=text("segment_id IS NULL"), sqlite_where=text("segment_id IS NULL")),
        Index("uq_recording_segment_media_kind", "segment_id", "kind", unique=True,
              postgresql_where=text("segment_id IS NOT NULL"), sqlite_where=text("segment_id IS NOT NULL")),
        CheckConstraint("size_bytes >= 0", name="ck_media_asset_size"),
        CheckConstraint("duration_ms >= 0", name="ck_media_asset_duration"),
    )


class InterviewTurnDB(Base):
    __tablename__ = "interview_turns"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    medical_interview_id = Column(
        Integer,
        ForeignKey("medical_interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id = Column(
        Integer,
        ForeignKey("interview_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    speaker = Column(String(20), nullable=False)
    segment_id = Column(String(36), ForeignKey("interview_recording_segments.id", ondelete="CASCADE"),
                        nullable=True, index=True)
    sequence = Column(Integer, nullable=False)
    start_ms = Column(BigInteger, nullable=False)
    end_ms = Column(BigInteger, nullable=False)
    transcript = Column(Text, nullable=False)
    input_source = Column(String(40), nullable=False)
    timing_source = Column(String(40), nullable=False)
    timing_quality = Column(String(30), nullable=False)
    paraverbal = Column(JSON, nullable=True)
    nonverbal_features = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    medical_interview = relationship("MedicalInterviewDB", back_populates="turns")

    __table_args__ = (
        UniqueConstraint(
            "medical_interview_id",
            "message_id",
            name="uq_interview_turn_message",
        ),
        UniqueConstraint(
            "medical_interview_id",
            "sequence",
            name="uq_interview_turn_sequence",
        ),
        CheckConstraint("start_ms >= 0", name="ck_interview_turn_start"),
        CheckConstraint("end_ms >= start_ms", name="ck_interview_turn_end"),
    )


class TurnVideoAnalysisDB(Base):
    """Durable lifecycle for one temporary nonverbal turn segment."""

    __tablename__ = "turn_video_analyses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    medical_interview_id = Column(
        Integer, ForeignKey("medical_interviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recording_id = Column(
        String(36), ForeignKey("interview_recordings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn_id = Column(
        String(36), ForeignKey("interview_turns.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    speaker = Column(String(20), nullable=False)
    start_ms = Column(BigInteger, nullable=False)
    end_ms = Column(BigInteger, nullable=False)
    storage_key = Column(String(500), nullable=True, unique=True)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default=TurnVideoAnalysisStatus.QUEUED.value,
        index=True,
    )
    result = Column(JSON, nullable=True)
    roi_snapshots = Column(JSON, nullable=False, default=list)
    error = Column(Text, nullable=True)
    queued_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("recording_id", "turn_id", name="uq_turn_video_analysis_recording_turn"),
        CheckConstraint("end_ms >= start_ms", name="ck_turn_video_analysis_window"),
        CheckConstraint("size_bytes >= 0", name="ck_turn_video_analysis_size"),
    )


class RecordingStartRequest(BaseModel):
    started_at: datetime
    capture_config: Dict[str, Any] = Field(default_factory=dict)


class RecordingUnavailableRequest(BaseModel):
    failure_code: str = Field(min_length=1, max_length=80)
    duration_ms: Optional[int] = Field(default=None, ge=0)


class TurnUpsertRequest(BaseModel):
    patient_roi_snapshots: Optional[list[dict]] = None
    segment_id: Optional[str] = Field(default=None, min_length=36, max_length=36)
    speaker: Literal["student", "patient"]
    sequence: int = Field(ge=0)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    transcript: str = Field(min_length=1)
    input_source: str = Field(min_length=1, max_length=40)
    timing_source: str = Field(min_length=1, max_length=40)
    timing_quality: Literal["measured", "provisional", "estimated"]


class RecordingStateResponse(BaseModel):
    interview_id: int
    recording_id: str
    recording_status: RecordingStatus
    duration_ms: Optional[int] = None


class RecapTurn(BaseModel):
    turn_id: str
    message_id: Optional[int] = None
    speaker: Literal["student", "patient"]
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    transcript: str
    input_source: str
    timing_source: str
    timing_quality: str
    paraverbal: Optional[Dict[str, Any]] = None
    nonverbal_features: Optional[Dict[str, Any]] = None


class InterviewRecapResponse(BaseModel):
    interview_id: int
    recording_status: RecordingStatus
    duration_ms: Optional[int] = None
    observation_processing: Dict[str, Any] = Field(default_factory=dict)
    evaluation_processing: Dict[str, Any] = Field(default_factory=dict)
    blocks: Optional[List[Dict[str, Any]]] = None
    turns: List[RecapTurn] = Field(default_factory=list)
