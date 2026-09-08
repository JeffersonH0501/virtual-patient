#!/usr/bin/env python3
"""Backfill Py-Feat observations for existing interview recordings."""

from __future__ import annotations

import argparse
import asyncio

from app.core.database import SessionLocal
from app.media.storage import get_media_storage
from app.models.medical_interview.interview_recording import InterviewRecordingDB
from app.routers.interview_recordings import (
    _attach_student_pyfeat_benchmark_observations,
)


async def backfill(interview_ids: list[int]) -> None:
    db = SessionLocal()
    try:
        storage = get_media_storage()
        for interview_id in interview_ids:
            recording = (
                db.query(InterviewRecordingDB)
                .filter(InterviewRecordingDB.medical_interview_id == interview_id)
                .first()
            )
            if recording is None:
                print(f"Interview {interview_id}: skipped (recording not found)", flush=True)
                continue

            print(f"Interview {interview_id}: processing", flush=True)
            await _attach_student_pyfeat_benchmark_observations(
                db=db,
                storage=storage,
                interview_id=interview_id,
                recording=recording,
            )
            db.commit()
            print(f"Interview {interview_id}: completed", flush=True)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill Py-Feat observations for one or more interviews."
    )
    parser.add_argument("interview_ids", nargs="+", type=int)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(backfill(parse_args().interview_ids))
