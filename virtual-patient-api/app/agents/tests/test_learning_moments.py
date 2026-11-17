"""Learning moment pipeline contracts without external model calls."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pydantic import ValidationError
from app.agents.schemas.learning_moments import LearningMomentOutput, LearningMoment, LearningMomentReferenceError, validate_moment
from app.models.processing_job import InterviewProcessingJobDB
from app.models.medical_interview.interview_evaluation import InterviewEvaluationDB
from app.multimodal.learning_moments import queue_learning_moments, generate_learning_moments, read_learning_moments, recording_for, build_category_message
from app.multimodal.conversation_formatter import MultimodalConversationFormatter
from app.agents.prompts.multimodal_evaluation import MULTIMODAL_EVALUATION_CONFIG
from app.agents.prompts.learning_moments import get_learning_moment_prompts
from app.multimodal.evaluation_service import evaluate_and_store_multimodal
from app.agents.tests.test_complete_multimodal_evaluation import database, seed_control, MESSAGES, turns

# Category order matches the per-category generation loop (one call per category).
CATEGORY_ORDER = ("show_interest", "show_empathy", "speak_clearly")


def moment(**changes):
    return {"category": "show_empathy", "turn_ids": ["T1"],
            "text": "When she said she felt sad you looked away. Look at the camera while she speaks.",
            "evidence_used": ["gaze_orientation"], **changes}


CONTEXT = {"turn_ids": ["T1", "T2"], "response_language": "English",
           "alias_to_turn_id": {"T1": "turn-1", "T2": "turn-2"},
           "transcripts": {category: "[TURN T1 speaker=DOCTOR]\nDOCTOR: Hello" for category in MULTIMODAL_EVALUATION_CONFIG},
           "criteria": {category: ["Criterion"] for category in MULTIMODAL_EVALUATION_CONFIG},
           "evaluations": {category: {"score": 3, "feedback": "f"} for category in MULTIMODAL_EVALUATION_CONFIG},
           "evidence": {category: {} for category in MULTIMODAL_EVALUATION_CONFIG}}
CONTEXT["evidence"]["show_empathy"] = {"T1": {"gaze_orientation": {}}, "T2": {"gaze_orientation": {}}}
CONTEXT["evidence"]["speak_clearly"] = {"T1": {"speech_timing": {}}, "T2": {"speech_timing": {}}}
NONE = {"parsed": LearningMomentOutput(moment=None)}


def _raw(**changes):
    return {"parsed": {"moment": moment(**changes)}}


def _run_generation(database, recording, side_effect):
    invocation = AsyncMock(side_effect=side_effect)
    agent = MagicMock()
    agent.llm.with_structured_output.return_value.ainvoke = invocation
    agent.llm.model_name = "mock-model"
    with patch("app.core.database.SessionLocal", return_value=database), patch("app.agents.evaluation_agent.EvaluationAgent", return_value=agent), patch("app.multimodal.learning_moments.build_context", return_value=(CONTEXT, "source", "run", "evidence")):
        asyncio.run(generate_learning_moments(7, recording.id, force=True))
        state = read_learning_moments(database, 7)
    return invocation, state


def test_category_message_has_labeled_sections_and_uses_alias_turns():
    message = build_category_message(CONTEXT, "show_empathy")
    assert message.startswith("RESPONSE LANGUAGE: English")
    assert "=== TRANSCRIPT (START) ===" in message and "=== TRANSCRIPT (END) ===" in message
    assert "=== EVIDENCE BY TURN" in message and "=== CRITERIA FOR THIS CATEGORY ===" in message
    assert "=== PRIOR EVALUATION FOR THIS CATEGORY (do not repeat its points) ===" in message
    assert "T1: gaze_orientation" in message and "turn-1" not in message


def test_prompts_render_one_per_category_in_the_requested_language():
    for language in ("English", "Spanish"):
        prompts = get_learning_moment_prompts(language)
        assert set(prompts) == set(CATEGORY_ORDER)
        for prompt in prompts.values():
            assert language in prompt and "{response_language}" not in prompt


@pytest.mark.parametrize("payload", [
    moment(turn_ids=[]), moment(turn_ids=["T1", "T1"]), moment(turn_ids=["T1", "T2", "T3"]),
    moment(category="open_communication"), moment(text=" "),
])
def test_invalid_contracts_are_rejected(payload):
    with pytest.raises(ValidationError):
        LearningMomentOutput(moment=payload)


def test_only_existing_turns_and_the_generated_category_are_accepted():
    assert validate_moment(LearningMoment(**moment()), "show_empathy", CONTEXT)
    with pytest.raises(LearningMomentReferenceError):
        validate_moment(LearningMoment(**moment(turn_ids=["T9"])), "show_empathy", CONTEXT)
    with pytest.raises(LearningMomentReferenceError):
        validate_moment(LearningMoment(**moment()), "show_interest", CONTEXT)


def test_formatter_reuses_quality_and_glossary_with_category_and_speaker_filters():
    evidence = {}
    for category in MULTIMODAL_EVALUATION_CONFIG:
        result = MultimodalConversationFormatter.format_messages(MESSAGES, turns(), category)
        evidence[category] = result.evidence_by_turn
        assert result.alias_to_turn_id == {"T1": "turn-1", "T2": "turn-2"}
        assert "NONCANONICAL TEXT" not in result.text and "raw_secret" not in str(result.evidence_by_turn)
    assert set(evidence["show_interest"]) == {"T2"}
    assert set(evidence["show_interest"]["T2"]) == {"gaze_orientation", "head_nods", "smile_activity"}
    assert "speech_timing" in evidence["show_empathy"].get("T1", {})
    assert set(evidence["speak_clearly"].get("T1", {})) <= {"speech_timing", "prosodic_level", "prosodic_variability"}


def test_synchronous_generation_runs_after_persistence_and_failure_keeps_scores(database):
    controller, original, recording = seed_control(database)
    before = original.model_dump()

    async def fail_generation(interview_id, recording_id, force=False):
        assert database.query(InterviewEvaluationDB).count() == 2
        raise RuntimeError("Mock generation failure")

    with patch("app.multimodal.learning_moments.generate_learning_moments", side_effect=fail_generation) as generate:
        results = asyncio.run(evaluate_and_store_multimodal(database, 7, SimpleNamespace(evaluate_multimodal=AsyncMock()), canonical_messages=MESSAGES))
    generate.assert_awaited_once()
    assert len(results) == 6
    assert controller.get_evaluation_by_interview_id(7).model_dump() == before


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
    assert database.query(InterviewEvaluationDB).count() == 1


def test_one_call_per_category_and_the_wording_is_stored_as_returned(database):
    _, _, recording = seed_control(database)
    wording = {"text": "Mostró atención mientras ella hablaba. Esta categoría espera más."}
    invocation, state = _run_generation(database, recording, [NONE, _raw(**wording), _raw(category="speak_clearly")])
    assert invocation.await_count == 3  # No retries.
    assert state["status"] == "completed"
    assert [m["category"] for m in state["moments"]] == ["show_empathy", "speak_clearly"]
    assert {key: state["moments"][0][key] for key in wording} == wording
    assert state["moments"][0]["turn_ids"] == ["turn-1"]


def test_category_and_evidence_come_from_the_call_and_the_cited_turns(database):
    # The model omitted `category` and `evidence_used` or named a signal the turn lacks.
    _, _, recording = seed_control(database)
    raw = {key: value for key, value in moment().items() if key not in ("category", "evidence_used")}
    _, state = _run_generation(database, recording, [
        NONE, {"parsed": {"moment": raw}}, _raw(category="show_interest", evidence_used=["smile_activity"])])
    assert [(m["category"], m["evidence_used"]) for m in state["moments"]] == [
        ("show_empathy", ["gaze_orientation"]), ("speak_clearly", ["speech_timing"])]


def test_unusable_output_skips_only_that_category(database):
    _, _, recording = seed_control(database)
    no_delivery = {"parsed": {"moment": {key: value for key, value in moment(category="show_interest").items() if key != "text"}}}
    _, state = _run_generation(database, recording, [no_delivery, _raw(turn_ids=["T9"]), _raw(category="speak_clearly")])
    assert state["status"] == "completed"
    assert [m["category"] for m in state["moments"]] == ["speak_clearly"]


@pytest.mark.parametrize("fail", [False, True])
def test_generation_and_failed_regeneration_preserve_evaluations(database, fail):
    _, _, recording = seed_control(database)
    old = [{"id": "old", **moment()}]
    recording.capture_config = {"learning_moments": {"status": "completed", "source_hash": "old-source", "moments": old}}
    database.commit()
    scores_before = database.query(InterviewEvaluationDB).first().evaluation_results.copy()
    side_effect = RuntimeError("Mock provider failure") if fail else [NONE, _raw(turn_ids=["T1", "T2"]), NONE]
    _, state = _run_generation(database, recording, side_effect)
    if fail:
        assert state["status"] == "failed" and state["stale"]
        assert recording_for(database, 7).capture_config["learning_moments"]["moments"] == old
    else:
        assert state["status"] == "completed" and not state["stale"]
        assert state["moments"][0]["turn_ids"] == ["turn-1", "turn-2"]
    assert database.query(InterviewEvaluationDB).first().evaluation_results == scores_before
