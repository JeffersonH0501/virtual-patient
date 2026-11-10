"""Targeted control compatibility, evidence boundaries and persistence tests."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # Register relationships before mapper configuration.
from app.agents.evaluation_agent import EvaluationAgent
from app.agents.prompts.evaluation_aspects import EVALUATION_ASPECTS
from app.agents.prompts.evaluation_prompts import get_evaluation_prompts
from app.agents.prompts.multimodal_evaluation import MULTIMODAL_EVALUATION_CONFIG, get_multimodal_metadata
from app.agents.schemas.evaluation import EvaluationResult
from app.agents.schemas.multimodal_evaluation import MultimodalEvaluationResult, validate_multimodal_result
from app.controllers.interview_evaluation_controller import InterviewEvaluationController
from app.models.medical_interview.interview_evaluation import InterviewEvaluationDB, InterviewEvaluationRunDB, InterviewEvaluationCreate, EvaluationCondition
from app.models.medical_interview.interview_recording import InterviewTurnDB
from app.models.medical_interview import MedicalInterviewDB
from app.models.medical_interview.interview_recording import InterviewRecordingDB
from app.multimodal.conversation_formatter import MultimodalConversationFormatter
from app.multimodal.config_loader import load_methodology_config
from app.multimodal.evaluation_service import evaluate_and_store_multimodal
from app.multimodal.label_glossary import LABEL_GLOSSARY


def turn(identifier="c12aba83-0d0b-47b9-b230-fb5c809f7eae", speaker="patient", start=0, **kwargs):
    return SimpleNamespace(id=identifier, message_id=kwargs.pop("message_id", start + 1), speaker=speaker, start_ms=start, sequence=start,
                           transcript="I am worried.", paraverbal=None, nonverbal_features=None, **kwargs)


def outcome(label, status="ok"):
    return {"value": label, "status": status, "evidence": {"secret_base_feature": 200}}


def format_turns(turns, aspect):
    messages = [{"id": item.message_id, "role": "user" if item.speaker == "student" else "assistant",
                 "content": item.transcript} for item in sorted(turns, key=lambda item: item.start_ms)]
    return MultimodalConversationFormatter.format_messages(messages, turns, aspect)


def test_registry_and_metadata_preserve_four_criteria():
    assert list(MULTIMODAL_EVALUATION_CONFIG) == ["show_interest", "show_empathy", "speak_clearly"]
    assert len(EVALUATION_ASPECTS["show_interest"]) == 4
    for language in ("en", "es"):
        metadata = get_multimodal_metadata(language)
        assert len(metadata) == 3
        assert len(metadata[0]["criteria"]) == 4
        assert metadata[0]["paraverbal_families"] == []
        assert metadata[0]["nonverbal_families"] == ["gaze_orientation", "head_nods", "smile_activity"]
        assert len(metadata[0]["evidence"]) == 3
    prompt = MULTIMODAL_EVALUATION_CONFIG["show_interest"]["prompt"]("Spanish")
    for criterion in EVALUATION_ASPECTS["show_interest"]:
        assert criterion in prompt
    assert "must not be penalized" in prompt
    assert "Do not infer interest, empathy, attention, emotion" in prompt
    assert "Spanish" in prompt
    assert "Prioritize these observations during patient-speaking turns" in prompt
    assert "Do not equate smiling with interest or empathy" in prompt
    assert "Smile behavior" in prompt
    assert "Prosodic" not in prompt and "Paraverbal" not in prompt


def test_glossary_covers_every_label_rule_including_temporal():
    config = load_methodology_config().label_rules
    for family in config["families"].values():
        for label in [family["fallback"], family["unavailable"], *[rule["value"] for rule in family["rules"]]]:
            assert label in LABEL_GLOSSARY
    for label, text in LABEL_GLOSSARY.items():
        if label.startswith("mixed_"):
            assert "no inherent negative meaning" in text


def test_formatter_filters_layers_and_student_voice_during_patient_turn():
    patient = turn()
    doctor = turn("0f4176f2-3317-4f83-bd16-76f178276948", "student", 20)
    for item in (patient, doctor):
        item.paraverbal = {"raw": {"secret_raw_feature": 42}, "processed": {"secret_processed": 45},
                           "base_labels": {"secret_base_label": "high"},
                           "integrated_labels": {"speech_timing": outcome("high_pause_load"),
                                                 "prosodic_level": outcome("typical_prosodic_level"),
                                                 "prosodic_variability": outcome("expressive_intonation")}}
        item.nonverbal_features = {"quality": {"expected_frames": 10, "valid_gaze_frames": 10, "valid_smile_frames": 10, "valid_nod_predictions": 10}, "integrated_labels": {"gaze_orientation": outcome("sustained_gaze_orientation"),
                                                       "head_nods": outcome("nodding_present"),
                                                       "smile_activity": outcome("moderate_smile_activity")}}
    formatted = format_turns([doctor, patient], "show_interest")
    patient_block, doctor_block = formatted.text.split("\n\n")
    assert patient_block.startswith(f"[TURN id={patient.id} speaker=PATIENT]")
    assert "DOCTOR BEHAVIOR WHILE LISTENING" in patient_block
    assert "prosodic" not in patient_block
    assert "DOCTOR BEHAVIOR WHILE SPEAKING" in doctor_block
    assert "Smile behavior: Smile activity was detected during a moderate proportion of the turn." in patient_block
    assert "prosodic" not in doctor_block and "intonation" not in doctor_block
    assert 'PATIENT: I am worried.' in patient_block
    assert 'DOCTOR: I am worried.' in doctor_block
    assert formatted.turn_ids == {doctor.id, patient.id}
    for excluded in ("secret_raw_feature", "secret_processed", "secret_base_label", "secret_base_feature", "high_pause_load", "typical_prosodic_level", "expressive_intonation", "threshold", "smile_activity", "smile_activity_ratio", "mean_smile_activation"):
        assert excluded not in formatted.text


def test_missing_invalid_and_unknown_evidence_are_unavailable():
    item = turn()
    item.nonverbal_features = {"quality": {"expected_frames": 10, "valid_gaze_frames": 10, "valid_smile_frames": 10, "valid_nod_predictions": 10}, "integrated_labels": {
        "gaze_orientation": outcome("scarce_gaze_orientation", "unavailable"),
        "head_nods": outcome("unknown_label"),
    }}
    formatted = format_turns([item], "show_interest")
    assert "DOCTOR BEHAVIOR" not in formatted.text
    assert formatted.evidence_by_turn == {}
    assert "scarce_gaze_orientation" not in formatted.text
    assert "unknown_label" not in formatted.text
    assert not formatted.has_valid_evidence


def test_critical_turns_filter_before_truncating_and_keep_real_ids():
    identifiers = frozenset({"turn-a", "turn-b", "turn-c", "turn-d"})
    payload = {"aspect": "invented", "score": 3.5, "feedback": "Test",
               "critical_turns": [{"turn_id": identifier, "annotation": "Observed issue"}
                                  for identifier in ["invented", "turn-a", "turn-a", "turn-b", "turn-c", "turn-d"]]}
    result = validate_multimodal_result(payload, "show_interest", identifiers)
    assert result.aspect == "show_interest"
    assert [entry.turn_id for entry in result.critical_turns] == ["turn-a", "turn-b", "turn-c"]
    assert len(MultimodalEvaluationResult.model_validate(payload).critical_turns) == 3
    assert MultimodalEvaluationResult(aspect="show_interest", score=5, feedback="Test").critical_turns == []


def test_original_agent_keeps_schema_prompts_and_results():
    agent = EvaluationAgent()
    assert agent.evaluation_prompts == get_evaluation_prompts("English", None)
    assert "critical_turns" not in EvaluationResult.model_fields
    categories = ["general_communication", "show_interest", "show_empathy", "speak_clearly", "open_communication"]
    results = [EvaluationResult(aspect=aspect, score=3.5, feedback=aspect) for aspect in categories]
    agent.structured_model = SimpleNamespace(ainvoke=AsyncMock(side_effect=results))
    actual = asyncio.run(agent.evaluate_multiple_aspects([{"role": "user", "content": "Hello"}], categories))
    assert actual == results
    for call, aspect in zip(agent.structured_model.ainvoke.await_args_list, categories):
        assert call.args[0][0].content == agent.evaluation_prompts[aspect]
        assert "DOCTOR: Hello" in call.args[0][1].content


def test_agent_runs_only_registry_aspect_and_keeps_scoring_separate_from_feedback():
    agent = EvaluationAgent()
    item = turn()
    item.nonverbal_features = {"quality": {"expected_frames": 10, "valid_gaze_frames": 10, "valid_smile_frames": 10, "valid_nod_predictions": 10}, "integrated_labels": {"gaze_orientation": outcome("sustained_gaze_orientation")}}
    conversation = format_turns([item], "show_interest")
    payload = {"aspect": "show_empathy", "score": 3.5, "feedback": "Test",
               "critical_turns": [{"turn_id": "invented", "annotation": "Test"},
                                  {"turn_id": item.id, "annotation": "Observed issue"}]}
    model = SimpleNamespace(ainvoke=AsyncMock(return_value={"parsed": None, "raw": SimpleNamespace(tool_calls=[{"args": payload}])}))
    agent.llm = MagicMock()
    agent.llm.with_structured_output.return_value = model
    result = asyncio.run(agent.evaluate_multimodal({"show_interest": conversation}))
    assert len(result) == 1 and result[0].aspect == "show_interest"
    assert result[0].score == 3.5 and result[0].feedback == "Test"
    assert "critical_turns" not in result[0].model_dump()
    agent.llm.with_structured_output.assert_called_once_with(
        EvaluationResult, method="function_calling", include_raw=True,
    )
    assert model.ainvoke.await_count == 1
    human_message = model.ainvoke.await_args.args[0][1].content
    assert conversation.text in human_message
    assert item.id in human_message
    assert "Smile behavior:" not in human_message
    assert "smile_activity" not in human_message
    assert "prosodic" not in human_message


@pytest.fixture
def database():
    engine = create_engine("sqlite://")
    InterviewEvaluationDB.__table__.create(engine)
    InterviewEvaluationRunDB.__table__.create(engine)
    InterviewTurnDB.__table__.create(engine)
    MedicalInterviewDB.__table__.create(engine)
    InterviewRecordingDB.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_two_conditions_coexist_and_multimodal_update_preserves_control(database):
    interview = MedicalInterviewDB(id=7, user_id=1, clinical_case_id=1)
    database.add(interview)
    database.commit()
    controller = InterviewEvaluationController(database)
    original = controller.create_evaluation(7, InterviewEvaluationCreate(
        evaluation_results=[EvaluationResult(aspect=aspect, score=4, feedback=f"Original {aspect}")
                            for aspect in ("general_communication", "completeness", "show_interest", "show_empathy", "speak_clearly", "open_communication")], overall_score=4))
    item = InterviewTurnDB(id="turn-a", message_id=1, medical_interview_id=7, speaker="patient", sequence=0,
                           start_ms=0, end_ms=20, transcript="Test", input_source="tts",
                           timing_source="playback", timing_quality="measured")
    item.nonverbal_features = {"quality": {"expected_frames": 10, "valid_gaze_frames": 10, "valid_smile_frames": 10, "valid_nod_predictions": 10}, "integrated_labels": {"gaze_orientation": outcome("sustained_gaze_orientation")}}
    database.add(item)
    database.commit()
    result = MultimodalEvaluationResult(aspect="show_interest", score=3.5, feedback="Multimodal",
                                      critical_turns=[{"turn_id": "turn-a", "annotation": "Observed issue"}])
    empathy = MultimodalEvaluationResult(aspect="show_empathy", score=4, feedback="Empathy", critical_turns=[])
    agent = SimpleNamespace(evaluate_multimodal=AsyncMock(return_value=[result, empathy]))
    messages = [{"id": 1, "role": "assistant", "content": "Test"}]
    asyncio.run(evaluate_and_store_multimodal(database, 7, agent, canonical_messages=messages))
    result.score = 3
    asyncio.run(evaluate_and_store_multimodal(database, 7, agent, canonical_messages=messages))
    assert database.query(InterviewEvaluationDB).count() == 2
    assert controller.get_evaluation_by_interview_id(7).model_dump() == original.model_dump()
    stored = controller.get_evaluation_by_interview_id(7, EvaluationCondition.TEXT_PLUS_MULTIMODAL)
    assert len(stored.evaluation_results) == 6
    assert stored.evaluation_results[2].score == 3
    assert stored.evaluation_results[2].critical_turns[0].turn_id == "turn-a"
    assert stored.overall_score == 3.8
    database.expire_all()
    assert interview.interview_evaluation.evaluation_condition == "TEXT_ONLY"
    assert interview.multimodal_interview_evaluation.evaluation_condition == "TEXT_PLUS_MULTIMODAL"
    assert len(interview.interview_evaluations) == 2
    assert "critical_turns" not in original.evaluation_results[0].model_dump()
    with pytest.raises(IntegrityError):
        controller.create_evaluation(7, InterviewEvaluationCreate(evaluation_results=[], overall_score=0))
    database.rollback()


def test_regeneration_keeps_stored_text_only_control():
    import sys
    import app.multimodal.reprocess as module
    import app.routers.medical_interviews as routes
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        user=SimpleNamespace(preferred_language="es"), patient_gender="female")
    controller = MagicMock()
    controller.get_interview_evaluation_data.return_value = {"messages": []}
    evaluation_controller = MagicMock()
    evaluation_controller.get_evaluation_by_interview_id.return_value = object()
    agent = MagicMock()
    agent.evaluate_all_aspects = AsyncMock()
    pipeline = SimpleNamespace(process_multimodal_interview=AsyncMock())
    multimodal = AsyncMock(return_value=[object()])
    with patch.dict(sys.modules, {"app.multimodal.pipeline": pipeline}), patch.object(module, "SessionLocal", return_value=db), patch.object(module, "EvaluationAgent", return_value=agent), patch.object(module, "_set_evaluation_status") as status, patch.object(routes, "_wait_for_multimodal_analysis", new=AsyncMock(return_value="complete")), patch.object(module, "evaluate_and_store_multimodal", new=multimodal):
        asyncio.run(module.reprocess_interview_evaluation(7, "recording-id"))
    agent.evaluate_all_aspects.assert_not_awaited()
    pipeline.process_multimodal_interview.assert_not_awaited()
    evaluation_controller.update_evaluation.assert_not_called()
    evaluation_controller.create_evaluation.assert_not_called()
    multimodal.assert_awaited_once_with(db, 7, agent)
    assert status.call_args.args[-1] == "complete"


def test_observation_refresh_evaluates_only_after_extraction():
    import sys
    import app.multimodal.reprocess as module
    pipeline = SimpleNamespace(process_multimodal_interview_isolated=AsyncMock())
    db = MagicMock()
    db.__enter__.return_value = db
    db.get.return_value.capture_config = {"observation_processing": {"status": "complete"}}
    async def evaluate_after_extraction(*_):
        pipeline.process_multimodal_interview_isolated.assert_awaited_once_with(7, "recording-id", use_full_video=True)
    with patch.dict(sys.modules, {"app.multimodal.process_isolation": pipeline}), patch.object(module, "SessionLocal", return_value=db), patch.object(module, "reprocess_interview_evaluation", new=AsyncMock(side_effect=evaluate_after_extraction)) as evaluate:
        asyncio.run(module.reprocess_interview_observations(7, "recording-id"))
    pipeline.process_multimodal_interview_isolated.assert_awaited_once_with(7, "recording-id", use_full_video=True)
    evaluate.assert_awaited_once_with(7, "recording-id")


def test_completion_waits_then_persists_separate_multimodal_result():
    import app.routers.medical_interviews as routes
    events = []
    db = MagicMock()
    controller = MagicMock()
    controller.get_interview_evaluation_data.return_value = {"messages": [], "clinical_case": None, "progress_summary": None}
    controller.format_messages_for_evaluation.return_value = [{"role": "user", "content": "Original"}]
    controller.complete_interview.side_effect = lambda *_: events.append("complete")
    agent = MagicMock()
    async def text(**kwargs):
        events.append("text")
        assert kwargs["conversation_messages"] == [{"role": "user", "content": "Original"}]
        assert len(kwargs["aspects"]) == 6 and "completeness" in kwargs["aspects"]
        return [EvaluationResult(aspect=aspect, score=4, feedback="Original") for aspect in kwargs["aspects"]]
    async def wait(*_):
        events.append("wait")
        return "partial"
    async def multimodal(*_, **kwargs):
        assert kwargs["canonical_messages"] == [{"role": "user", "content": "Original"}]
        events.append("multimodal")
    agent.evaluate_all_aspects = text
    evaluation_controller = MagicMock()
    evaluation_controller.get_evaluation_by_interview_id.return_value = None
    evaluation_controller.calculate_overall_score.return_value = 4
    with patch.object(routes, "_ensure_final_summary", new=AsyncMock(return_value=SimpleNamespace(summary_text="Final canonical summary"))), patch.object(routes, "SessionLocal", return_value=db), patch.object(routes, "MedicalInterviewController", return_value=controller), patch.object(routes, "EvaluationAgent", return_value=agent), patch.object(routes, "InterviewEvaluationController", return_value=evaluation_controller), patch.object(routes, "_wait_for_multimodal_analysis", side_effect=wait), patch.object(routes, "evaluate_and_store_multimodal", side_effect=multimodal):
        asyncio.run(routes._evaluate_and_complete_interview(7, "en", None))
    assert events == ["text", "wait", "multimodal", "complete"]
    assert evaluation_controller.create_evaluation.call_args.args[1].evaluation_condition == EvaluationCondition.TEXT_ONLY
