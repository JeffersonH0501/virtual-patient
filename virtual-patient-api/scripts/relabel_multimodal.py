#!/usr/bin/env python3
"""Relabel stored multimodal turns without re-extracting media (Requirement 21.1).

This script re-derives Base_Labels and Integrated_Labels for one or more
interviews from the *already stored* per-turn raw/processed features, using the
current ``thresholds.yaml`` / ``label_rules.yaml``. It never invokes the
OpenSMILE or shared visual extractors: it reconstructs the typed
``ParaverbalProcessedFeatures`` / ``NonverbalProcessedFeatures`` from each
turn's persisted ``processed`` block, recomputes the per-interview session
references with the pipeline's own two-pass guarded logic, and rewrites
``base_labels`` / ``integrated_labels`` / ``versions`` / ``config_hash`` in
place while preserving the stored ``raw`` / ``processed`` / ``quality`` /
``status`` / ``reason``.

Turns (or modality layers) whose stored ``processed`` block is null/unavailable
are left exactly as-is: without processed features there is nothing to relabel,
and re-running the extractors is explicitly out of scope here.

The layered per-turn JSON shape (written by the pipeline, design section 20):

    {
      "raw": {...} | null,
      "processed": {...} | null,
      "base_labels": {...} | null,
      "integrated_labels": {...} | null,
      "quality": {...},
      "versions": {...},
      "config_hash": "...",
      "status": "ok" | "unavailable" | "insufficient_reference_data",
      "reason": "..." | null
    }

CLI: ``python -m scripts.relabel_multimodal <interview_id> [<interview_id> ...]``
(or ``python scripts/relabel_multimodal.py ...`` from the API directory).
"""

from __future__ import annotations

import argparse
from typing import Any

from app.core.database import SessionLocal
from app.models.medical_interview.interview_recording import InterviewTurnDB
from app.models.medical_interview import MedicalInterviewDB
from app.multimodal.calibration import read_personal_baseline
from app.multimodal.config_loader import MethodologyConfig, load_methodology_config
from app.multimodal.label_engine import (
    integrate_nonverbal_labels,
    integrate_paraverbal_labels,
)
from app.multimodal.pipeline import (
    _NONVERBAL_SESSION_FEATURES,
    _PARAVERBAL_SESSION_FEATURES,
    compute_session_references,
)
from app.multimodal.schemas import (
    NonverbalProcessedFeatures,
    ParaverbalProcessedFeatures,
)
from app.multimodal.threshold_engine import (
    compute_nonverbal_base_labels,
    compute_paraverbal_base_labels,
)

_STUDENT_SPEAKER = "student"


def _reconstruct_processed(
    layer: dict[str, Any] | None,
    model: type,
) -> Any | None:
    """Rebuild a typed processed-features model from a stored modality layer.

    Returns ``None`` when the layer is absent or its ``processed`` block is
    null/unavailable, so the caller leaves that layer untouched (no relabel).
    Validation failures are also treated as "not relabelable" rather than
    fabricating features.
    """
    if not isinstance(layer, dict):
        return None
    processed = layer.get("processed")
    if not isinstance(processed, dict):
        return None
    try:
        return model.model_validate(processed)
    except Exception:  # noqa: BLE001 - a malformed stored block is not relabelable.
        return None


def _collect_processed(
    turns: list[InterviewTurnDB],
    column: str,
    model: type,
    *,
    student_only: bool,
) -> dict[str, Any]:
    """Reconstruct processed features per turn for one modality column.

    ``column`` is ``"paraverbal"`` or ``"nonverbal_features"``. Only turns with a
    usable stored ``processed`` block are included; the rest are omitted so the
    session-reference pass matches the population the pipeline used. Paraverbal is
    student-only (patient turns carry no paraverbal layer).
    """
    processed_by_turn: dict[str, Any] = {}
    for turn in turns:
        if student_only and turn.speaker != _STUDENT_SPEAKER:
            continue
        reconstructed = _reconstruct_processed(getattr(turn, column), model)
        if reconstructed is not None:
            processed_by_turn[turn.id] = reconstructed
    return processed_by_turn


def _relabel_paraverbal_layer(
    layer: dict[str, Any],
    processed: ParaverbalProcessedFeatures,
    config: MethodologyConfig,
    *,
    baseline_available: bool,
    session_refs: dict[str, dict[str, float]] | None,
) -> dict[str, Any]:
    """Rewrite a paraverbal layer's labels/versions/config_hash from stored features."""
    base_labels = compute_paraverbal_base_labels(
        processed,
        config,
        baseline_available=baseline_available,
        session_refs=session_refs,
    )
    integrated = integrate_paraverbal_labels(base_labels, config)
    return _rewrite_labels(layer, base_labels, integrated, config)


