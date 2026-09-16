"""Typed stage contracts for the multimodal pipeline (Requirement 3).

These are Pydantic v2 data contracts, not SQL tables (Requirement 3.4). They
are serialized into the existing ``interview_turns.paraverbal`` and
``interview_turns.nonverbal_features`` JSON columns, and into
``interview_metadata.calibration.personal_baseline`` for the personal baseline.

Design decisions preserved here:

* A single shared status/reason vocabulary captures every unavailable path so
  that a missing or low-quality value is representable without fabricating a
  number (Requirement 24.1, 24.3). Unavailable values carry a ``status`` and an
  optional ``reason`` and never a placeholder measurement.
* Fundamental-frequency values are expressed in semitones only, never in Hertz
  (Requirement 7.6, 15.6).
* The contracts are descriptive-only: they represent behavioural and contextual
  observations, not empathy, attention, warmth, or any psychological state.
* Paraverbal and nonverbal contracts are symmetric across the four stages: raw
  features, processed features, base labels, and integrated labels
  (Requirement 3.1, 3.2).
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class OutcomeStatus(str, Enum):
    """Outcome status for a family label or a modality layer (Requirement 24.1).

    ``OK`` marks an available outcome; the other members mark distinct
    unavailable paths that must never be represented as an unexplained null.
    """

    OK = "ok"
    UNAVAILABLE = "unavailable"
    INSUFFICIENT_REFERENCE_DATA = "insufficient_reference_data"


class UnavailableReason(str, Enum):
    """Explains why an outcome is unavailable (Requirement 24.1, 24.3).

    The members mirror the pipeline's error and quality taxonomy: an extractor
    failed, the captured signal was insufficient, the personal baseline was
    missing, the session reference distribution was insufficient, a required
    processed feature was unavailable, or a generic processing error occurred.
    """

    EXTRACTOR_FAILURE = "extractor_failure"
    INSUFFICIENT_SIGNAL = "insufficient_signal"
    MISSING_CALIBRATION = "missing_calibration"
    INSUFFICIENT_REFERENCE_DATA = "insufficient_reference_data"
    FEATURE_UNAVAILABLE = "feature_unavailable"
    PROCESSING_ERROR = "processing_error"


class PersonalBaseline(BaseModel):
    """Per-participant numeric reference derived from calibration media.

    Fundamental frequency is stored in semitones only, never in Hertz
    (Requirement 7.6, 15.6). Both gaze axes are required so every valid baseline
    supports participant-relative visual alignment.
    """

    baseline_f0_semitones: float
    baseline_loudness: float
    neutral_head_yaw: float
    neutral_head_pitch: float
    neutral_head_roll: float
    neutral_gaze_yaw: float
    neutral_gaze_pitch: float


# ---------------------------------------------------------------------------
# Paraverbal contracts
# ---------------------------------------------------------------------------


class ParaverbalRawFeatures(BaseModel):
    """Signal-level paraverbal outputs of extraction, before derivation.

    Produced by the OpenSMILE extractor. Contains only raw sample arrays,
    segmentation, per-signal metadata, and quality; it carries no labels.
    """

    word_count: int
    voiced_duration_ms: int
    f0_samples_semitones: list[float]
    loudness_samples: list[float]
    pause_segments_ms: list[float]
    turn_duration_ms: int
    extractor: dict
    audio_quality: dict


class ParaverbalProcessedFeatures(BaseModel):
    """Derived paraverbal metrics computed by preprocessing.

    Every field is optional so that a feature that could not be derived is
    represented as ``None`` rather than a fabricated number. ``relative_pitch_shift_st``
    requires a ``PersonalBaseline`` and is ``None`` when no baseline is available.
    Field names match the derivation formulas in the design.
    """

    speech_rate_wpm: float | None = None
    articulation_rate_wpm: float | None = None
    pause_count: int | None = None
    total_pause_duration_ms: float | None = None
    median_pause_duration_ms: float | None = None
    pause_frequency_per_min: float | None = None
    pause_time_ratio: float | None = None
    median_loudness: float | None = None
    f0_median_semitones: float | None = None
    f0_p20_p80_range_semitones: float | None = None
    loudness_p20_p80_range: float | None = None
    relative_pitch_shift_st: float | None = None


class FamilyLabel(BaseModel):
    """One interpretive outcome for a feature or a label family.

    A ``value`` is present only when ``status`` is ``OK``; otherwise ``value`` is
    ``None`` and ``reason`` explains the unavailability. This lets an unavailable
    outcome be represented without a fabricated value (Requirement 24.3).
    ``evidence`` records which base labels contributed to the outcome.
    """

    status: OutcomeStatus
    value: str | None = None
    reason: UnavailableReason | None = None
    evidence: dict = Field(default_factory=dict)


class ParaverbalBaseLabels(BaseModel):
    """Per-feature paraverbal base labels grouped by family.

    Each family maps feature names to their per-feature ``FamilyLabel`` as
    produced by the threshold engine.
    """

    temporal: dict[str, FamilyLabel]
    prosodic_level: dict[str, FamilyLabel]
    prosodic_modulation: dict[str, FamilyLabel]


class ParaverbalIntegratedLabels(BaseModel):
    """Exactly one integrated paraverbal label per family."""

    temporal: FamilyLabel
    prosodic_level: FamilyLabel
    prosodic_modulation: FamilyLabel


# ---------------------------------------------------------------------------
# Nonverbal contracts (symmetric to the paraverbal contracts, Requirement 3.2)
# Families: visual_orientation, head_gestural_feedback, facial_expressivity.
# ---------------------------------------------------------------------------


class NonverbalRawFeatures(BaseModel):
    """Signal-level nonverbal outputs of extraction, before derivation.

    Produced by the Py-Feat extractor. Contains per-frame raw arrays,
    segmentation, per-signal metadata, and frame-level quality; it carries no
    labels. Field names match the real Py-Feat 2.1.1 columns used downstream.
    """

    face_score_samples: list[float]
    gaze_yaw_samples: list[float]
    gaze_pitch_samples: list[float]
    au12_samples: list[float]
    head_pitch_samples: list[float]
    # Optional head yaw/roll raw series. These are used to derive the neutral
    # head pose (all three axes) for the personal baseline in calibration
    # (Requirement 15.1). They default to empty so existing turn extraction and
    # its consumers (tasks 3.1/3.2) keep working unchanged when the extractor
    # does not populate them.
    head_yaw_samples: list[float] = Field(default_factory=list)
    head_roll_samples: list[float] = Field(default_factory=list)
    frame_timestamps_ms: list[float]
    sample_fps: float
    turn_duration_ms: int
    extractor: dict
    video_quality: dict


class NonverbalProcessedFeatures(BaseModel):
    """Derived nonverbal metrics computed by preprocessing.

    Every field is optional so that a feature that could not be derived is
    represented as ``None`` rather than a fabricated number. Field names match
    the derivation formulas in the design. ``context`` records the interaction
    context (``speaking`` or ``listening``) for the turn.
    """

    visual_alignment_ratio: float | None = None
    median_visual_alignment_dwell_ms: float | None = None
    nod_count: int | None = None
    nod_rate_min: float | None = None
    context: Literal["speaking", "listening"] | None = None
    smile_activity_ratio: float | None = None
    mean_smile_activation: float | None = None


class NonverbalBaseLabels(BaseModel):
    """Per-feature nonverbal base labels grouped by family."""

    visual_orientation: dict[str, FamilyLabel]
    head_gestural_feedback: dict[str, FamilyLabel]
    facial_expressivity: dict[str, FamilyLabel]


class NonverbalIntegratedLabels(BaseModel):
    """Exactly one integrated nonverbal label per family."""

    visual_orientation: FamilyLabel
    head_gestural_feedback: FamilyLabel
    facial_expressivity: FamilyLabel


# ---------------------------------------------------------------------------
# Combined per-turn contracts
# ---------------------------------------------------------------------------


class IntegratedLabels(BaseModel):
    """Integrated labels across both modalities for a turn (Requirement 3.3)."""

    paraverbal: ParaverbalIntegratedLabels | None = None
    nonverbal: NonverbalIntegratedLabels | None = None


class ModalityLayer(BaseModel):
    """Layered result for one modality of one turn.

    Carries the four stage outputs (``raw``, ``processed``, ``base_labels``,
    ``integrated_labels``) plus ``quality`` and an overall ``status``/``reason``.
    Stage outputs are optional dicts so an unavailable stage is represented
    without fabricated content.
    """

    raw: dict | None = None
    processed: dict | None = None
    base_labels: dict | None = None
    integrated_labels: dict | None = None
    quality: dict = Field(default_factory=dict)
    status: OutcomeStatus
    reason: UnavailableReason | None = None


class MultimodalTurnResult(BaseModel):
    """Full multimodal result for a single turn (Requirement 3.3, 6.x, 16.x).

    Records both modality layers plus the methodology ``versions`` and the
    deterministic ``config_hash`` so every result is reproducible and traceable
    to the configuration that produced it. Paraverbal is ``None`` for patient
    turns; nonverbal is present for all turns.
    """

    turn_id: str
    modality_context: Literal["speaking", "listening"]
    paraverbal: ModalityLayer | None = None
    nonverbal: ModalityLayer | None = None
    versions: dict
    config_hash: str
