#!/usr/bin/env python3
"""Print a compact multimodal observation summary for one interview (read-only).

Summarizes the layered per-turn shape produced by the multimodal pipeline
(design section 20): per-turn presence of the paraverbal / nonverbal layers,
each layer's ``status`` / ``reason``, the integrated label per family
(``temporal`` / ``prosodic_level`` / ``prosodic_modulation`` for paraverbal;
``visual_orientation`` / ``head_gestural_feedback`` / ``facial_expressivity`` for
nonverbal), and the ``versions`` / ``config_hash`` provenance.

Legacy flat JSON (pre-refactor rows carrying top-level ``speech_rate_wpm`` or
``interpretability.*``) is tolerated: it simply has no layered ``status`` /
``integrated_labels`` and is reported as ``legacy`` without failing. This script
never writes; it only reads and prints.

CLI: ``python -m scripts.verify_observations <interview_id>``.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.medical_interview.interview_recording import (
    InterviewRecordingDB,
    InterviewTurnDB,
)
from app.routers.interview_recordings import _without_none

_PARAVERBAL_FAMILIES = ("temporal", "prosodic_level", "prosodic_modulation")
_NONVERBAL_FAMILIES = (
    "visual_orientation",
    "head_gestural_feedback",
    "facial_expressivity",
)


def _contains_none(value: Any) -> bool:
    if isinstance(value, dict):
        return any(item is None or _contains_none(item) for item in value.values())
    if isinstance(value, list):
        return any(item is None or _contains_none(item) for item in value)
    return False


def _is_layered(payload: Any) -> bool:
    """True when the payload is a layered per-turn result (has a ``status``).

    The pipeline always stamps a ``status`` on each persisted modality layer.
    Legacy flat JSON has no such key, so its absence distinguishes the two shapes
    without importing the legacy adapter (task 8.2).
    """
    return isinstance(payload, dict) and "status" in payload


def _family_integrated(payload: dict[str, Any], families: tuple[str, ...]) -> dict[str, Any]:
    """Extract the integrated label value/status per family from a layered layer."""
    integrated = payload.get("integrated_labels")
    if not isinstance(integrated, dict):
        return {family: None for family in families}
    summary: dict[str, Any] = {}
    for family in families:
        entry = integrated.get(family)
        if isinstance(entry, dict):
            summary[family] = entry.get("value") or entry.get("status")
        else:
            summary[family] = None
    return summary


def _summarize_layer(
    payloads: list[dict[str, Any]],
    families: tuple[str, ...],
) -> dict[str, Any]:
    """Summarize one modality across all turns: presence, statuses, families."""
    layered = [item for item in payloads if _is_layered(item)]
    legacy = [item for item in payloads if item and not _is_layered(item)]

    status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    family_value_counts: dict[str, Counter[str]] = {family: Counter() for family in families}
    versions: Any = None
    config_hash: Any = None

    for item in layered:
        status_counts[str(item.get("status"))] += 1
        reason = item.get("reason")
        if reason is not None:
            reason_counts[str(reason)] += 1
        if versions is None:
            versions = item.get("versions")
        if config_hash is None:
            config_hash = item.get("config_hash")
        for family, value in _family_integrated(item, families).items():
            family_value_counts[family][str(value)] += 1

    return {
        "present": len(payloads),
        "layered": len(layered),
        "legacy": len(legacy),
        "statusCounts": dict(status_counts),
        "reasonCounts": dict(reason_counts),
        "integratedByFamily": {
            family: dict(counts) for family, counts in family_value_counts.items()
        },
        "versions": versions,
        "configHash": config_hash,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize layered multimodal observations for one interview."
    )
    parser.add_argument("interview_id", type=int)
    args = parser.parse_args()

    with SessionLocal() as db:
        recording = db.scalar(
            select(InterviewRecordingDB).where(
                InterviewRecordingDB.medical_interview_id == args.interview_id
            )
        )
        if recording is None:
            raise SystemExit(f"Interview recording {args.interview_id} was not found")

        turns = list(
            db.scalars(
                select(InterviewTurnDB)
                .where(InterviewTurnDB.medical_interview_id == args.interview_id)
                .order_by(InterviewTurnDB.sequence)
            )
        )
        paraverbal = [turn.paraverbal for turn in turns if turn.paraverbal]
        nonverbal = [
            turn.nonverbal_features for turn in turns if turn.nonverbal_features
        ]
        public_payloads = [
            _without_none(payload)
            for turn in turns
            for payload in (turn.paraverbal, turn.nonverbal_features)
            if payload
        ]

        summary = {
            "interviewId": args.interview_id,
            "processing": (recording.capture_config or {}).get(
                "observation_processing"
            ),
            "turnCount": len(turns),
            "paraverbal": _summarize_layer(paraverbal, _PARAVERBAL_FAMILIES),
            "nonverbal": _summarize_layer(nonverbal, _NONVERBAL_FAMILIES),
            "publicPayloadContainsNull": any(
                _contains_none(payload) for payload in public_payloads
            ),
        }
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
