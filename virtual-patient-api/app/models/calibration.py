"""Browser capture metadata contracts; retained media lives in CalibrationCaptureDB."""

from __future__ import annotations

from typing import Literal
from math import isfinite, isclose

from pydantic import BaseModel, Field, model_validator


GAZE_TARGETS = (
    ("CENTER", .5, .5), ("TOP_LEFT", .1, .1), ("BOTTOM_RIGHT", .9, .9),
    ("TOP_RIGHT", .9, .1), ("BOTTOM_LEFT", .1, .9), ("TOP_CENTER", .5, .1),
    ("BOTTOM_CENTER", .5, .9), ("MIDDLE_LEFT", .1, .5), ("MIDDLE_RIGHT", .9, .5),
)
MEDIAPIPE_GAZE_SOURCE = "mediapipe_five_point_v1"


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



class GazeCalibrationMetadata(BaseModel):
    experimental_quality_bypass: bool = False
    gaze_source: Literal["mediapipe_five_point_v1"]
    geometry: CalibrationGeometry
    targets: list[CalibrationTarget]
    geometry_stable: bool

    @model_validator(mode="after")
    def validate_protocol(self):
        protocol_targets = GAZE_TARGETS[:5]
        if len(self.targets) != len(protocol_targets) or {target.target_order for target in self.targets} != set(range(1, len(protocol_targets)+1)):
            raise ValueError("Gaze calibration targets must match the selected source protocol")
        expected = [name for name, _, _ in protocol_targets]
        ordered = sorted(self.targets, key=lambda item: item.target_order)
        if [target.target_id for target in ordered] != expected:
            raise ValueError("Gaze calibration target order does not match the versioned protocol")
        for target, (_, x, y) in zip(ordered, protocol_targets):
            if (not isclose(target.target_normalized_x, x, abs_tol=1e-9)
                    or not isclose(target.target_normalized_y, y, abs_tol=1e-9)
                    or not isfinite(target.target_pixel_x) or not isfinite(target.target_pixel_y)
                    or not isclose(target.target_pixel_x, x * self.geometry.viewport_width, abs_tol=1)
                    or not isclose(target.target_pixel_y, y * self.geometry.viewport_height, abs_tol=1)):
                raise ValueError("Calibration target coordinates do not match the protocol and viewport")
        if any(target.observation_window_start_ms < target.presentation_start_ms or target.observation_window_end_ms > target.presentation_end_ms or target.observation_window_end_ms <= target.observation_window_start_ms for target in ordered):
            raise ValueError("Gaze observation windows must be inside presentation windows")
        if any(current.presentation_start_ms < previous.presentation_end_ms for previous, current in zip(ordered, ordered[1:])):
            raise ValueError("Gaze targets must have ordered non-overlapping intervals")
        return self


class CameraCalibrationMetadata(BaseModel):
    experimental_quality_bypass: bool = False
    geometry: CalibrationGeometry
    geometry_stable: bool
    affine_matrix: list[list[float]]
    gaze_source: Literal["mediapipe_five_point_v1"] = MEDIAPIPE_GAZE_SOURCE

    @model_validator(mode="after")
    def validate_matrix(self):
        if len(self.affine_matrix) != 2 or any(len(row) != 3 for row in self.affine_matrix):
            raise ValueError("Camera calibration requires a 2x3 affine gaze matrix")
        if not all(isfinite(value) for row in self.affine_matrix for value in row):
            raise ValueError("Camera calibration matrix must be finite")
        return self



GUIDED_CHECK_KINDS_V1 = ("gaze_still", "gaze_turn", "gaze_nod", "gaze_away",
                     "smile_neutral", "smile_speech", "smile_silent", "smile_speech_positive")
GUIDED_CHECK_KINDS = (*GUIDED_CHECK_KINDS_V1[:4], "gaze_camera", "nod_still", "nod_three", "head_shake", *GUIDED_CHECK_KINDS_V1[4:])
NONVERBAL_CHECK_KINDS = GUIDED_CHECK_KINDS[5:]


class LiveGazeMetadata(BaseModel):
    profile: dict


class GuidedCheckEnvironment(BaseModel):
    device_type: Literal["unspecified", "laptop", "tablet", "other"] = "unspecified"
    camera_position: Literal["unknown", "top", "bottom", "left", "right", "external"] = "unknown"


class GuidedCheckInterval(BaseModel):
    kind: Literal["gaze_still", "gaze_turn", "gaze_nod", "gaze_away", "gaze_camera", "nod_still", "nod_three", "head_shake",
                  "smile_neutral", "smile_speech", "smile_silent", "smile_speech_positive"]
    start_ms: int = Field(ge=0)
    observation_start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_interval(self):
        if not self.start_ms <= self.observation_start_ms < self.end_ms or not 1000 <= self.end_ms - self.observation_start_ms <= 15000:
            raise ValueError("Guided check must contain 1 to 15 seconds of observations")
        return self


class GuidedOnlyMetadata(BaseModel):
    geometry: CalibrationGeometry
    geometry_stable: bool
    guided_checks: list[GuidedCheckInterval]
    guided_environment: GuidedCheckEnvironment
    attestations: dict[str, str]
    profile: dict = Field(default_factory=dict)
    camera_result: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_checks(self):
        if not self.geometry_stable or self.guided_environment.device_type != "laptop" or self.guided_environment.camera_position != "top":
            raise ValueError("Guided checks require stable supported geometry")
        if tuple(item.kind for item in self.guided_checks) not in (GUIDED_CHECK_KINDS, NONVERBAL_CHECK_KINDS):
            raise ValueError("Guided checks require the complete protocol")
        if any(current.start_ms < previous.end_ms for previous, current in zip(self.guided_checks, self.guided_checks[1:])):
            raise ValueError("Guided checks cannot overlap")
        return self


class UnifiedCalibrationMetadata(GazeCalibrationMetadata):
    guided_protocol: Literal["guided_checks_v4_orientation"] = "guided_checks_v4_orientation"
    camera_reference_start_ms: int = Field(ge=0)
    camera_reference_end_ms: int = Field(gt=0)
    guided_checks: list[GuidedCheckInterval] = Field(default_factory=list, max_length=12)
    guided_environment: GuidedCheckEnvironment = Field(default_factory=GuidedCheckEnvironment)

    @model_validator(mode="after")
    def validate_camera_interval(self):
        if (self.camera_reference_start_ms < max(target.presentation_end_ms for target in self.targets)
                or self.camera_reference_end_ms <= self.camera_reference_start_ms):
            raise ValueError("Camera reference must follow the gaze targets")
        if self.guided_checks:
            if self.guided_protocol == "guided_checks_v4_orientation" and tuple(item.kind for item in self.guided_checks) != GUIDED_CHECK_KINDS:
                raise ValueError("Orientation comparison requires the complete twelve-step protocol")
            if self.guided_environment.device_type != "laptop" or self.guided_environment.camera_position != "top":
                raise ValueError("Guided calibration requires a laptop with a top-center camera")
            if tuple(item.kind for item in self.guided_checks) not in (GUIDED_CHECK_KINDS, GUIDED_CHECK_KINDS_V1):
                raise ValueError("Guided checks must follow the complete versioned protocol")
            previous_end = self.camera_reference_end_ms
            for item in self.guided_checks:
                if item.start_ms < previous_end:
                    raise ValueError("Guided checks must follow the camera reference without overlap")
                previous_end = item.end_ms
        return self
