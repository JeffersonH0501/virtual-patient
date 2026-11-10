"""Shared reference, threshold/label assembly and persisted turn-result policy."""
from __future__ import annotations
from math import isfinite
from typing import Any, Sequence
from app.models.medical_interview import InterviewTurnDB
from app.multimodal.config_loader import MethodologyConfig
from app.multimodal.label_engine import integrate_nonverbal_labels, integrate_paraverbal_labels
from app.multimodal.threshold_engine import compute_nonverbal_base_labels, compute_paraverbal_base_labels
from app.multimodal.schemas import (
    ModalityLayer, MultimodalTurnResult, NonverbalProcessedFeatures, NonverbalRawFeatures,
    OutcomeStatus, ParaverbalProcessedFeatures, ParaverbalRawFeatures, UnavailableReason,
)

STATUS_COMPLETE = "complete"


STATUS_PARTIAL = "partial"


STATUS_UNAVAILABLE = "unavailable"


_PARAVERBAL_SESSION_FEATURES = ("median_loudness", "loudness_p20_p80_range")


_NONVERBAL_SESSION_FEATURES = ()


_SESSION_PERCENTILES = {"p25": 0.25, "p75": 0.75}


_STUDENT_SPEAKER = "student"


_CONTEXT_SPEAKING = "speaking"


_CONTEXT_LISTENING = "listening"


def _assemble_turn_result(
    *,
    turn: InterviewTurnDB,
    config: MethodologyConfig,
    versions: dict,
    config_hash: str,
    baseline_available: bool,
    paraverbal_raw: ParaverbalRawFeatures | None,
    paraverbal_processed: ParaverbalProcessedFeatures | None,
    para_session_refs: dict[str, dict[str, float]] | None,
    nonverbal_raw: NonverbalRawFeatures | None,
    nonverbal_processed: NonverbalProcessedFeatures | None,
    nonverbal_reasons: dict[str, UnavailableReason],
    nonverbal_session_refs: dict[str, dict[str, float]] | None,
    outcome: "_OutcomeTracker",
) -> MultimodalTurnResult:
    """Run the threshold + label engines and build one turn's layered result.

    Paraverbal is only computed for student turns; for patient turns the
    paraverbal layer is ``None`` and is never fabricated (Requirement 17.3). The
    nonverbal layer is always attempted (Requirement 17.2).
    """
    context = _context_for(turn)
    is_student = turn.speaker == _STUDENT_SPEAKER

    paraverbal_layer: ModalityLayer | None = None
    if is_student:
        paraverbal_layer = _paraverbal_layer(
            config=config,
            baseline_available=baseline_available,
            raw=paraverbal_raw,
            processed=paraverbal_processed,
            session_refs=para_session_refs,
            outcome=outcome,
        )

    nonverbal_layer = _nonverbal_layer(
        config=config,
        baseline_available=baseline_available,
        raw=nonverbal_raw,
        processed=nonverbal_processed,
        reasons=nonverbal_reasons,
        session_refs=nonverbal_session_refs,
        outcome=outcome,
    )

    return MultimodalTurnResult(
        turn_id=turn.id,
        modality_context=context,
        paraverbal=paraverbal_layer,
        nonverbal=nonverbal_layer,
        versions=versions,
        config_hash=config_hash,
    )


def _paraverbal_layer(
    *,
    config: MethodologyConfig,
    baseline_available: bool,
    raw: ParaverbalRawFeatures | None,
    processed: ParaverbalProcessedFeatures | None,
    session_refs: dict[str, dict[str, float]] | None,
    outcome: "_OutcomeTracker",
) -> ModalityLayer:
    """Build the paraverbal :class:`ModalityLayer` for one student turn."""
    if raw is None or processed is None:
        outcome.note_gap()
        return ModalityLayer(
            status=OutcomeStatus.UNAVAILABLE,
            reason=UnavailableReason.INSUFFICIENT_SIGNAL,
        )

    base_labels = compute_paraverbal_base_labels(
        processed,
        config,
        baseline_available=baseline_available,
        session_refs=session_refs,
    )
    integrated = integrate_paraverbal_labels(base_labels, config)
    from app.multimodal.quality_policy import family_evidence_available, QUALITY_POLICY_VERSION
    from app.multimodal.schemas import FamilyLabel
    signal = {"raw": raw.model_dump(), "quality": raw.audio_quality}
    for family in type(integrated).model_fields:
        if not family_evidence_available(signal, family):
            setattr(integrated, family, FamilyLabel(status=OutcomeStatus.UNAVAILABLE,
                    reason=UnavailableReason.INSUFFICIENT_SIGNAL))
            outcome.note_gap()
    outcome.note_ok()
    return ModalityLayer(
        raw=raw.model_dump(),
        processed=processed.model_dump(),
        base_labels=base_labels.model_dump(),
        integrated_labels=integrated.model_dump(),
        quality={**raw.audio_quality, "eligibility_policy_version": QUALITY_POLICY_VERSION},
        status=OutcomeStatus.OK,
    )


