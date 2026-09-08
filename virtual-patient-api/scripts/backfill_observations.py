#!/usr/bin/env python3
"""Backfill all derived recording observations for existing interviews."""

from __future__ import annotations

import argparse
import asyncio

from app.core.database import SessionLocal
from app.models.medical_interview.interview_recording import InterviewRecordingDB
from app.routers.interview_recordings import _process_recording_observations


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
        await _process_recording_observations(interview_id, recording_id)
        print(f"Interview {interview_id}: completed", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill all derived observations for one or more interviews."
    )
    parser.add_argument("interview_ids", nargs="+", type=int)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(backfill(parse_args().interview_ids))
