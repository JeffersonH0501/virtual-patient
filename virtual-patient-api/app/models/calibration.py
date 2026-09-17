"""Persistence and API contracts for reproducible calibration attempts."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class CalibrationStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    CAPTURE_VALIDATION = "capture_validation"
    GAZE_TARGETS = "gaze_targets"
    CAMERA_REFERENCE = "camera_reference"
    VOICE_BASELINE = "voice_baseline"
    PROCESSING = "processing"
    PASSED = "passed"
    FAILED = "failed"


class CalibrationAttemptDB(Base):
    __tablename__ = "calibration_attempts"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    medical_interview_id = Column(Integer, ForeignKey("medical_interviews.id", ondelete="CASCADE"), nullable=True)
    status = Column(String(32), nullable=False, default=CalibrationStatus.NOT_STARTED.value)
    failure_reason = Column(String(80), nullable=True)
    is_active = Column(Boolean, nullable=False, default=False)
    calibration_version = Column(String(80), nullable=False, default="multimodal_calibration_v1")
    calibration_metadata = Column("metadata", JSON, nullable=False, default=dict)
    profile = Column(JSON, nullable=True)
    quality = Column(JSON, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    media_assets = relationship("CalibrationMediaAssetDB", back_populates="attempt", cascade="all, delete-orphan")
    __table_args__ = (
        CheckConstraint("NOT is_active OR (status = 'passed' AND medical_interview_id IS NOT NULL)", name="ck_calibration_active_passed_linked"),
        Index("ix_calibration_attempt_user", "user_id"),
        Index("ix_calibration_attempt_interview", "medical_interview_id"),
        Index("uq_calibration_active_interview", "medical_interview_id", unique=True, postgresql_where=text("is_active"), sqlite_where=text("is_active = 1")),
    )


class CalibrationMediaAssetDB(Base):
    __tablename__ = "calibration_media_assets"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    calibration_attempt_id = Column(String(36), ForeignKey("calibration_attempts.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(30), nullable=False)
    storage_key = Column(String(500), nullable=False, unique=True)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    duration_ms = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    asset_metadata = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    attempt = relationship("CalibrationAttemptDB", back_populates="media_assets")
    __table_args__ = (
        UniqueConstraint("calibration_attempt_id", "kind", name="uq_calibration_media_kind"),
        Index("ix_calibration_media_attempt", "calibration_attempt_id"),
    )


class CalibrationTarget(BaseModel):
    target_id: str
    target_order: int = Field(ge=1, le=9)
    target_normalized_x: float = Field(ge=0, le=1)
    target_normalized_y: float = Field(ge=0, le=1)
    target_pixel_x: float = Field(ge=0)
    target_pixel_y: float = Field(ge=0)
    presentation_start_ms: int = Field(ge=0)
    presentation_end_ms: int = Field(gt=0)
    observation_window_start_ms: int = Field(ge=0)
    observation_window_end_ms: int = Field(gt=0)


class CalibrationGeometry(BaseModel):
    viewport_width: int = Field(gt=0)
    viewport_height: int = Field(gt=0)
    device_pixel_ratio: float = Field(gt=0)
    screen_width: int | None = Field(default=None, gt=0)
    screen_height: int | None = Field(default=None, gt=0)
    orientation: Literal["portrait", "landscape"]
    video_width: int = Field(gt=0)
    video_height: int = Field(gt=0)


class CalibrationCaptureMetadata(BaseModel):
    geometry: CalibrationGeometry
    targets: list[CalibrationTarget]
    camera_reference_start_ms: int = Field(ge=0)
    camera_reference_end_ms: int = Field(gt=0)
    voice_baseline_start_ms: int = Field(ge=0)
    voice_baseline_end_ms: int = Field(gt=0)
    geometry_stable: bool

    @model_validator(mode="after")
    def validate_protocol(self):
        if len(self.targets) != 9 or {target.target_order for target in self.targets} != set(range(1, 10)):
            raise ValueError("Calibration requires exactly nine ordered targets")
        expected = ["CENTER", "TOP_LEFT", "BOTTOM_RIGHT", "TOP_RIGHT", "BOTTOM_LEFT", "TOP_CENTER", "BOTTOM_CENTER", "MIDDLE_LEFT", "MIDDLE_RIGHT"]
        ordered = sorted(self.targets, key=lambda item: item.target_order)
        if [target.target_id for target in ordered] != expected:
            raise ValueError("Calibration target order does not match the versioned protocol")
        if any(target.observation_window_start_ms < target.presentation_start_ms or target.observation_window_end_ms > target.presentation_end_ms or target.observation_window_end_ms <= target.observation_window_start_ms for target in ordered):
            raise ValueError("Calibration target observation windows must be inside presentation windows")
        if self.camera_reference_end_ms <= self.camera_reference_start_ms or self.voice_baseline_end_ms <= self.voice_baseline_start_ms:
            raise ValueError("Calibration intervals must be positive")
        if self.camera_reference_start_ms < ordered[-1].presentation_end_ms or self.voice_baseline_start_ms < self.camera_reference_end_ms:
            raise ValueError("Calibration stages must be ordered and non-overlapping")
        return self
