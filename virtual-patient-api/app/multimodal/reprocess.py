"""Separate observation extraction from evaluation of persisted evidence."""

from __future__ import annotations

import logging

from app.agents.evaluation_agent import EvaluationAgent
from app.core.database import SessionLocal
from app.models.medical_interview import MedicalInterviewDB, InterviewRecordingDB
from app.utils.language import convert_language_code_to_name
from app.multimodal.evaluation_service import evaluate_and_store_multimodal


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _set_evaluation_status(db, recording_id, status):
    recording = db.query(InterviewRecordingDB).filter(InterviewRecordingDB.id == recording_id).first()
    if recording is not None:
        recording.capture_config = {
            **(recording.capture_config or {}),
            "evaluation_processing": {
                **(recording.capture_config or {}).get("evaluation_processing", {}),
                "status": status,
            },
        }
        db.commit()


async def reprocess_interview_evaluation(
    interview_id: int,
    recording_id: str,
) -> None:
    """Replace the multimodal evaluation using already persisted evidence."""
    await _evaluate_saved_evidence(interview_id, recording_id)


async def reprocess_interview_observations(interview_id: int, recording_id: str) -> None:
    """Regenerate observations and evaluate the resulting evidence."""
    # Step 1: run the whole multimodal analysis to completion. It manages its own
    # DB session and the observation_processing lifecycle, and never raises.
    try:
        from app.multimodal.process_isolation import process_multimodal_interview_isolated

        await process_multimodal_interview_isolated(interview_id, recording_id, use_full_video=True)
    except Exception:  # noqa: BLE001 - defensive; the pipeline already guards.
        logger.exception(
            "reprocess_interview interview_id=%s recording_id=%s stage=multimodal "
            "result=failed",
            interview_id,
            recording_id,
        )
        db = SessionLocal()
        try:
            recording = db.query(InterviewRecordingDB).filter(InterviewRecordingDB.id == recording_id).first()
            if recording is not None:
                recording.capture_config = {**(recording.capture_config or {}), "observation_processing": {"status": "failed"}}
                db.commit()
        finally:
            db.close()
    with SessionLocal() as db:
        recording = db.get(InterviewRecordingDB, recording_id)
        observation_status = (recording.capture_config or {}).get("observation_processing", {}).get("status") if recording else None
        if observation_status not in {"complete", "partial", "unavailable"}:
            _set_evaluation_status(db, recording_id, "failed")
            return
    await reprocess_interview_evaluation(interview_id, recording_id)


async def _evaluate_saved_evidence(interview_id: int, recording_id: str) -> None:
    db = SessionLocal()
    try:
        _set_evaluation_status(db, recording_id, "processing")
        interview = (
            db.query(MedicalInterviewDB)
            .filter(MedicalInterviewDB.id == interview_id)
            .first()
        )
        if interview is None:
            logger.warning(
                "reprocess_interview interview_id=%s recording_id=%s stage=evaluation "
                "result=skipped reason=interview_unavailable",
                interview_id,
                recording_id,
            )
            _set_evaluation_status(db, recording_id, "failed")
            return

        # The evaluation language follows the interview owner's preferred
        # language, matching the original completion flow.
        owner_language_code = (
            interview.user.preferred_language if interview.user else None
        ) or "en"
        target_language = convert_language_code_to_name(owner_language_code)
        agent = EvaluationAgent(
            target_language=target_language,
            patient_gender=interview.patient_gender,
        )

        # Review refresh never changes or recreates the text-only control.
        evaluation_results = await evaluate_and_store_multimodal(db, interview_id, agent)
        _set_evaluation_status(db, recording_id, "complete" if evaluation_results else "unavailable")

        logger.info(
            "reprocess_interview interview_id=%s recording_id=%s stage=evaluation "
            "condition=TEXT_PLUS_MULTIMODAL result=persisted aspect_count=%s",
            interview_id,
            recording_id,
            len(evaluation_results),
        )
    except Exception:  # noqa: BLE001 - background task must not propagate.
        db.rollback()
        _set_evaluation_status(db, recording_id, "failed")
        logger.exception(
            "reprocess_interview interview_id=%s recording_id=%s stage=evaluation "
            "result=failed",
            interview_id,
            recording_id,
        )
    finally:
        db.close()