def _relabel_nonverbal_layer(
    layer: dict[str, Any],
    processed: NonverbalProcessedFeatures,
    config: MethodologyConfig,
    *,
    baseline_available: bool,
    session_refs: dict[str, dict[str, float]] | None,
) -> dict[str, Any]:
    """Rewrite a nonverbal layer's labels/versions/config_hash from stored features."""
    base_labels = compute_nonverbal_base_labels(
        processed,
        config,
        baseline_available=baseline_available,
        session_refs=session_refs,
    )
    integrated = integrate_nonverbal_labels(base_labels, config)
    return _rewrite_labels(layer, base_labels, integrated, config)


def _rewrite_labels(
    layer: dict[str, Any],
    base_labels: Any,
    integrated: Any,
    config: MethodologyConfig,
) -> dict[str, Any]:
    """Return a new layer dict with recomputed labels and refreshed provenance.

    Preserves the stored ``raw`` / ``processed`` / ``quality`` / ``status`` /
    ``reason`` and only replaces ``base_labels`` / ``integrated_labels`` /
    ``versions`` / ``config_hash``. A new dict is returned (never in-place
    mutation) so SQLAlchemy marks the JSON column dirty.
    """
    updated = dict(layer)
    updated["base_labels"] = base_labels.model_dump()
    updated["integrated_labels"] = integrated.model_dump()
    updated["versions"] = config.versions.model_dump()
    updated["config_hash"] = config.config_hash
    return updated


def relabel(interview_ids: list[int]) -> None:
    """Relabel every stored turn for the given interviews from stored features."""
    config = load_methodology_config()
    min_turns = int(config.thresholds.get("min_turns_for_session_stats", 0) or 0)

    db = SessionLocal()
    try:
        for interview_id in interview_ids:
            interview = (
                db.query(MedicalInterviewDB)
                .filter(MedicalInterviewDB.id == interview_id)
                .first()
            )
            if interview is None:
                print(f"Interview {interview_id}: skipped (interview not found)", flush=True)
                continue

            turns = list(
                db.query(InterviewTurnDB)
                .filter(InterviewTurnDB.medical_interview_id == interview_id)
                .order_by(InterviewTurnDB.sequence)
            )
            if not turns:
                print(f"Interview {interview_id}: skipped (no turns)", flush=True)
                continue

            # Personal baseline gates baseline-relative paraverbal features
            # exactly as it did during the original pipeline run.
            baseline_available = read_personal_baseline(interview) is not None

            # Reconstruct processed features once per modality for the session
            # reference pass, then relabel each turn from the same values.
            paraverbal_processed = _collect_processed(
                turns, "paraverbal", ParaverbalProcessedFeatures, student_only=True
            )
            nonverbal_processed = _collect_processed(
                turns, "nonverbal_features", NonverbalProcessedFeatures, student_only=False
            )

            para_session_refs = compute_session_references(
                processed_by_turn=paraverbal_processed,
                feature_names=_PARAVERBAL_SESSION_FEATURES,
                min_turns=min_turns,
            )
            nonverbal_session_refs = compute_session_references(
                processed_by_turn=nonverbal_processed,
                feature_names=_NONVERBAL_SESSION_FEATURES,
                min_turns=min_turns,
            )

            relabeled_para = 0
            relabeled_nonverbal = 0
            for turn in turns:
                processed = paraverbal_processed.get(turn.id)
                if processed is not None and isinstance(turn.paraverbal, dict):
                    turn.paraverbal = _relabel_paraverbal_layer(
                        turn.paraverbal,
                        processed,
                        config,
                        baseline_available=baseline_available,
                        session_refs=para_session_refs,
                    )
                    relabeled_para += 1

                processed = nonverbal_processed.get(turn.id)
                if processed is not None and isinstance(turn.nonverbal_features, dict):
                    turn.nonverbal_features = _relabel_nonverbal_layer(
                        turn.nonverbal_features,
                        processed,
                        config,
                        baseline_available=baseline_available,
                        session_refs=nonverbal_session_refs,
                    )
                    relabeled_nonverbal += 1

            db.commit()
            print(
                f"Interview {interview_id}: relabeled "
                f"paraverbal={relabeled_para} nonverbal={relabeled_nonverbal} "
                f"(turns={len(turns)}, config_hash={config.config_hash[:12]})",
                flush=True,
            )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-derive base and integrated labels from stored raw/processed "
            "features for one or more interviews, without re-extracting media."
        )
    )
    parser.add_argument("interview_ids", nargs="+", type=int)
    return parser.parse_args()


if __name__ == "__main__":
    relabel(parse_args().interview_ids)
