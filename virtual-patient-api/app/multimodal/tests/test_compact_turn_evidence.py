"""The per-turn evidence sent to the evaluator is compact, consistent and traceable."""
import asyncio
import copy
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.models  # Register relationships before mapper configuration.
from app.agents.evaluation_agent import EvaluationAgent
from app.agents.prompts.multimodal_evaluation import MULTIMODAL_EVALUATION_CONFIG
from app.agents.schemas.evaluation import EvaluationResult
from app.multimodal.config_loader import load_methodology_config
from app.multimodal.conversation_formatter import MultimodalConversationFormatter, analysed_window_seconds
from app.multimodal.evidence_text import render_family_evidence
from app.multimodal.label_engine import integrate_nonverbal_labels, integrate_paraverbal_labels
from app.multimodal.label_glossary import LABEL_GLOSSARY
from app.multimodal.learning_moments import build_category_message
from app.multimodal.schemas import NonverbalProcessedFeatures, ParaverbalProcessedFeatures
from app.multimodal.threshold_engine import compute_nonverbal_base_labels, compute_paraverbal_base_labels

CONFIG = load_methodology_config()
FULL_VISUAL_QUALITY = {"evaluable_gaze_ms": 10_000, "evaluable_smile_ms": 10_000, "nod_evaluable_ms": 10_000, "nod_eligible_ms": 10_000}


def nonverbal_payload(raw=None, **processed):
    """A stored nonverbal payload whose labels come from the real threshold and label engines."""
    features = NonverbalProcessedFeatures(**processed)
    base = compute_nonverbal_base_labels(features, CONFIG, baseline_available=True, session_refs=None)
    integrated = integrate_nonverbal_labels(base, CONFIG).model_dump(mode="json")
    return {"processed": features.model_dump(), "integrated_labels": integrated,
            "raw": {"turn_duration_ms": 10_000, **(raw or {})}, "quality": dict(FULL_VISUAL_QUALITY)}


def paraverbal_payload(issues=(), **processed):
    features = ParaverbalProcessedFeatures(**processed)
    base = compute_paraverbal_base_labels(features, CONFIG, baseline_available=True, session_refs=None)
    integrated = integrate_paraverbal_labels(base, CONFIG).model_dump(mode="json")
    return {"processed": features.model_dump(), "integrated_labels": integrated, "quality": {"issues": list(issues)}}


def stored_turn(speaker, start_ms, end_ms, *, quality="measured", source=None, number=0, **payloads):
    default_source = {"student": "turn_media", "patient": "tts_playback"}[speaker]
    return SimpleNamespace(
        id=f"00000000-0000-4000-8000-{number:012d}", message_id=number + 1, speaker=speaker, sequence=number,
        start_ms=start_ms, end_ms=end_ms, timing_quality=quality, timing_source=source or default_source,
        transcript="Original text.", paraverbal=payloads.get("paraverbal"), nonverbal_features=payloads.get("nonverbal"))


def messages_for(turns):
    ordered = sorted(turns, key=lambda item: item.sequence)
    return [{"id": item.message_id, "role": "user" if item.speaker == "student" else "assistant",
             "content": f"{'DOCTOR' if item.speaker == 'student' else 'PATIENT'} wording {item.sequence}"} for item in ordered]


def interview():
    """One patient reply (listened to for 8.6 s) and the doctor's answer (13.3 s)."""
    return [
        stored_turn("patient", 1_000, 9_600, number=0, nonverbal=nonverbal_payload(
            interaction_gaze_ratio=0.974, nod_count=1, smile_activity_ratio=0.2, mean_smile_activation=0.3, context="listening")),
        stored_turn("student", 12_000, 25_300, number=1,
                    nonverbal=nonverbal_payload(interaction_gaze_ratio=0.763, nod_count=3, smile_activity_ratio=0.004, context="speaking"),
                    paraverbal=paraverbal_payload(speech_rate_wpm=152.7, articulation_rate_wpm=190, pause_count=0, pause_time_ratio=0.0,
                                                  pause_frequency_per_min=0.0, f0_p20_p80_range_semitones=2.96)),
    ]


