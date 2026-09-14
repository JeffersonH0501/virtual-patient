"""Print a compact observation-processing summary for one interview."""

from __future__ import annotations

import argparse
import json
from typing import Any

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.medical_interview.interview_recording import (
    InterviewRecordingDB,
    InterviewTurnDB,
)
from app.routers.interview_recordings import _without_none


def _contains_none(value: Any) -> bool:
    if isinstance(value, dict):
        return any(item is None or _contains_none(item) for item in value.values())
    if isinstance(value, list):
        return any(item is None or _contains_none(item) for item in value)
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
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
        interpreted = [
            item["interpretability"]["acoustic_temporal"]
            for item in paraverbal
            if item.get("interpretability", {}).get("acoustic_temporal")
        ]
        public_payloads = [
            _without_none(payload)
            for turn in turns
            for payload in (
                turn.paraverbal,
                turn.nonverbal_features,
            )
            if payload
        ]

        summary = {
            "interviewId": args.interview_id,
            "processing": (recording.capture_config or {}).get(
                "observation_processing"
            ),
            "turnCount": len(turns),
            "available": {
                "paraverbal": len(paraverbal),
                "nonverbal": len(nonverbal),
            },
            "interpretability": {
                "turnCount": len(interpreted),
                "labelStatus": interpreted[0]["labels"]["status"]
                if interpreted
                else None,
                "calibrationVersion": interpreted[0]["calibration"]["version"]
                if interpreted
                else None,
                "temporalProfiles": [
                    item["labels"]["values"].get("temporal_profile")
                    for item in interpreted
                ],
            },
            "publicPayloadContainsNull": any(
                _contains_none(payload) for payload in public_payloads
            ),
        }
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
