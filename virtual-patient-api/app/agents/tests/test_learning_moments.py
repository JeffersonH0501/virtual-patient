"""Focused feedback contracts without external model calls."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pydantic import ValidationError
from app.agents.schemas.learning_moments import LearningMomentsOutput, validate_references
from app.models.processing_job import InterviewProcessingJobDB
from app.models.medical_interview.interview_evaluation import InterviewEvaluationDB
from app.multimodal.learning_moments import queue_learning_moments, generate_learning_moments, read_learning_moments, recording_for, build_context
from app.multimodal.conversation_formatter import MultimodalConversationFormatter
from app.agents.prompts.multimodal_evaluation import MULTIMODAL_EVALUATION_CONFIG
from app.multimodal.evaluation_service import evaluate_and_store_multimodal
from app.agents.tests.test_complete_multimodal_evaluation import database, seed_control, MESSAGES, turns


def moment(**changes):
    return {"category": "show_empathy", "type": "improvement", "turn_ids": ["turn-1", "turn-2"],
            "observation": "The concern was followed by another question.",
            "recommendation": "Acknowledge the concern before continuing.", "evidence_used": ["text", "gaze_orientation"], **changes}


CONTEXT = {"turn_ids": ["turn-1", "turn-2"], "response_language": "English",
           "evidence": {category: {} for category in MULTIMODAL_EVALUATION_CONFIG}}
CONTEXT["evidence"]["show_empathy"] = {"turn-1": {"gaze_orientation": {}}, "turn-2": {"gaze_orientation": {}}}


def test_empty_and_multimodal_improvement_are_valid_without_quota():
    assert LearningMomentsOutput(moments=[]).moments == []
    output = LearningMomentsOutput(moments=[moment()])
    assert validate_references(output, CONTEXT) is output


@pytest.mark.parametrize("changes", [{"type": "strength"}, {"evidence_used": ["text"]},
                                     {"turn_ids": ["turn-1", "turn-2"], "evidence_used": ["head_nods"]}])
def test_general_or_unsupported_moments_are_rejected(changes):
    with pytest.raises(ValueError):
        validate_references(LearningMomentsOutput(moments=[moment(**changes)]), CONTEXT)


def test_each_referenced_turn_requires_cited_multimodal_evidence():
    context = {**CONTEXT, "evidence": {**CONTEXT["evidence"], "show_empathy": {"turn-1": {"gaze_orientation": {}}}}}
    with pytest.raises(ValueError):
        validate_references(LearningMomentsOutput(moments=[moment()]), context)


def test_provider_envelope_annotations_are_ignored_without_relaxing_limits():
    output = LearningMomentsOutput.model_validate({"moments": [moment()], "maxItems": 3})
    assert set(output.model_dump()) == {"moments"}
    with pytest.raises(ValidationError):
        LearningMomentsOutput.model_validate({"moments": [moment()] * 4, "maxItems": 3})


@pytest.mark.parametrize("payload", [
    [moment()] * 4, [moment(turn_ids=[])], [moment(turn_ids=["turn-1", "turn-1"])],
    [moment(category="open_communication")], [moment(observation=" ")],
])
def test_invalid_contracts_are_rejected(payload):
    with pytest.raises(ValidationError):
        LearningMomentsOutput(moments=payload)


@pytest.mark.parametrize("changes", [{"turn_ids": ["foreign-turn"]}, {"evidence_used": ["speech_timing"]}, {"category": "show_interest"}])
def test_foreign_turns_and_unavailable_or_unauthorized_evidence_are_rejected(changes):
    with pytest.raises(ValueError):
        validate_references(LearningMomentsOutput(moments=[moment(**changes)]), CONTEXT)


def test_formatter_reuses_quality_and_glossary_with_category_and_speaker_filters():
    evidence = {}
    for category, config in MULTIMODAL_EVALUATION_CONFIG.items():
        config = {**config, "nonverbal_speakers": ("patient",)} if category == "show_interest" else config
        result = MultimodalConversationFormatter.format_messages(MESSAGES, turns(), category, config_override=config, render_evidence=False)
        evidence[category] = result.evidence_by_turn
        assert "NONCANONICAL TEXT" not in result.text
        assert "raw_secret" not in str(result.evidence_by_turn)
    assert set(evidence["show_interest"]) == {"turn-2"}
    assert set(evidence["show_interest"]["turn-2"]) == {"gaze_orientation", "head_nods", "smile_activity"}
    assert "speech_timing" not in evidence["show_empathy"].get("turn-1", {})
    assert set(evidence["speak_clearly"].get("turn-1", {})) <= {"speech_timing", "prosodic_variability"}


def test_scheduling_is_after_persistence_and_failure_keeps_both_scores(database):
    controller, original, recording = seed_control(database)
    before = original.model_dump()
    def fail_queue(db, interview_id):
        assert db.query(InterviewEvaluationDB).count() == 2
        assert recording.capture_config["evaluation_processing"]["status"] == "complete"
        raise RuntimeError("Mock generation queue failure")
    with patch("app.multimodal.learning_moments.queue_learning_moments", side_effect=fail_queue):
        results = asyncio.run(evaluate_and_store_multimodal(database, 7, SimpleNamespace(evaluate_multimodal=AsyncMock()), canonical_messages=MESSAGES))
    assert len(results) == 6
    assert controller.get_evaluation_by_interview_id(7).model_dump() == before
    assert recording.capture_config["learning_moments"]["status"] == "failed"
    assert recording.capture_config["evaluation_processing"]["status"] == "complete"


def test_queue_retries_are_idempotent_and_generation_is_independent(database):
    _, _, recording = seed_control(database)
    InterviewProcessingJobDB.__table__.create(database.get_bind())
    recording.capture_config = {"learning_moments": {"status": "completed", "source_hash": "source", "moments": []}}
    database.commit()
    with patch("app.multimodal.learning_moments.build_context", return_value=(CONTEXT, "source", "run", "evidence")):
        queue_learning_moments(database, 7)
        assert database.query(InterviewProcessingJobDB).count() == 0
        queue_learning_moments(database, 7, force=True)
        queue_learning_moments(database, 7, force=True)
        assert database.query(InterviewProcessingJobDB).count() == 1
    assert database.query(InterviewEvaluationDB).count() == 1  # No scoring rerun.


@pytest.mark.parametrize("corrected", [True, False])
def test_generation_retries_invalid_references_once(database, corrected):
    _, _, recording = seed_control(database)
    invalid = {"parsed": LearningMomentsOutput(moments=[moment(evidence_used=["speech_timing"])])}
    valid = {"parsed": LearningMomentsOutput(moments=[moment()])}
    invocation = AsyncMock(side_effect=[invalid, valid if corrected else invalid])
    agent = MagicMock()
    agent.llm.with_structured_output.return_value.ainvoke = invocation
    with patch("app.core.database.SessionLocal", return_value=database), patch(
        "app.agents.evaluation_agent.EvaluationAgent", return_value=agent,
    ), patch("app.multimodal.learning_moments.build_context", return_value=(CONTEXT, "source", "run", "evidence")):
        asyncio.run(generate_learning_moments(7, recording.id, force=True))
        state = read_learning_moments(database, 7)
    assert invocation.await_count == 2
    assert state["status"] == ("completed" if corrected else "failed")
    assert len(state["moments"]) == int(corrected)


@pytest.mark.parametrize("fail", [False, True])
def test_generation_and_failed_regeneration_preserve_evaluations(database, fail):
    _, _, recording = seed_control(database)
    old = [{"id": "old", **moment()}]
    recording.capture_config = {"learning_moments": {"status": "completed", "source_hash": "old-source", "moments": old}}
    database.commit()
    scores_before = database.query(InterviewEvaluationDB).first().evaluation_results.copy()
    invocation = AsyncMock(side_effect=RuntimeError("Mock provider failure")) if fail else AsyncMock(return_value={"parsed": LearningMomentsOutput(moments=[moment()])})
    agent = MagicMock()
    agent.llm.with_structured_output.return_value.ainvoke = invocation
    agent.llm.model_name = "mock-model"
    with patch("app.core.database.SessionLocal", return_value=database), patch("app.agents.evaluation_agent.EvaluationAgent", return_value=agent), patch("app.multimodal.learning_moments.build_context", return_value=(CONTEXT, "source", "run", "evidence")):
        asyncio.run(generate_learning_moments(7, recording.id, force=True))
        state = read_learning_moments(database, 7)
        if fail:
            assert state["status"] == "failed" and state["stale"]
            assert recording_for(database, 7).capture_config["learning_moments"]["moments"] == old
            assert state["moments"] == []
        else:
            assert state["status"] == "completed" and not state["stale"]
            assert state["moments"][0]["turn_ids"] == ["turn-1", "turn-2"]
            assert state["evaluation_run_id"] == "run"
    assert database.query(InterviewEvaluationDB).first().evaluation_results == scores_before