def render(turns, category):
    return MultimodalConversationFormatter.format_messages(messages_for(turns), turns, category)


# ---- duration -----------------------------------------------------------------------------------------------

def test_a_measured_window_gives_the_verifiable_duration_of_each_speaker():
    assert analysed_window_seconds(stored_turn("patient", 1_000, 9_600)) == 8.6
    assert analysed_window_seconds(stored_turn("student", 12_000, 25_300)) == 13.3


@pytest.mark.parametrize("turn", [
    stored_turn("patient", 1_000, 9_600, quality="provisional"),
    stored_turn("patient", 1_000, 9_600, quality="unavailable"),
    stored_turn("patient", 1_000, 9_600, source="tts_written"),
    stored_turn("student", 1_000, 9_600, source="tts_playback"),
    stored_turn("student", 5_000, 5_000),
    stored_turn("student", 6_000, 5_000),
    SimpleNamespace(speaker="student", start_ms=None, end_ms=None, timing_quality="measured", timing_source="turn_media"),
])
def test_an_unverified_or_unusable_window_has_no_duration(turn):
    assert analysed_window_seconds(turn) is None


def test_the_header_states_the_duration_once_and_the_family_lines_do_not_repeat_it():
    text = render(interview(), "show_empathy").text
    assert "[TURN T1 speaker=PATIENT duration=8.6s]" in text
    assert "[TURN T2 speaker=DOCTOR duration=13.3s]" in text
    assert len(re.findall(r"duration=", text)) == 2
    for repeated in ("second turn", "evaluable visual time", "evaluable facial time", "of the speech window"):
        assert repeated not in text


def test_a_turn_without_a_verified_window_keeps_its_original_header():
    turns = interview()
    turns[0].timing_quality = "provisional"
    turns[1].timing_source = "tts_written"
    text = render(turns, "show_empathy").text
    assert "[TURN T1 speaker=PATIENT]" in text and "[TURN T2 speaker=DOCTOR]" in text
    assert "duration=" not in text
    assert "completion was not confirmed" in text


# ---- category filtering --------------------------------------------------------------------------------------

def test_each_category_reads_only_the_turns_it_is_authorised_for():
    turns = interview()
    interest, empathy, clarity = (render(turns, aspect) for aspect in ("show_interest", "show_empathy", "speak_clearly"))
    # Interest: only the doctor listening. No evidence, and therefore no duration, for the doctor's own speech.
    assert "[TURN T1 speaker=PATIENT duration=8.6s]" in interest.text and "[TURN T2 speaker=DOCTOR]" in interest.text
    assert set(interest.evidence_by_turn) == {"T1"}
    assert set(interest.evidence_by_turn["T1"]) == {"gaze_orientation", "head_nods", "smile_activity"}
    # Clarity: only the doctor speaking, and only the vocal families.
    assert "[TURN T1 speaker=PATIENT]" in clarity.text and "[TURN T2 speaker=DOCTOR duration=13.3s]" in clarity.text
    assert set(clarity.evidence_by_turn) == {"T2"}
    assert set(clarity.evidence_by_turn["T2"]) <= {"speech_timing", "prosodic_level", "prosodic_variability"}
    assert "Visual orientation" not in clarity.text and "Head gestural" not in clarity.text
    # Empathy: both roles, kept apart by their headings.
    assert set(empathy.evidence_by_turn) == {"T1", "T2"}
    assert empathy.text.index("WHILE LISTENING") < empathy.text.index("[TURN T2") < empathy.text.index("WHILE SPEAKING")
    assert "Temporal speech pattern" not in empathy.text.split("[TURN T2")[0]


def test_only_the_three_enriched_categories_use_this_representation():
    assert list(MULTIMODAL_EVALUATION_CONFIG) == ["show_interest", "show_empathy", "speak_clearly"]


# ---- compact wording ------------------------------------------------------------------------------------------

