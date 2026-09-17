"""Smile observations derived from MediaPipe face blendshapes."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean

from app.nonverbal.shared_observations import SharedFrameObservation


SMILE_THRESHOLD = 0.395


@dataclass(frozen=True)
class SmileObservation:
    timestamp_ms: float
    mouth_smile_left: float
    mouth_smile_right: float
    smile_activation: float
    smile_detected: bool


def extract_smile(observation: SharedFrameObservation) -> SmileObservation | None:
    if not observation.face_valid or not observation.blendshapes:
        return None
    left = observation.blendshapes.get("mouthSmileLeft")
    right = observation.blendshapes.get("mouthSmileRight")
    if left is None or right is None:
        return None
    activation = (left + right) / 2.0
    return SmileObservation(
        timestamp_ms=observation.timestamp_ms,
        mouth_smile_left=left,
        mouth_smile_right=right,
        smile_activation=activation,
        smile_detected=left >= SMILE_THRESHOLD or right >= SMILE_THRESHOLD,
    )


def aggregate_smile(observations: list[SmileObservation]) -> tuple[float | None, float | None]:
    if not observations:
        return None, None
    return (
        sum(item.smile_detected for item in observations) / len(observations),
        fmean(item.smile_activation for item in observations),
    )