def _nonverbal_layer(
    *,
    config: MethodologyConfig,
    baseline_available: bool,
    raw: NonverbalRawFeatures | None,
    processed: NonverbalProcessedFeatures | None,
    reasons: dict[str, UnavailableReason],
    session_refs: dict[str, dict[str, float]] | None,
    outcome: "_OutcomeTracker",
) -> ModalityLayer:
    """Build the nonverbal :class:`ModalityLayer` for one turn (all speakers)."""
    if raw is None or processed is None:
        outcome.note_gap()
        return ModalityLayer(
            status=OutcomeStatus.UNAVAILABLE,
            reason=UnavailableReason.INSUFFICIENT_SIGNAL,
        )

    base_labels = compute_nonverbal_base_labels(
        processed,
        config,
        baseline_available=baseline_available,
        session_refs=session_refs,
        unavailable_reasons=reasons,
    )
    integrated = integrate_nonverbal_labels(base_labels, config)
    from app.multimodal.quality_policy import family_evidence_available, QUALITY_POLICY_VERSION
    from app.multimodal.schemas import FamilyLabel
    signal = {"raw": raw.model_dump(), "quality": raw.video_quality}
    for family in type(integrated).model_fields:
        if not family_evidence_available(signal, family):
            setattr(integrated, family, FamilyLabel(status=OutcomeStatus.UNAVAILABLE,
                    reason=UnavailableReason.INSUFFICIENT_SIGNAL))
            outcome.note_gap()
    outcome.note_ok()
    quality = dict(raw.video_quality)
    quality["eligibility_policy_version"] = QUALITY_POLICY_VERSION
    if reasons:
        # Surface per-feature unavailability reasons alongside quality so every
        # null carries an explanation (Requirement 24.3).
        quality = {
            **quality,
            "feature_reasons": {name: reason.value for name, reason in reasons.items()},
        }
    serialized_raw = raw.model_dump()
    for field in ("gaze_yaw_samples", "gaze_pitch_samples", "head_pitch_samples", "head_yaw_samples", "head_roll_samples"):
        if not serialized_raw.get(field):
            serialized_raw.pop(field, None)
    return ModalityLayer(
        raw=serialized_raw,
        processed=processed.model_dump(),
        base_labels=base_labels.model_dump(),
        integrated_labels=integrated.model_dump(),
        quality=quality,
        status=OutcomeStatus.OK,
    )


def _persist_turn(turn: InterviewTurnDB, result: MultimodalTurnResult) -> None:
    """Write the layered per-turn result into the existing JSON columns.

    Paraverbal is written only for student turns (``None`` for patient turns, so
    it is never fabricated). Nonverbal is written for all turns. The persisted
    shape matches design section 20: ``raw``/``processed``/``base_labels``/
    ``integrated_labels``/``quality``/``versions``/``config_hash``/``status``/
    ``reason``. This function only stages the columns on the ORM object; the
    caller commits once (batched writes, Requirement 19.5).
    """
    # ``versions`` and ``config_hash`` live on the turn result, not on the
    # per-modality layer; both persisted layers carry the same methodology
    # provenance so each column is independently traceable (Requirement 16.1,
    # 16.2). Reassigning a new dict (never in-place mutation) marks the plain
    # ``Column(JSON)`` attribute dirty for the caller's batched commit.
    turn.paraverbal = _layer_to_json(
        result.paraverbal, versions=result.versions, config_hash=result.config_hash
    )
    turn.nonverbal_features = _layer_to_json(
        result.nonverbal, versions=result.versions, config_hash=result.config_hash
    )


