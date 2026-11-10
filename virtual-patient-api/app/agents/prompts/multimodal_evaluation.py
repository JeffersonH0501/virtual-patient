"""Category evidence policy layered onto the unchanged inherited prompts."""

from app.core.functional_config import load_prompt, read_config_json


from .evaluation_aspects import get_all_aspects
from .evaluation_prompts import (
    get_show_interest_prompt, get_show_empathy_prompt, get_speak_clearly_prompt,
)

_CONTENT = read_config_json("prompts/multimodal_evaluation/evidence.json")

POLICY_VERSION = "multimodal_categories_v4_score_only"
OBSERVATION_NOTE = _CONTENT["OBSERVATION_NOTE"]

INTEREST_ASPECTS = tuple(_CONTENT["INTEREST_ASPECTS"])
EMPATHY_ASPECTS = tuple(_CONTENT["EMPATHY_ASPECTS"])
CLARITY_ASPECTS = tuple(_CONTENT["CLARITY_ASPECTS"])

INTERPRETATION_RULES = load_prompt("multimodal_evaluation/interpretation_rules")


def _extend_prompt(original, aspects, rules, target_language):
    evidence = "\n".join(f"- {item}" for item in aspects)
    return f"{original(target_language)}\nRelevant multimodal evidence:\n{evidence}\n{rules}\n{INTERPRETATION_RULES}"


def get_multimodal_show_interest_prompt(target_language: str = "English") -> str:
    return _extend_prompt(get_show_interest_prompt, INTEREST_ASPECTS,
        load_prompt("multimodal_evaluation/show_interest_rules"), target_language)


def get_multimodal_show_empathy_prompt(target_language: str = "English") -> str:
    return _extend_prompt(get_show_empathy_prompt, EMPATHY_ASPECTS,
        load_prompt("multimodal_evaluation/show_empathy_rules"), target_language)


def get_multimodal_speak_clearly_prompt(target_language: str = "English") -> str:
    return _extend_prompt(get_speak_clearly_prompt, CLARITY_ASPECTS,
        load_prompt("multimodal_evaluation/speak_clearly_rules"), target_language)


_VISUAL = ("gaze_orientation", "head_nods", "smile_activity")
_NAMES = _CONTENT["_NAMES"]

MULTIMODAL_EVALUATION_CONFIG = {
    "show_interest": {
        "nonverbal": _VISUAL, "nonverbal_speakers": ("patient", "student"),
        "paraverbal": (), "family_display_names": _NAMES,
        "prompt": get_multimodal_show_interest_prompt,
        "multimodal_evaluation_aspects": INTEREST_ASPECTS,
        "evidence": {
            "en": list(INTEREST_ASPECTS),
            "es": _CONTENT["evidence_es"]["INTEREST_ASPECTS"],
        },
    },
    "show_empathy": {
        "nonverbal": _VISUAL, "nonverbal_speakers": ("patient", "student"),
        "paraverbal": ("prosodic_level", "prosodic_variability"), "family_display_names": _NAMES,
        "prompt": get_multimodal_show_empathy_prompt,
        "multimodal_evaluation_aspects": EMPATHY_ASPECTS,
        "evidence": {
            "en": list(EMPATHY_ASPECTS),
            "es": _CONTENT["evidence_es"]["EMPATHY_ASPECTS"],
        },
    },
    "speak_clearly": {
        "nonverbal": (), "nonverbal_speakers": (),
        "paraverbal": ("speech_timing", "prosodic_variability"), "family_display_names": _NAMES,
        "prompt": get_multimodal_speak_clearly_prompt,
        "multimodal_evaluation_aspects": CLARITY_ASPECTS,
        "evidence": {
            "en": list(CLARITY_ASPECTS),
            "es": _CONTENT["evidence_es"]["CLARITY_ASPECTS"],
        },
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
