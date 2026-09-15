"""Pydantic v2 response models for the dev/debug calibration tool.

These models describe a single raw frame observation for display in the
calibration debug UI. They intentionally follow an availability-aware pattern:
every value that may be missing is ``Optional`` and defaults to ``None`` (never
``0``), and a parallel ``reasons`` map explains why any given field is null.
This keeps "evidence not available" clearly distinct from "value is zero", in
line with the project decision to treat absent or low-quality evidence as
information not available rather than negative performance.

No processed features, base/integrated labels, or turn aggregates are modeled
here. Only raw, frame-level values plus lightweight metadata.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractorInfo(BaseModel):
    """Identifying metadata for the extractor that produced a frame."""

    name: str
    version: str
    detector: str | None = None


class PyFeatFrameDebug(BaseModel):
    """Raw, single-image Py-Feat observation for one debug frame.

    Numeric fields are the raw values read from the best-``FaceScore`` detection
    row. They are not thresholded, aligned, or aggregated. Landmarks are raw
    image-pixel coordinates as returned by the detector.
    """

    face_detected: bool = False
    face_score: float | None = None
    gaze_yaw: float | None = None
    gaze_pitch: float | None = None
    head_yaw: float | None = None
    head_pitch: float | None = None
    head_roll: float | None = None
    au12: float | None = None
    # Raw 68-point (or detector-native) landmarks as [x, y] image-pixel pairs.
    landmarks: list[list[float]] | None = None
    image_width: int | None = None
    image_height: int | None = None
    # Echo of the client-provided capture timestamp, if any.
    frame_timestamp_ms: float | None = None
    # Server-side processing latency for this single frame.
    processing_ms: float = 0.0
    extractor: ExtractorInfo
    # Field-name -> short machine-readable reason for any null value.
    reasons: dict[str, str] = Field(default_factory=dict)


class OpenSmileFeatureNames(BaseModel):
    """Real OpenSMILE LLD column names backing each displayed value.

    Surfacing the true column names keeps the debug readout honest: the UI shows
    which raw signal a number came from, and ``voicing`` documents whichever
    voicing-related signal was actually available (or ``None`` with a reason).
    """

    f0: str | None = None
    loudness: str | None = None
    voicing: str | None = None


class OpenSmileFrameDebug(BaseModel):
    """Raw, representative frame-level OpenSMILE values for one audio chunk.

    Each value is a single displayable number taken from the per-frame LLD
    dataframe (a recent finite frame value), NOT a turn-level aggregate feature.
    It exists purely for live display in the calibration tool.
    """

    f0_semitones: float | None = None
    loudness: float | None = None
    voicing: float | None = None
    voicing_kind: str | None = None
    feature_names: OpenSmileFeatureNames = Field(default_factory=OpenSmileFeatureNames)
    feature_set: str = "eGeMAPSv02"
    frame_timestamp_ms: float | None = None
    processing_ms: float = 0.0
    reasons: dict[str, str] = Field(default_factory=dict)


class DebugUnavailable(BaseModel):
    """Returned (with HTTP 503) when a debug extractor cannot run at all."""

    available: bool = False
    reason: str