def _layer_to_json(
    layer: ModalityLayer | None,
    *,
    versions: dict,
    config_hash: str,
) -> dict[str, Any] | None:
    """Serialize one modality layer to the persisted JSON shape, or ``None``.

    Produces the design section-20 shape: ``raw``/``processed``/``base_labels``/
    ``integrated_labels``/``quality``/``versions``/``config_hash``/``status``/
    ``reason``. ``versions`` and ``config_hash`` are the turn-result provenance
    stamped into every persisted modality layer (Requirement 16.1, 16.2).

    ``None`` (e.g. the paraverbal layer of a patient turn) is stored as SQL
    ``NULL`` rather than an empty object, so patient turns carry no fabricated
    paraverbal payload.
    """
    if layer is None:
        return None
    payload = {
        "raw": layer.raw,
        "processed": layer.processed,
        "base_labels": layer.base_labels,
        "integrated_labels": layer.integrated_labels,
        "quality": layer.quality,
        "versions": versions,
        "config_hash": config_hash,
        "status": layer.status.value,
        "reason": layer.reason.value if layer.reason is not None else None,
    }
    from app.multimodal.evidence_text import render_family_evidence
    payload["evidence_text"] = {
        family: description for family in (layer.integrated_labels or {})
        if (description := render_family_evidence(payload, family)) is not None
    }
    return payload


def compute_session_references(
    *,
    processed_by_turn: dict[str, Any],
    feature_names: Sequence[str],
    min_turns: int,
    raw_by_turn: dict[str, Any] | None = None,
) -> dict[str, dict[str, float]] | None:
    """Compute per-feature P25/P75 session references, or ``None`` when guarded.

    Pass 1 (already done by the caller) produced processed features for every
    valid turn. Here, pass 2 computes the session percentiles once: for each
    session-relative feature, gather its non-``None`` values across turns and, if
    at least ``min_turns`` turns qualify, compute P25/P75 with the same linear
    interpolation the preprocessing percentiles use. When fewer than
    ``min_turns`` qualifying turns exist, return ``None`` so every
    session-relative family becomes ``insufficient_reference_data`` (Requirement
    13.3). A feature with no values is simply omitted from the reference map, so
    the threshold engine reports ``insufficient_reference_data`` for it.
    """
    qualifying_turns = len(processed_by_turn)
    if min_turns > 0 and qualifying_turns < min_turns:
        return None
    if qualifying_turns == 0:
        return None

    references: dict[str, dict[str, float]] = {}
    from app.multimodal.quality_policy import reference_feature_available
    for feature in feature_names:
        values = [
            value
            for turn_id, processed in processed_by_turn.items()
            if (value := getattr(processed, feature, None)) is not None
            and isfinite(value)
            and (raw_by_turn is None or reference_feature_available(raw_by_turn.get(turn_id), feature))
        ]
        if len(values) < min_turns or not values:
            continue
        references[feature] = {
            key: _percentile(values, fraction)
            for key, fraction in _SESSION_PERCENTILES.items()
        }
    return references or None


def _percentile(values: Sequence[float], fraction: float) -> float:
    """Percentile via linear interpolation between closest ranks (NumPy default).

    Consistent with ``app/paraverbal/preprocessing._percentile``: for ``n``
    sorted values the target rank is ``fraction * (n - 1)`` and the result
    interpolates linearly between the two bracketing samples. Callers guarantee a
    non-empty input.
    """
    ordered = sorted(float(value) for value in values)
    count = len(ordered)
    if count == 1:
        return ordered[0]
    rank = fraction * (count - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, count - 1)
    weight = rank - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * weight


def _context_for(turn: InterviewTurnDB) -> str:
    """Interaction context from the turn speaker: student -> speaking else listening."""
    return _context_for_speaker(turn.speaker)


def _context_for_speaker(speaker: str) -> str:
    return _CONTEXT_SPEAKING if speaker == _STUDENT_SPEAKER else _CONTEXT_LISTENING


class _OutcomeTracker:
    """Tracks whether the run produced usable outcomes and/or hit any gap.

    Final status rules (Requirement 24.2): if at least one modality/family
    yielded a usable outcome and no gap occurred -> ``complete``; if usable
    outcomes exist but any single feature/modality was missing -> ``partial``
    (never ``failed`` for a single gap); if nothing usable was produced ->
    ``unavailable``. A wholesale failure is handled separately by the caller
    (``failed``) via exception handling.
    """

    def __init__(self) -> None:
        self._any_ok = False
        self._any_gap = False

    def note_ok(self) -> None:
        self._any_ok = True

    def note_gap(self) -> None:
        self._any_gap = True

    def final_status(self) -> str:
        if not self._any_ok:
            return STATUS_UNAVAILABLE
        if self._any_gap:
            return STATUS_PARTIAL
        return STATUS_COMPLETE
