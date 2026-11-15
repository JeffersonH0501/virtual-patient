"""Per-category pedagogical generation after scoring; never a scoring prompt.

One prompt per multimodal category (interest, empathy, clarity) per type (improvement,
strength). Each prompt is run once for its category and type, and returns at most one
highly specific moment (or none). There is no global cap. The response language is
injected explicitly so feedback never defaults to English.
"""

from app.core.functional_config import render_prompt

PROMPT_VERSION = "learning_moments_v11_with_strengths"

_CATEGORY_FILES = {
    "show_interest": "multimodal_evaluation_prompts/learning_moment_show_interest",
    "show_empathy": "multimodal_evaluation_prompts/learning_moment_show_empathy",
    "speak_clearly": "multimodal_evaluation_prompts/learning_moment_speak_clearly",
}

_STRENGTH_FILES = {
    "show_interest": "multimodal_evaluation_prompts/strength_moment_show_interest",
    "show_empathy": "multimodal_evaluation_prompts/strength_moment_show_empathy",
    "speak_clearly": "multimodal_evaluation_prompts/strength_moment_speak_clearly",
}


def get_learning_moment_prompts(response_language: str = "English") -> dict:
    """Render each category improvement prompt in the requested response language."""
    return {category: render_prompt(path, response_language=response_language)
            for category, path in _CATEGORY_FILES.items()}


def get_strength_moment_prompts(response_language: str = "English") -> dict:
    """Render each category strength prompt in the requested response language."""
    return {category: render_prompt(path, response_language=response_language)
            for category, path in _STRENGTH_FILES.items()}
