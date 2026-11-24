"""Print a privacy-safe, durable technical report for one interview flow."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from app.core.database import SessionLocal
from app.models.medical_interview import (
    InterviewMediaAssetDB,
    InterviewTurnDB,
    MedicalInterviewDB,
    TurnVideoAnalysisDB,
)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _elapsed_ms(start: datetime | None, end: datetime | None) -> int | None:
    if not start or not end:
        return None
    return round((end - start).total_seconds() * 1000)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _feature_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    return {
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "processed": payload.get("processed"),
        "integrated_labels": payload.get("integrated_labels"),
        "quality": payload.get("quality"),
        "versions": payload.get("versions"),
        "config_hash": payload.get("config_hash"),
    }


def build_report(interview_id: int) -> dict[str, Any]:
    with SessionLocal() as db:
        interview = db.query(MedicalInterviewDB).filter(
            MedicalInterviewDB.id == interview_id
        ).first()
        if interview is None:
            raise LookupError(f"Interview {interview_id} was not found")

        recording = interview.recording
        assets = []
        if recording is not None:
            assets = db.query(InterviewMediaAssetDB).filter(
                InterviewMediaAssetDB.recording_id == recording.id
            ).order_by(InterviewMediaAssetDB.kind).all()

        turns = db.query(InterviewTurnDB).filter(
            InterviewTurnDB.medical_interview_id == interview_id
        ).order_by(InterviewTurnDB.sequence).all()
        jobs = db.query(TurnVideoAnalysisDB).filter(
            TurnVideoAnalysisDB.medical_interview_id == interview_id
        ).all()
        jobs_by_turn = {job.turn_id: job for job in jobs}

        calibration = (interview.interview_metadata or {}).get("calibration") or {}
        calibration_profile = calibration.get("profile") or {}
        evaluation = interview.interview_evaluation

        return {
            "interview": {
                "id": interview.id,
                "public_id": interview.public_id,
                "status": _enum_value(interview.status),
                "created_at": _iso(interview.created_at),
                "started_at": _iso(interview.start_time),
                "completed_at": _iso(interview.end_time),
                "duration_seconds": interview.total_duration,
                "completion_reason": (interview.interview_metadata or {}).get(
                    "completion_reason"
                ),
            },
            "calibration": {
                "version": calibration.get("version"),
                "status": calibration.get("status"),
                "failure_reason": calibration.get("failure_reason"),
                "completed_at": calibration.get("completed_at"),
                "algorithm": calibration_profile.get("algorithm"),
                "quality": calibration.get("quality"),
                "personal_baseline_available": bool(
                    calibration.get("personal_baseline")
                ),
            },
            "recording": None if recording is None else {
                "id": recording.id,
                "status": recording.status,
                "failure_code": recording.failure_code,
                "started_at": _iso(recording.started_at),
                "ended_at": _iso(recording.ended_at),
                "duration_ms": recording.duration_ms,
                "observation_processing": (
                    recording.capture_config or {}
                ).get("observation_processing"),
                "assets": [
                    {
                        "kind": asset.kind,
                        "status": asset.status,
                        "content_type": asset.content_type,
                        "size_bytes": asset.size_bytes,
                        "duration_ms": asset.duration_ms,
                    }
                    for asset in assets
                ],
            },
            "turns": [
                {
                    "sequence": turn.sequence,
                    "turn_id": turn.id,
                    "speaker": turn.speaker,
                    "start_ms": turn.start_ms,
                    "end_ms": turn.end_ms,
                    "duration_ms": turn.end_ms - turn.start_ms,
                    "video_job": None if turn.id not in jobs_by_turn else {
                        "status": jobs_by_turn[turn.id].status,
                        "error": jobs_by_turn[turn.id].error,
                        "queued_at": _iso(jobs_by_turn[turn.id].queued_at),
                        "started_at": _iso(jobs_by_turn[turn.id].started_at),
                        "completed_at": _iso(jobs_by_turn[turn.id].completed_at),
                        "queue_wait_ms": _elapsed_ms(
                            jobs_by_turn[turn.id].queued_at,
                            jobs_by_turn[turn.id].started_at,
                        ),
                        "processing_ms": _elapsed_ms(
                            jobs_by_turn[turn.id].started_at,
                            jobs_by_turn[turn.id].completed_at,
                        ),
                        "size_bytes": jobs_by_turn[turn.id].size_bytes,
                    },
                    "paraverbal": _feature_summary(turn.paraverbal),
                    "nonverbal": _feature_summary(turn.nonverbal_features),
                }
                for turn in turns
            ],
            "evaluation": None if evaluation is None else {
                "overall_score": evaluation.overall_score,
                "completed_at": _iso(evaluation.completion_timestamp),
                "aspects": [
                    {
                        "aspect": result.get("aspect"),
                        "score": result.get("score"),
                    }
                    for result in (evaluation.evaluation_results or [])
                ],
            },
            "completion_order": {
                "last_turn_analysis_completed_at": _iso(max(
                    (job.completed_at for job in jobs if job.completed_at),
                    default=None,
                )),
                "interview_completed_at": _iso(interview.end_time),
                "completed_after_all_turns": bool(
                    interview.end_time
                    and all(job.completed_at for job in jobs)
                    and interview.end_time >= max(job.completed_at for job in jobs)
                ) if jobs else bool(interview.end_time),
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("interview_id", type=int)
    args = parser.parse_args()
    try:
        report = build_report(args.interview_id)
    except LookupError as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
