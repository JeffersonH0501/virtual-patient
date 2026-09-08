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
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
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
    consent_basis = Column(String(30), nullable=False, default="institutional")
    consent_policy_version = Column(String(80), nullable=False)
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

    __table_args__ = (
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_recording_duration"),
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
    storage_key = Column(String(500), nullable=False, unique=True)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    duration_ms = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="ready")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    recording = relationship("InterviewRecordingDB", back_populates="assets")

    __table_args__ = (
        UniqueConstraint("recording_id", "kind", name="uq_recording_media_kind"),
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
    sequence = Column(Integer, nullable=False)
    start_ms = Column(BigInteger, nullable=False)
    end_ms = Column(BigInteger, nullable=False)
    transcript = Column(Text, nullable=False)
    input_source = Column(String(40), nullable=False)
    timing_source = Column(String(40), nullable=False)
    timing_quality = Column(String(30), nullable=False)
    paraverbal = Column(JSON, nullable=True)
    nonverbal_features = Column(JSON, nullable=True)
    pyfeat_nonverbal_features = Column(JSON, nullable=True)
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


class RecordingStartRequest(BaseModel):
    started_at: datetime
    capture_config: Dict[str, Any] = Field(default_factory=dict)


class RecordingUnavailableRequest(BaseModel):
    failure_code: str = Field(min_length=1, max_length=80)
    duration_ms: Optional[int] = Field(default=None, ge=0)


class TurnUpsertRequest(BaseModel):
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
    pyfeat_nonverbal_features: Optional[Dict[str, Any]] = None


class InterviewRecapResponse(BaseModel):
    interview_id: int
    recording_status: RecordingStatus
    duration_ms: Optional[int] = None
    observation_processing: Dict[str, Any] = Field(default_factory=dict)
    student_audio_source: Optional[str] = None
    student_video_source: Optional[str] = None
    patient_audio_source: Optional[str] = None
    patient_video_source: Optional[str] = None
    turns: List[RecapTurn] = Field(default_factory=list)