def test_the_interview_example_is_compact_and_has_no_spurious_precision():
    text = render(interview(), "show_empathy").text
    assert "Gaze mostly toward the interaction area or calibrated camera (97% of the analysed time)." in text
    assert "1 head nod detected." in text and "3 head nods detected." in text
    assert LABEL_GLOSSARY["scarce_smile_activity"] in text
    assert not re.search(r"\d+\.\d+%", text)
    assert "words per minute" not in text
    # No pause counters when there were none: the label already says so.
    assert "0 internal pauses" not in text and "0.0%" not in text


@pytest.mark.parametrize("ratio, expected", [(0.0, "0%"), (0.004, "<1%"), (0.0149, "1%"), (0.156, "16%"), (0.994, "99%"), (0.996, "100%")])
def test_percentages_are_whole_numbers_and_a_trace_is_not_zero(ratio, expected):
    text = render_family_evidence(nonverbal_payload(interaction_gaze_ratio=ratio), "gaze_orientation")
    assert f"({expected} " in text


def test_pauses_keep_only_their_nonzero_count():
    payload = paraverbal_payload(speech_rate_wpm=140, articulation_rate_wpm=190, pause_count=4, total_pause_duration_ms=3500,
                                 median_pause_duration_ms=700, pause_frequency_per_min=12, pause_time_ratio=0.351)
    text = render_family_evidence(payload, "speech_timing")
    assert text == LABEL_GLOSSARY[payload["integrated_labels"]["speech_timing"]["value"]] + " 4 internal pauses of at least 500 ms."
    payload["processed"]["pause_count"] = 1
    assert "1 internal pause of at least 500 ms" in render_family_evidence(payload, "speech_timing")


def test_closed_eyes_are_reported_only_when_they_matter():
    def gaze(seconds):
        closed = int(seconds * 10)
        samples = ([{"timestamp_ms": 0, "state": "INSIDE"}]
                   + [{"timestamp_ms": 100 * (step + 1), "state": "OUTSIDE", "reason": "eyes_closed"} for step in range(closed)]
                   + [{"timestamp_ms": 100 * (closed + 1), "state": "INSIDE"}])
        return nonverbal_payload(interaction_gaze_ratio=0.6, raw={"sample_fps": 10, "extractor": {"window_end_ms": 100 * (closed + 2)},
                                                              "gaze_semantic_observations": samples})
    assert "closed eyes" not in render_family_evidence(gaze(0.2), "gaze_orientation")
    assert "closed eyes" not in render_family_evidence(gaze(0.4), "gaze_orientation")
    for seconds in (0.5, 1.0):
        text = render_family_evidence(gaze(seconds), "gaze_orientation")
        assert text.split("The time away includes", 1)[1] == " closed eyes."


def test_vocal_levels_and_modulation_carry_no_raw_numbers_the_reader_cannot_calibrate():
    payload = paraverbal_payload(f0_p20_p80_range_semitones=9.0, median_loudness=0.93, loudness_p20_p80_range=0.91)
    for family in ("prosodic_level", "prosodic_variability"):
        text = render_family_evidence(payload, family)
        if text is not None:
            assert not re.search(r"\d", text), text


def test_no_description_presents_a_relative_band_as_a_standard():
    for label, description in LABEL_GLOSSARY.items():
        assert not re.search(r"\bP\d{2}\b|provisional bands|defined typical ranges|norm\b|standard", description), (label, description)
    for label in ("elevated_loudness", "reduced_loudness", "typical_loudness"):
        assert "this student's other analysed turns" in LABEL_GLOSSARY[label]


# ---- labels agree with the measurements -----------------------------------------------------------------------

@pytest.mark.parametrize("ratio", [0.0, 0.1, 0.49, 0.5, 0.51, 0.9, 1.0])
def test_the_gaze_wording_follows_the_threshold_that_produced_the_label(ratio):
    payload = nonverbal_payload(interaction_gaze_ratio=ratio)
    cutoff = CONFIG.thresholds["nonverbal"]["gaze_orientation"]["interaction_gaze_ratio"]["threshold"]
    text = render_family_evidence(payload, "gaze_orientation")
    assert text.startswith("Gaze mostly toward" if ratio >= cutoff else "Gaze mostly away from")


