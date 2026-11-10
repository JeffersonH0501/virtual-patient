"""Timestamped ocular observation shared by visual processing."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GazeObservation:
    timestamp_ms: float
    valid: bool
    state: str
    unclipped_x: float | None = None
    unclipped_y: float | None = None
    display_x: float | None = None
    display_y: float | None = None
