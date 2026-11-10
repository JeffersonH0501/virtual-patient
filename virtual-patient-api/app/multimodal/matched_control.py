"""Optional research control for prompt/schema confounding; not an app condition."""
from dataclasses import replace
from enum import Enum
from app.agents.prompts.multimodal_evaluation import MULTIMODAL_EVALUATION_CONFIG
from app.agents.schemas.evaluation import EvaluationResult
from app.models.medical_interview.interview_recording import InterviewTurnDB
from app.multimodal.conversation_formatter import MultimodalConversationFormatter
from app.multimodal.evaluation_runs import stage_evaluation_run


class ResearchCondition(str, Enum):
    MATCHED_TEXT_CONTROL = "MATCHED_TEXT_CONTROL"


async def evaluate_matched_text_control(db, interview_id, agent, canonical_messages):
    """Use the same enriched prompt, IDs and schema with every signal unavailable.

    This adds three explicitly requested research LLM calls. It never overwrites
    either application condition or automatically runs during completion.
    """
    turns = db.query(InterviewTurnDB).filter(InterviewTurnDB.medical_interview_id == interview_id).all()
    conversations = {aspect: replace(MultimodalConversationFormatter.format_messages(
        canonical_messages, turns, aspect, include_evidence=False), has_valid_evidence=True)
        for aspect in MULTIMODAL_EVALUATION_CONFIG}
    results = await agent.evaluate_multimodal(conversations)
    run_id = stage_evaluation_run(db, interview_id, ResearchCondition.MATCHED_TEXT_CONTROL, agent, {
        "canonical_messages": canonical_messages,
        "conversations": {aspect: item.text for aspect, item in conversations.items()},
        "prompts": {aspect: config["prompt"](agent.target_language) for aspect, config in MULTIMODAL_EVALUATION_CONFIG.items()},
        "output_schema": EvaluationResult.model_json_schema(),
        "structured_output_method": "function_calling",
    }, {"evaluation_results": [result.model_dump(mode="json") for result in results]})
    db.commit()
    return run_id, results
