"""Six-category pairing, canonical transcript and evidence fallback contracts."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models
from app.agents.evaluation_agent import EvaluationAgent
from app.agents.prompts.evaluation_prompts import get_evaluation_prompts
from app.agents.prompts.multimodal_evaluation import MULTIMODAL_EVALUATION_CONFIG, get_multimodal_metadata
from app.agents.schemas.evaluation import EvaluationResult
from app.agents.schemas.multimodal_evaluation import MultimodalEvaluationResult
from app.controllers.interview_evaluation_controller import InterviewEvaluationController
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.models.medical_interview.interview_evaluation import InterviewEvaluationDB, InterviewEvaluationRunDB, InterviewEvaluationCreate, EvaluationCondition
from app.models.medical_interview.interview_recording import InterviewTurnDB, InterviewRecordingDB
from app.multimodal.conversation_formatter import MultimodalConversationFormatter
from app.multimodal.evaluation_service import EVALUATION_CATEGORY_ORDER, evaluate_and_store_multimodal


def labels():
    return {"quality": {"expected_frames": 10, "valid_gaze_frames": 10, "valid_smile_frames": 10, "valid_nod_predictions": 10}, "integrated_labels": {
        family: {"status": "ok", "value": value}
        for family, value in {
            "gaze_orientation": "interaction_gaze_inside",
            "head_nods": "nodding_present",
            "smile_activity": "moderate_smile_activity",
            "speech_timing": "high_pause_load",
            "prosodic_level": "typical_loudness",
            "prosodic_variability": "high_f0_variability",
        }.items()
    }, "raw": {"raw_secret": 10}, "processed": {"processed_secret": 20},
       "base_labels": {"base_secret": "value"}}


def turns():
    return [SimpleNamespace(id=f"turn-{index}", message_id=index,
                            speaker=speaker, transcript="NONCANONICAL TEXT",
                            start_ms=1000 - index, sequence=1000 - index,
                            nonverbal_features=labels(), paraverbal=labels())
            for index, speaker in [(1, "student"), (2, "patient")]]


MESSAGES = [
    {"id": 1, "role": "user", "content": 'What worries you?\nPlease tell me "everything".'},
    {"id": 2, "role": "assistant", "content": "I am afraid."},
    {"id": 3, "role": "user", "content": "A message without a captured turn."},
]


@pytest.mark.parametrize("aspect", list(MULTIMODAL_EVALUATION_CONFIG))
def test_original_prompt_is_preserved_as_exact_prefix(aspect):
    for language in ("English", "Spanish"):
        original = get_evaluation_prompts(language)[aspect]
        enriched = MULTIMODAL_EVALUATION_CONFIG[aspect]["prompt"](language)
        assert enriched.startswith(original)
        assert "Relevant multimodal evidence:" in enriched[len(original):]
        assert "Critical Turns" not in enriched and "Learning Moments" not in enriched
        assert "Missing or unavailable multimodal evidence must not be penalized" in enriched


def test_matched_control_preserves_text_and_ids_without_multimodal_labels():
    source = turns()
    for aspect in MULTIMODAL_EVALUATION_CONFIG:
        enriched = MultimodalConversationFormatter.format_messages(MESSAGES, source, aspect)
        matched = MultimodalConversationFormatter.format_messages(MESSAGES, source, aspect, include_evidence=False)
        assert matched.turn_ids == enriched.turn_ids
        assert matched.canonical_text == enriched.canonical_text
        assert not matched.has_valid_evidence
        assert matched.evidence_by_turn == {}


@pytest.mark.parametrize("aspect", list(MULTIMODAL_EVALUATION_CONFIG))
def test_transcript_is_identical_and_unmatched_messages_survive(aspect):
    formatted = MultimodalConversationFormatter.format_messages(MESSAGES, turns(), aspect)
    assert formatted.canonical_text == EvaluationAgent()._format_conversation(MESSAGES)
    assert "NONCANONICAL TEXT" not in formatted.text
    assert formatted.text.index("What worries you?") < formatted.text.index("I am afraid.")
    assert formatted.text.endswith("DOCTOR: A message without a captured turn.")
    assert formatted.turn_ids == {"turn-1", "turn-2"}
    assert formatted.has_valid_evidence
    for message in MESSAGES:
        assert message["content"] in formatted.text
    for forbidden in ("raw_secret", "processed_secret", "base_secret", "NONCANONICAL TEXT"):
        assert forbidden not in formatted.text


@pytest.mark.parametrize("aspect,patient_families,doctor_families", [
    ("show_interest", ["Visual orientation", "Head gestural feedback", "Smile behavior"],
     ["Visual orientation", "Head gestural feedback", "Smile behavior"]),
    ("show_empathy", ["Visual orientation", "Head gestural feedback", "Smile behavior"],
     ["Visual orientation", "Head gestural feedback", "Smile behavior", "Prosodic level", "Prosodic modulation"]),
    ("speak_clearly", [], ["Temporal speech pattern", "Prosodic modulation"]),
])
def test_evidence_allowlist_filters_by_category_and_speaker(aspect, patient_families, doctor_families):
    formatted = MultimodalConversationFormatter.format_messages(MESSAGES[:2], turns(), aspect)
    doctor, patient = formatted.text.split("\n\n", 1)
    names = ["Visual orientation", "Head gestural feedback", "Smile behavior", "Temporal speech pattern", "Prosodic level", "Prosodic modulation"]
    for name in names:
        assert (f"- {name}:" in doctor) == (name in doctor_families)
        assert (f"- {name}:" in patient) == (name in patient_families)
    assert "smile_activity" not in formatted.text
    assert "facial expression" not in formatted.text
    assert "smile_activity_ratio" not in formatted.text


@pytest.mark.parametrize("aspect", ["general_communication", "completeness", "open_communication"])
def test_textual_categories_cannot_enter_multimodal_formatter(aspect):
    assert aspect not in MULTIMODAL_EVALUATION_CONFIG
    with pytest.raises(KeyError):
        MultimodalConversationFormatter.format_messages(MESSAGES, turns(), aspect)


def test_mismatched_speaker_and_orphan_turn_do_not_supply_evidence_or_ids():
    items = turns()
    items[0].speaker = "patient"
    items[1].message_id = 99
    result = MultimodalConversationFormatter.format_messages(MESSAGES, items, "show_interest")
    assert result.text == EvaluationAgent()._format_conversation(MESSAGES)
    assert not result.turn_ids and not result.has_valid_evidence


@pytest.fixture
def database():
    engine = create_engine("sqlite://")
    for model in (InterviewEvaluationDB, InterviewEvaluationRunDB, InterviewTurnDB, InterviewRecordingDB):
        model.__table__.create(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def seed_control(db):
    controller = InterviewEvaluationController(db)
    original = controller.create_evaluation(7, InterviewEvaluationCreate(
        evaluation_results=[EvaluationResult(aspect=aspect, score=index / 2 + 2,
                                             feedback=f"Original {aspect}", timestamp="2026-10-13T10:00:00")
                            for index, aspect in enumerate(EVALUATION_CATEGORY_ORDER)],
        overall_score=3.2,
    ))
    recording = InterviewRecordingDB(id="recording-a", medical_interview_id=7,
                                     started_at=datetime(2026, 10, 13, tzinfo=timezone.utc),
                                     consent_policy_version="test-policy", capture_config={})
    db.add(recording)
    db.commit()
    return controller, original, recording


@pytest.mark.parametrize("available", [set(), {"show_interest"}, set(MULTIMODAL_EVALUATION_CONFIG)])
def test_six_results_exact_copy_fallback_average_and_regeneration(database, available):
    controller, original, recording = seed_control(database)
    snapshot = original.model_dump()
    conversations = {
        aspect: SimpleNamespace(has_valid_evidence=aspect in available, text="Enriched test conversation")
        for aspect in MULTIMODAL_EVALUATION_CONFIG
    }
    generated = [MultimodalEvaluationResult(aspect=aspect, score=4.75, feedback=f"Enriched {aspect}",
                 critical_turns=[{"turn_id": "turn-1", "annotation": "An observed problem."}])
                 for aspect in MULTIMODAL_EVALUATION_CONFIG if aspect in available]
    agent = SimpleNamespace(evaluate_multimodal=AsyncMock(return_value=generated))
    with patch.object(MultimodalConversationFormatter, "load", side_effect=lambda _, aspect, messages: conversations[aspect]):
        for _ in range(2):
            results = asyncio.run(evaluate_and_store_multimodal(database, 7, agent, canonical_messages=MESSAGES))
    assert len(results) == 6
    assert [result.aspect for result in results] == list(EVALUATION_CATEGORY_ORDER)
    stored = controller.get_evaluation_by_interview_id(7, EvaluationCondition.TEXT_PLUS_MULTIMODAL)
    assert stored.overall_score == controller.calculate_overall_score(results)
    assert stored.overall_score is not None
    for index, aspect in enumerate(EVALUATION_CATEGORY_ORDER):
        if aspect not in available:
            assert stored.evaluation_results[index].model_dump() == original.evaluation_results[index].model_dump()
            assert "critical_turns" not in stored.evaluation_results[index].model_dump()
        else:
            assert stored.evaluation_results[index].score == 4.75
            assert stored.evaluation_results[index].critical_turns[0].turn_id == "turn-1"
    assert controller.get_evaluation_by_interview_id(7).model_dump() == snapshot
    assert database.query(InterviewEvaluationDB).count() == 2
    runs = database.query(InterviewEvaluationRunDB).all()
    assert len(runs) == 2
    assert runs[0].snapshot["inputs"]["canonical_messages"] == MESSAGES
    assert runs[0].snapshot["inputs"]["text_only_control"]["evaluation_results"] == original.model_dump(mode="json")["evaluation_results"]
    if available:
        assert set(agent.evaluate_multimodal.await_args.args[0]) == available
    else:
        agent.evaluate_multimodal.assert_not_awaited()
    availability = recording.capture_config["evaluation_processing"]["evidence_availability"]
    for aspect in MULTIMODAL_EVALUATION_CONFIG:
        assert availability[aspect] == ("available" if aspect in available else "unavailable_text_fallback")


def test_no_turns_reuses_all_textual_results_without_any_llm_call(database):
    controller, original, _ = seed_control(database)
    agent = SimpleNamespace(evaluate_multimodal=AsyncMock())
    results = asyncio.run(evaluate_and_store_multimodal(database, 7, agent, canonical_messages=MESSAGES))
    assert [result.model_dump() for result in results] == [result.model_dump() for result in original.evaluation_results]
    agent.evaluate_multimodal.assert_not_awaited()
    assert controller.get_evaluation_by_interview_id(7, EvaluationCondition.TEXT_PLUS_MULTIMODAL).overall_score == 3.2


def test_incomplete_text_control_is_rejected_without_llm_or_multimodal_row(database):
    controller = InterviewEvaluationController(database)
    controller.create_evaluation(7, InterviewEvaluationCreate(evaluation_results=[EvaluationResult(aspect="show_interest", score=4, feedback="Test")]))
    agent = SimpleNamespace(evaluate_multimodal=AsyncMock())
    with pytest.raises(ValueError, match="six evaluation categories"):
        asyncio.run(evaluate_and_store_multimodal(database, 7, agent, canonical_messages=MESSAGES))
    agent.evaluate_multimodal.assert_not_awaited()
    assert database.query(InterviewEvaluationDB).count() == 1


def test_missing_llm_category_keeps_previous_multimodal_result(database):
    controller, _, _ = seed_control(database)
    old = controller.create_evaluation(7, InterviewEvaluationCreate(
        evaluation_condition=EvaluationCondition.TEXT_PLUS_MULTIMODAL,
        evaluation_results=[EvaluationResult(aspect=aspect, score=3, feedback="Old") for aspect in EVALUATION_CATEGORY_ORDER], overall_score=3))
    agent = SimpleNamespace(evaluate_multimodal=AsyncMock(return_value=[]))
    with patch.object(MultimodalConversationFormatter, "load", return_value=SimpleNamespace(has_valid_evidence=True)):
        with pytest.raises(ValueError, match="every available category"):
            asyncio.run(evaluate_and_store_multimodal(database, 7, agent, canonical_messages=MESSAGES))
    assert controller.get_evaluation_by_interview_id(7, EvaluationCondition.TEXT_PLUS_MULTIMODAL).model_dump() == old.model_dump()


def test_canonical_message_mapping_preserves_text_only_rendering():
    messages = [SimpleNamespace(id=entry["id"], content=entry["content"],
                               sender_type="user" if entry["role"] == "user" else "patient") for entry in MESSAGES]
    formatted = MedicalInterviewController(MagicMock()).format_messages_for_evaluation(messages)
    assert formatted == MESSAGES
    assert EvaluationAgent()._format_conversation(formatted) == EvaluationAgent()._format_conversation(MESSAGES)


def test_metadata_exposes_only_three_enriched_categories_with_original_criteria():
    for language in ("en", "es"):
        metadata = get_multimodal_metadata(language)
        assert [item["aspect"] for item in metadata] == list(MULTIMODAL_EVALUATION_CONFIG)
        assert [len(item["criteria"]) for item in metadata] == [4, 6, 4]
        assert all(item["multimodal_evaluation_aspects"] == item["evidence"] for item in metadata)


def test_real_agent_calls_only_three_enriched_categories_without_contextual_feedback():
    agent = EvaluationAgent()
    conversations = {aspect: MultimodalConversationFormatter.format_messages(MESSAGES, turns(), aspect)
                     for aspect in MULTIMODAL_EVALUATION_CONFIG}
    model = SimpleNamespace(ainvoke=AsyncMock(side_effect=[{
        "parsed": None,
        "raw": SimpleNamespace(tool_calls=[{"args": {
            "aspect": aspect, "score": 4, "feedback": f"Feedback {aspect}",
            "critical_turns": [{"turn_id": identifier, "annotation": "A contextual issue."}
                               for identifier in ("invented", "turn-1", "turn-1", "turn-2")],
        }}]),
    } for aspect in MULTIMODAL_EVALUATION_CONFIG]))
    agent.llm = MagicMock()
    agent.llm.with_structured_output.return_value = model
    results = asyncio.run(agent.evaluate_multimodal(conversations))
    assert [item.aspect for item in results] == list(MULTIMODAL_EVALUATION_CONFIG)
    assert model.ainvoke.await_count == 3
    for item, call in zip(results, model.ainvoke.await_args_list):
        assert "critical_turns" not in item.model_dump()
        assert conversations[item.aspect].text in call.args[0][1].content
    # No fallback call when all authorized evidence becomes unavailable.
    empty = {aspect: MultimodalConversationFormatter.format_messages(MESSAGES, [], aspect)
             for aspect in MULTIMODAL_EVALUATION_CONFIG}
    assert asyncio.run(agent.evaluate_multimodal(empty)) == []
    assert model.ainvoke.await_count == 3


def test_partial_valid_evidence_remains_available_but_unknown_or_invalid_labels_do_not():
    items = turns()
    items[0].nonverbal_features = None
    items[1].nonverbal_features = {"quality": labels()["quality"], "integrated_labels": {
        "gaze_orientation": {"status": "unavailable", "value": "scarce_gaze_orientation"},
        "head_nods": {"status": "ok", "value": "unknown"},
        "smile_activity": {"status": "ok", "value": "moderate_smile_activity"},
    }}
    result = MultimodalConversationFormatter.format_messages(MESSAGES, items, "show_interest")
    assert result.has_valid_evidence
    assert "scarce_gaze_orientation" not in result.text and "unknown" not in result.text
    assert "Smile activity was detected" in result.text
    assert "Visual orientation:" not in result.text
    assert "Head gestural feedback:" not in result.text


def test_regeneration_uses_current_textual_results_without_reevaluating_them(database):
    controller, _, _ = seed_control(database)
    agent = SimpleNamespace(evaluate_multimodal=AsyncMock())
    asyncio.run(evaluate_and_store_multimodal(database, 7, agent, canonical_messages=MESSAGES))
    control = controller.get_evaluation_by_interview_id(7)
    control.evaluation_results[0].score = 5
    control.evaluation_results[0].feedback = "Current textual feedback"
    current = controller.update_evaluation(7, InterviewEvaluationCreate(
        evaluation_results=control.evaluation_results,
        overall_score=controller.calculate_overall_score(control.evaluation_results)))
    asyncio.run(evaluate_and_store_multimodal(database, 7, agent, canonical_messages=MESSAGES))
    updated = controller.get_evaluation_by_interview_id(7, EvaluationCondition.TEXT_PLUS_MULTIMODAL)
    assert updated.evaluation_results[0].model_dump() == current.evaluation_results[0].model_dump()
    agent.evaluate_multimodal.assert_not_awaited()
