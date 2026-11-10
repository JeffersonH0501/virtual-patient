"""Assemble six-category results while preserving the stored textual control."""

from app.agents.prompts.multimodal_evaluation import MULTIMODAL_EVALUATION_CONFIG, POLICY_VERSION
from app.controllers.interview_evaluation_controller import InterviewEvaluationController
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.models.medical_interview.interview_evaluation import EvaluationCondition, InterviewEvaluationCreate
from app.models.medical_interview.interview_recording import InterviewRecordingDB
from .conversation_formatter import MultimodalConversationFormatter
from .evaluation_runs import stage_evaluation_run
from .quality_policy import QUALITY_POLICY_VERSION
from app.agents.schemas.evaluation import EvaluationResult
from app.models.medical_interview.interview_recording import InterviewTurnDB

EVALUATION_CATEGORY_ORDER = (
    "general_communication", "completeness", "show_interest",
    "show_empathy", "speak_clearly", "open_communication",
)


def validate_text_control(results):
    """Reject incomplete or technical-error results before persisting a control."""
    text_results = {result.aspect: result for result in results}
    technical_markers = ("evaluation failed due to technical error", "evaluation failed:", "completeness evaluation failed")
    if any(any(marker in result.feedback.lower() for marker in technical_markers) for result in results):
        raise ValueError("Legacy technical fallback results are not valid performance measurements")
    if len(results) != 6 or set(text_results) != set(EVALUATION_CATEGORY_ORDER):
        raise ValueError("TEXT_ONLY must contain exactly the six evaluation categories")
    return text_results


async def evaluate_and_store_multimodal(db, interview_id, agent, *, canonical_messages=None):
    controller = InterviewEvaluationController(db)
    original = controller.get_evaluation_by_interview_id(interview_id)
    if original is None:
        raise ValueError("A complete TEXT_ONLY evaluation is required")
    text_results = validate_text_control(original.evaluation_results)
    if canonical_messages is None:
        source = MedicalInterviewController(db)
        messages = source.get_interview_evaluation_data(interview_id)["messages"]
        canonical_messages = source.format_messages_for_evaluation(messages)
    formatter = MultimodalConversationFormatter(db)
    conversations = {
        aspect: formatter.load(interview_id, aspect, canonical_messages)
        for aspect in MULTIMODAL_EVALUATION_CONFIG
    }
    available = {aspect: conversation for aspect, conversation in conversations.items()
                 if conversation.has_valid_evidence}
    evidence_snapshot = [{key: getattr(turn, key) for key in (
        "id", "message_id", "speaker", "start_ms", "end_ms", "timing_quality", "paraverbal", "nonverbal_features",
    )} for turn in db.query(InterviewTurnDB).filter(InterviewTurnDB.medical_interview_id == interview_id).all()]
    enriched_results = await agent.evaluate_multimodal(available) if available else []
    enriched_by_aspect = {result.aspect: result for result in enriched_results}
    if len(enriched_by_aspect) != len(enriched_results) or set(enriched_by_aspect) != set(available):
        raise ValueError("Multimodal evaluation did not return every available category exactly once")
    results = [enriched_by_aspect.get(aspect, text_results[aspect]) for aspect in EVALUATION_CATEGORY_ORDER]
    payload = InterviewEvaluationCreate(
        evaluation_condition=EvaluationCondition.TEXT_PLUS_MULTIMODAL,
        evaluation_results=results,
        overall_score=controller.calculate_overall_score(results),
    )
    run_id = stage_evaluation_run(db, interview_id, payload.evaluation_condition, agent, {
        "canonical_messages": canonical_messages,
        "policy_version": POLICY_VERSION,
        "conversations": {aspect: conversation.text for aspect, conversation in conversations.items()},
        "prompts": {aspect: config["prompt"](getattr(agent, "target_language", "English"))
                    for aspect, config in MULTIMODAL_EVALUATION_CONFIG.items()},
        "available_aspects": list(available),
        "evidence": evidence_snapshot,
        "quality_policy_version": QUALITY_POLICY_VERSION,
        "output_schema": EvaluationResult.model_json_schema(),
        "text_only_control": original.model_dump(mode="json"),
        "structured_output_method": "function_calling",
    }, payload)
    if controller.update_evaluation(interview_id, payload, commit=False) is None:
        controller.create_evaluation(interview_id, payload, commit=False)
    # Record fallback explicitly without changing the copied EvaluationResult payloads.
    recording = db.query(InterviewRecordingDB).filter(
        InterviewRecordingDB.medical_interview_id == interview_id,
    ).first()
    if recording is not None:
        capture = recording.capture_config or {}
        recording.capture_config = {
            **capture,
            "evaluation_processing": {
                **capture.get("evaluation_processing", {}),
                "status": "complete",
                "policy_version": POLICY_VERSION,
                "run_id": run_id,
                "evidence_availability": {
                    aspect: "available" if aspect in available else "unavailable_text_fallback"
                    for aspect in MULTIMODAL_EVALUATION_CONFIG
                },
            },
        }
    db.commit()
    if recording is not None:
        try:
            from .learning_moments import queue_learning_moments
            queue_learning_moments(db, interview_id)
        except Exception:
            # The evaluation is already committed and must remain available.
            import logging
            db.rollback()
            try:
                recording.capture_config = {**(recording.capture_config or {}), "learning_moments": {
                    **(recording.capture_config or {}).get("learning_moments", {}),
                    "status": "failed", "error_code": "learning_moments_queue_failed",
                }}
                db.commit()
            except Exception:
                db.rollback()  # Even failure-status persistence cannot invalidate scoring.
            logging.getLogger(__name__).error("Learning moments scheduling failed interview_id=%s", interview_id)
    return results
