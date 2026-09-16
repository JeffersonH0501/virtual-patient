#!/usr/bin/env python3
"""Backfill multimodal observations for existing interviews.

Re-runs the full staged multimodal pipeline
(:func:`app.multimodal.pipeline.process_multimodal_interview`) for one or more
interviews. The pipeline re-extracts media (OpenSMILE + OpenFace 3.0), preprocesses,
thresholds, and labels both modalities in a single pass, then persists the
layered per-turn result. To relabel from *already stored* raw/processed features
*without* re-extracting media, use ``scripts/relabel_multimodal.py`` instead.

CLI: ``python -m scripts.backfill_observations <interview_id> [<interview_id> ...]``.
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.database import SessionLocal
from app.models.medical_interview.interview_recording import InterviewRecordingDB
from app.multimodal.pipeline import process_multimodal_interview


async def backfill(interview_ids: list[int]) -> None:
    db = SessionLocal()
    try:
        recordings = {
            recording.medical_interview_id: recording.id
            for recording in db.query(InterviewRecordingDB).filter(
                InterviewRecordingDB.medical_interview_id.in_(interview_ids)
            )
        }
    finally:
        db.close()

    for interview_id in interview_ids:
        recording_id = recordings.get(interview_id)
        if recording_id is None:
            print(f"Interview {interview_id}: skipped (recording not found)", flush=True)
            continue
        print(f"Interview {interview_id}: processing", flush=True)
        # process_multimodal_interview owns its own DB session and never raises;
        # it records a failed observation-processing status on error.
        await process_multimodal_interview(interview_id, recording_id)
        print(f"Interview {interview_id}: completed", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill the multimodal pipeline for one or more interviews."
    )
    parser.add_argument("interview_ids", nargs="+", type=int)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(backfill(parse_args().interview_ids))
