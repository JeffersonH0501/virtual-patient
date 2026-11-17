"""Multimodal evaluation prompts and category evidence policy.

The scoring prompt of each multimodal category IS the inherited text-only prompt
(Bayona) with one added block that describes the evidence and how to read it, so the
two conditions differ only in the evidence. The feedback comment is written by a second
call that does not score. See ``config/prompts/multimodal_evaluation_prompts``.

The constants below are structural configuration consumed by the conversation
formatter, the evaluation metadata endpoint and learning moments. They describe
which observable families apply to each category and how they are surfaced to
reviewers; they are not prompt text.
"""

from app.core.functional_config import render_prompt

from app.core.functional_config import load_prompt

from .evaluation_aspects import format_aspects_for_prompt, get_all_aspects
from .evaluation_prompts import get_show_empathy_prompt, get_show_interest_prompt, get_speak_clearly_prompt

POLICY_VERSION = "multimodal_categories_v7_text_prompt_plus_evidence_block"

OBSERVATION_NOTE = {
    "en": "Multimodal observations describe observable behavior and are used as complementary evidence. They are not direct measurements of psychological states or communication quality. Missing or unavailable evidence must not be penalized.",
    "es": "Las observaciones multimodales describen conductas observables y se usan como evidencia complementaria. No son medidas directas de estados psicológicos ni de calidad comunicativa. La evidencia ausente o no disponible no debe penalizarse.",
}

# Human-readable family names surfaced to reviewers and in evidence blocks.
_NAMES = {
    "gaze_orientation": "Visual orientation",
    "head_nods": "Head gestural feedback",
    "smile_activity": "Smile behavior",
    "speech_timing": "Temporal speech pattern",
    "prosodic_level": "Prosodic level",
    "prosodic_variability": "Prosodic modulation",
}

_VISUAL = ("gaze_orientation", "head_nods", "smile_activity")

# Per-category complementary-evidence descriptions shown in the evaluation
# metadata (UI and learning moments). These summarize, in plain language, the
# observable families each category may consider.
_EVIDENCE = {
    "show_interest": {
        "en": [
            "Visual orientation while the patient is speaking may be considered as complementary evidence of the doctor's observable listening behavior.",
            "Head nodding while the patient is speaking may be considered as complementary evidence of the doctor's observable listening behavior.",
            "Smile-related behavior while the patient is speaking may be considered as complementary information about how the doctor behaved during the interaction.",
        ],
        "es": [
            "Orientación visual mientras habla el paciente: evidencia complementaria de la conducta observable al escuchar.",
            "Asentimientos mientras habla el paciente: evidencia complementaria de la conducta observable al escuchar.",
            "Conducta de sonrisa mientras habla el paciente: información complementaria sobre la conducta durante la interacción; no demuestra interés por sí sola.",
        ],
    },
    "show_empathy": {
        "en": [
            "Visual orientation and head nodding while the patient is speaking, and smile-related behavior, may be considered as complementary evidence of observable listening behavior.",
            "Smile-related behavior may be considered as complementary information about how friendliness and interpersonal warmth were behaviorally expressed.",
            "Speech timing, prosodic level and prosodic modulation while the doctor is responding may be considered as complementary information about how responses were delivered, read against the emotional moment of the conversation.",
        ],
        "es": [
            "Orientación visual y asentimientos mientras habla el paciente: evidencia complementaria de la conducta observable al escuchar.",
            "Conducta de sonrisa al escuchar: información complementaria sobre la expresión conductual de amabilidad y calidez interpersonal.",
            "Patrón temporal del habla, nivel y modulación prosódica mientras habla el estudiante: información complementaria sobre cómo entregó sus respuestas, leída según el momento emocional de la conversación.",
        ],
    },
    "speak_clearly": {
        "en": [
            "Temporal speech patterns, including speaking rate and pauses, may be considered as complementary evidence of how clearly information was delivered.",
            "Pausing while providing information may be considered when assessing whether the delivery allowed sufficient space for the patient to assimilate information.",
            "Prosodic modulation and prosodic level may be considered as complementary evidence of how explanations, opinions, and recommendations were delivered.",
        ],
        "es": [
            "Patrones temporales del habla, incluida velocidad y pausas: evidencia complementaria de la entrega de información.",
            "Pausas durante las explicaciones: información complementaria sobre el espacio para asimilar lo explicado.",
            "Modulación y nivel prosódico mientras habla el estudiante: evidencia complementaria sobre cómo entregó explicaciones, opiniones y recomendaciones.",
        ],
    },
}


_TEXT_PROMPTS = {
    "show_interest": get_show_interest_prompt,
    "show_empathy": get_show_empathy_prompt,
    "speak_clearly": get_speak_clearly_prompt,
}
_EVIDENCE_ANCHOR = "\nInstructions:"


