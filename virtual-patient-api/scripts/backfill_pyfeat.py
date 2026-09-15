#!/usr/bin/env python3
"""Backfill nonverbal (Py-Feat) observations for existing interview recordings.

After the multimodal refactor there is no Py-Feat-only backfill path: the staged
pipeline runs the paraverbal and nonverbal modalities together in a single pass.
The former router helper that attached nonverbal observations in isolation has
been removed. This script therefore runs the full multimodal pipeline
(:func:`app.multimodal.pipeline.process_multimodal_interview`), which produces
the nonverbal layer (visual orientation, head gestural feedback, facial
expressivity) as part of the unified run, alongside the paraverbal layer.

It is functionally equivalent to ``scripts/backfill_observations.py`` and is kept
only for the familiar entry-point name. Prefer ``backfill_observations.py`` for
new work, or ``scripts/relabel_multimodal.py`` to re-derive labels from stored
features without re-extracting media.

CLI: ``python -m scripts.backfill_pyfeat <interview_id> [<interview_id> ...]``.
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
        # The unified pipeline produces the nonverbal layer for all turns; it
        # owns its own DB session and never raises to its caller.
        await process_multimodal_interview(interview_id, recording_id)
        print(f"Interview {interview_id}: completed", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill nonverbal observations via the unified multimodal pipeline "
            "for one or more interviews."
        )
    )
    parser.add_argument("interview_ids", nargs="+", type=int)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(backfill(parse_args().interview_ids))
