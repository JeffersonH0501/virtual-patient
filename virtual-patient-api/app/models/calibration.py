"""Calibration capture contracts.

The multimodal calibration is processed temporarily and never persisted as its
own database rows (see ``app/routers/calibration.py``). Only the browser capture
metadata contracts live here; there is no ``CalibrationAttemptDB`` /
``CalibrationMediaAssetDB`` lifecycle. The passed calibration result is stored
inside ``interview_metadata.calibration`` when the interview starts.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