def _prompt_builder(category):
    def build(target_language: str = "English") -> str:
        """The text-only prompt with the evidence block inserted before its instructions."""
        text_prompt = _TEXT_PROMPTS[category](target_language)
        if text_prompt.count(_EVIDENCE_ANCHOR) != 1:
            raise ValueError(f"The text-only prompt of {category} must contain exactly one 'Instructions:' line")
        block = load_prompt(f"multimodal_evaluation_prompts/evidence_{category}").strip()
        return text_prompt.replace(_EVIDENCE_ANCHOR, f"\n{block}{_EVIDENCE_ANCHOR}", 1)

    return build


# What each category's feedback comment names; the rest of the comment prompt is shared.
_FEEDBACK_FOCUS = {
    "show_interest": {
        "category_title": "The doctor shows interest in the patient",
        "pattern_focus": "where the doctor looked while the patient spoke, nods and smiling",
        "moment_instruction": ("Name the specific moment (quote or closely paraphrase what the patient raised, such as an idea, "
                               "concern or need) and what the doctor said or did next, then give one example of a question or "
                               "sentence the doctor could have used there."),
    },
    "show_empathy": {
        "category_title": "The doctor shows understanding and empathy",
        "pattern_focus": ("where the doctor looked while the patient spoke, nods and smiling, and how the doctor's voice was "
                          "mostly delivered when responding: pace, pauses and variation"),
        "moment_instruction": ("Name the specific moment (quote or paraphrase the emotion the patient expressed and what the "
                               "doctor did next) and give one example of a sentence the doctor could have said there."),
    },
    "speak_clearly": {
        "category_title": "The doctor communicates clearly and completely",
        "pattern_focus": ("how the doctor mostly delivered explanations, opinions and recommendations: pace, pauses, loudness "
                          "and variation in intonation; judge it only in turns where the doctor explains"),
        "moment_instruction": ("Name the specific word, term or explanation involved (quote the doctor) and say what was missing, "
                               "then give one example of how to say it in plain words or check understanding."),
    },
}


def _feedback_prompt_builder(category):
    def build(target_language: str = "English") -> str:
        return render_prompt(
            "multimodal_evaluation_prompts/category_feedback",
            aspects_text=format_aspects_for_prompt(category),
            target_language=target_language,
            **_FEEDBACK_FOCUS[category],
        )

    return build


def get_multimodal_show_interest_prompt(target_language: str = "English") -> str:
    return _prompt_builder("show_interest")(target_language)


def get_multimodal_show_empathy_prompt(target_language: str = "English") -> str:
    return _prompt_builder("show_empathy")(target_language)


def get_multimodal_speak_clearly_prompt(target_language: str = "English") -> str:
    return _prompt_builder("speak_clearly")(target_language)


MULTIMODAL_EVALUATION_CONFIG = {
    "show_interest": {
        "nonverbal": _VISUAL, "nonverbal_speakers": ("patient",),
        "paraverbal": (), "family_display_names": _NAMES,
        "prompt": get_multimodal_show_interest_prompt,
        "feedback_prompt": _feedback_prompt_builder("show_interest"),
        "evidence": _EVIDENCE["show_interest"],
    },
    "show_empathy": {
        "nonverbal": _VISUAL, "nonverbal_speakers": ("patient", "student"),
        "paraverbal": ("speech_timing", "prosodic_level", "prosodic_variability"), "family_display_names": _NAMES,
        "prompt": get_multimodal_show_empathy_prompt,
        "feedback_prompt": _feedback_prompt_builder("show_empathy"),
        "evidence": _EVIDENCE["show_empathy"],
    },
    "speak_clearly": {
        "nonverbal": (), "nonverbal_speakers": (),
        "paraverbal": ("speech_timing", "prosodic_level", "prosodic_variability"), "family_display_names": _NAMES,
        "prompt": get_multimodal_speak_clearly_prompt,
        "feedback_prompt": _feedback_prompt_builder("speak_clearly"),
        "evidence": _EVIDENCE["speak_clearly"],
    },
}


def get_multimodal_metadata(language: str = "en") -> list[dict]:
    language = language if language in OBSERVATION_NOTE else "en"
    aspects = get_all_aspects(language)
    return [{
        "aspect": aspect, "criteria": aspects[aspect],
        "nonverbal_families": list(config["nonverbal"]),
        "paraverbal_families": list(config["paraverbal"]),
        "multimodal_evaluation_aspects": config["evidence"][language],
        "evidence": config["evidence"][language],
        "observation_note": OBSERVATION_NOTE[language],
    } for aspect, config in MULTIMODAL_EVALUATION_CONFIG.items()]
