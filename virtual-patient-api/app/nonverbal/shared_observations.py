"""Versioned frame observations shared by every server-side visual branch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SharedFrameObservation:
    timestamp_ms: float
    frame: Any
    face_valid: bool
    landmarks: Any | None = None
    blendshapes: dict[str, float] | None = None
    facial_transformation_matrix: Any | None = None
    reason: str | None = None
    frame_width: int | None = None
    frame_height: int | None = None