@pytest.mark.parametrize("ratio", [0.004, 0.05, 0.10, 0.11, 0.2, 0.35, 0.36, 0.9])
def test_the_smile_wording_follows_the_label_the_engine_produced_from_the_ratio(ratio):
    payload = nonverbal_payload(smile_activity_ratio=ratio, mean_smile_activation=0.3)
    label = payload["integrated_labels"]["smile_activity"]["value"]
    text = render_family_evidence(payload, "smile_activity")
    assert text.startswith(LABEL_GLOSSARY[label].rstrip("."))
    assert text == LABEL_GLOSSARY[label]
    assert "%" not in text


def test_the_smile_bands_in_the_wording_are_the_configured_ones():
    assert CONFIG.thresholds["nonverbal"]["smile_activity"]["smile_activity_ratio"]["breaks"] == [0.0, 0.10, 0.35]


@pytest.mark.parametrize("processed", [
    {"speech_rate_wpm": 200, "articulation_rate_wpm": 230, "pause_count": 0, "pause_frequency_per_min": 0, "pause_time_ratio": 0},
    {"speech_rate_wpm": 90, "articulation_rate_wpm": 120, "pause_count": 0, "pause_frequency_per_min": 0, "pause_time_ratio": 0},
    {"speech_rate_wpm": 140, "articulation_rate_wpm": 190, "pause_count": 0, "pause_frequency_per_min": 0, "pause_time_ratio": 0},
    {"speech_rate_wpm": 140, "articulation_rate_wpm": 190, "pause_count": 6, "total_pause_duration_ms": 4000, "median_pause_duration_ms": 700,
     "pause_frequency_per_min": 20, "pause_time_ratio": 0.4},
])
def test_the_speech_timing_text_keeps_the_engine_description_and_only_nonzero_pause_counts(processed):
    payload = paraverbal_payload(**processed)
    label = payload["integrated_labels"]["speech_timing"]["value"]
    text = render_family_evidence(payload, "speech_timing")
    assert text.startswith(LABEL_GLOSSARY[label])
    assert "words per minute" not in text and "median pause" not in text and "%" not in text
    if processed["pause_count"]:
        assert f"{processed['pause_count']} internal pauses" in text
    else:
        assert text == LABEL_GLOSSARY[label]


@pytest.mark.parametrize("semitones, phrase", [(2.0, "varied little"), (9.0, "varied widely")])
def test_the_intonation_wording_follows_the_configured_f0_bands(semitones, phrase):
    bands = CONFIG.thresholds["paraverbal"]["prosodic_variability"]["f0_p20_p80_range_semitones"]
    assert bands["low_below"] < 4.5 and bands["high_above"] < 9.5
    assert phrase in render_family_evidence(paraverbal_payload(f0_p20_p80_range_semitones=semitones), "prosodic_variability")


# ---- integrity and traceability -------------------------------------------------------------------------------

def test_text_order_and_identifiers_are_preserved_and_the_persisted_metrics_are_not_touched():
    turns = interview()
    before = copy.deepcopy([(item.paraverbal, item.nonverbal_features) for item in turns])
    messages = messages_for(turns)
    for aspect in MULTIMODAL_EVALUATION_CONFIG:
        formatted = MultimodalConversationFormatter.format_messages(messages, turns, aspect)
        assert formatted.canonical_text == "\n\n".join(f"{'DOCTOR' if m['role'] == 'user' else 'PATIENT'}: {m['content']}" for m in messages)
        positions = [formatted.text.index(m["content"]) for m in messages]
        assert positions == sorted(positions)
        assert formatted.alias_to_turn_id == {"T1": turns[0].id, "T2": turns[1].id}
        assert "DOCTOR wording 1" in formatted.text and "PATIENT wording 0" in formatted.text
        for turn in turns:
            assert turn.id not in formatted.text
    assert before == [(item.paraverbal, item.nonverbal_features) for item in turns]


