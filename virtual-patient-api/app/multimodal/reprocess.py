"""Regeneration orchestrator for the review screen.

This module wires the two pipelines that produce a finished evaluation, in the
order the review "Regenerate evaluation" action requires:

1. The full multimodal pipeline (:func:`process_multimodal_interview`) runs to
   completion first. It re-extracts paraverbal (OpenSMILE) and non-verbal
   (MediaPipe/BlazeGaze/CCDb-HG) evidence, re-derives the per-turn integrated
   labels and overwrites ``interview_turns.paraverbal`` /
   ``interview_turns.nonverbal_features``. It owns its own DB session and
   advances the ``observation_processing`` lifecycle in
   ``recording.capture_config``.

2. Only after that stage finishes does the final communication evaluation run
   again (Bayona's textual rubric via :class:`EvaluationAgent`), replacing the
   stored :class:`InterviewEvaluationDB` in place.

The two operations are deliberately sequential: the final evaluation cannot
start until the multimodal analysis has produced the per-turn integrated
labels. This mirrors the "recording -> multimodal -> text-evaluation" boundary
already prepared in :mod:`app.multimodal.pipeline`, but keeps the methodology
module free of evaluation-agent wiring.

Scheduled by the router as a FastAPI background task. Like the multimodal
pipeline it never raises to its caller: any unexpected failure is logged and the
interview is left in a consistent, observable state.
"""

from __future__ import annotations

import logging

from app.agents.evaluation_agent import EvaluationAgent
from app.controllers.interview_evaluation_controller import InterviewEvaluationController
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.core.database import SessionLocal
from app.models.medical_interview import MedicalInterviewDB
from app.models.medical_interview import InterviewEvaluationCreate
from app.multimodal.pipeline import process_multimodal_interview
from app.utils.language import convert_language_code_to_name


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


_EVALUATION_ASPECTS = [
    "general_communication",
    "completeness",
    "show_interest",
    "show_empathy",
    "speak_clearly",
    "open_communication",
]


async def reprocess_interview_evaluation(
    interview_id: int,
    recording_id: str,
) -> None:
    """Re-run the multimodal pipeline, then the final text evaluation.

    This is the entry point scheduled by
    ``POST /medical-interviews/{interview_id}/recording/reprocess``. The interview
    is expected to already be ``completed`` (guarded at the router); the
    regeneration overwrites both the per-turn multimodal evidence and the stored
    interview evaluation without changing the interview lifecycle status, so the
    review screen and its recap stay reachable while the work runs and the UI
    tracks progress through ``observation_processing``.
    """
    # Step 1: run the whole multimodal analysis to completion. It manages its own
    # DB session and the observation_processing lifecycle, and never raises.
    try:
        await process_multimodal_interview(interview_id, recording_id, use_full_video=True)
    except Exception:  # noqa: BLE001 - defensive; the pipeline already guards.
        logger.exception(
            "reprocess_interview interview_id=%s recording_id=%s stage=multimodal "
            "result=failed",
            interview_id,
            recording_id,
        )
        return

    # Step 2: only after the multimodal pipeline finished, re-run the final
    # textual evaluation and overwrite the stored evaluation in place.
    db = SessionLocal()
    try:
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
            return

        controller = MedicalInterviewController(db)
        evaluation_data = controller.get_interview_evaluation_data(interview_id)
        formatted_messages = controller.format_messages_for_evaluation(
            evaluation_data["messages"]
        )

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

        evaluation_results = await agent.evaluate_all_aspects(
            conversation_messages=formatted_messages,
            clinical_case=evaluation_data["clinical_case"],
            progress_summary=evaluation_data["progress_summary"],
            hypotheses=evaluation_data.get("hypotheses", []),
            aspects=_EVALUATION_ASPECTS,
        )

        if not evaluation_results:
            logger.warning(
                "reprocess_interview interview_id=%s recording_id=%s stage=evaluation "
                "result=skipped reason=no_results",
                interview_id,
                recording_id,
            )
            return

        evaluation_controller = InterviewEvaluationController(db)
        overall_score = evaluation_controller.calculate_overall_score(evaluation_results)
        payload = InterviewEvaluationCreate(
            evaluation_results=evaluation_results,
            overall_score=overall_score,
        )
        # An interview reaching review always has a stored evaluation, so update
        # in place; fall back to create if it is somehow missing.
        updated = evaluation_controller.update_evaluation(interview_id, payload)
        if updated is None:
            evaluation_controller.create_evaluation(interview_id, payload)

        logger.info(
            "reprocess_interview interview_id=%s recording_id=%s stage=evaluation "
            "result=persisted aspect_count=%s overall_score=%s",
            interview_id,
            recording_id,
            len(evaluation_results),
            overall_score,
        )
    except Exception:  # noqa: BLE001 - background task must not propagate.
        db.rollback()
        logger.exception(
            "reprocess_interview interview_id=%s recording_id=%s stage=evaluation "
            "result=failed",
            interview_id,
            recording_id,
        )
    finally:
        db.close()