def test_only_gaze_evidence_contains_a_percentage_in_each_category_conversation():
    for aspect in MULTIMODAL_EVALUATION_CONFIG:
        conversation = render(interview(), aspect)
        assert not any(term in conversation.text for term in ("words per minute", "median pause", "pauses took"))
        for evidence in conversation.evidence_by_turn.values():
            for family, text in evidence.items():
                if family == "gaze_orientation":
                    assert "%" in text
                else:
                    assert "%" not in text


def test_absent_behaviors_and_unavailable_families_are_not_rendered_as_evidence():
    quiet = nonverbal_payload(interaction_gaze_ratio=0.9, nod_count=0, smile_activity_ratio=0.0, mean_smile_activation=0.0)
    assert render_family_evidence(quiet, "head_nods") is None and render_family_evidence(quiet, "smile_activity") is None
    quiet["quality"] = {"evaluable_gaze_ms": 100}
    assert render_family_evidence(quiet, "gaze_orientation") is None


def test_a_missing_measurement_falls_back_to_the_description_of_the_label():
    payload = nonverbal_payload(interaction_gaze_ratio=0.9)
    payload["processed"]["interaction_gaze_ratio"] = None
    assert render_family_evidence(payload, "gaze_orientation") == LABEL_GLOSSARY["interaction_gaze_inside"]


# ---- the same representation reaches every call ---------------------------------------------------------------

def test_scoring_and_comment_calls_receive_the_same_compact_conversation():
    turns = interview()
    conversation = render(turns, "show_empathy")
    agent = EvaluationAgent()
    scoring = SimpleNamespace(ainvoke=AsyncMock(return_value=EvaluationResult(aspect="show_empathy", score=3.5, feedback="Short")))
    commenting = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(feedback="Comment")))
    agent.structured_model = scoring
    agent.llm = MagicMock()
    agent.llm.with_structured_output.return_value = commenting
    asyncio.run(agent.evaluate_multimodal({"show_empathy": conversation}))
    scoring_message = scoring.ainvoke.await_args.args[0][1].content
    comment_message = commenting.ainvoke.await_args.args[0][1].content
    for message in (scoring_message, comment_message):
        assert conversation.text in message
        assert "[TURN T2 speaker=DOCTOR duration=13.3s]" in message
    # The evidence block of the prompt explains the header and warns that bands are not norms.
    system_prompt = scoring.ainvoke.await_args.args[0][0].content
    assert "duration=" in system_prompt and "clinical norm" in system_prompt


def test_learning_moments_see_the_same_transcript_and_still_cite_families_by_key():
    turns = interview()
    conversations = {aspect: render(turns, aspect) for aspect in MULTIMODAL_EVALUATION_CONFIG}
    context = {"response_language": "English", "alias_to_turn_id": conversations["show_empathy"].alias_to_turn_id,
               "transcripts": {aspect: item.text for aspect, item in conversations.items()},
               "evidence": {aspect: item.evidence_by_turn for aspect, item in conversations.items()},
               "criteria": {aspect: ["Criterion"] for aspect in conversations},
               "evaluations": {aspect: {"score": 3, "feedback": "f"} for aspect in conversations}}
    message = build_category_message(context, "show_empathy")
    assert "[TURN T2 speaker=DOCTOR duration=13.3s]" in message
    assert re.search(r"T1: .*gaze_orientation", message) and re.search(r"T2: .*speech_timing", message)
    assert "turn-" not in message and turns[0].id not in message


@pytest.mark.parametrize("category", ["show_interest", "show_empathy", "speak_clearly"])
def test_every_evidence_block_explains_the_header_and_that_bands_are_not_norms(category):
    prompt = MULTIMODAL_EVALUATION_CONFIG[category]["prompt"]("English")
    assert "duration=" in prompt and "clinical norm" in prompt
    assert "must NOT be penalized" in prompt
