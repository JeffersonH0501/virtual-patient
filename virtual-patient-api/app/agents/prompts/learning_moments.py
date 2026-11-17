"""Per-category pedagogical generation after scoring; never a scoring prompt.

One prompt per multimodal category (interest, empathy, clarity). Each prompt is run
once for its category and returns at most one highly specific improvement moment (or
none), centered on how the student delivered one part of the interview. There is no
global cap. The response language is injected explicitly so feedback never defaults
to English.
"""

from app.core.functional_config import render_prompt

PROMPT_VERSION = "learning_moments_v21_balanced"

_CATEGORY_FILES = {
    "show_interest": "multimodal_evaluation_prompts/learning_moment_show_interest",
    "show_empathy": "multimodal_evaluation_prompts/learning_moment_show_empathy",
    "speak_clearly": "multimodal_evaluation_prompts/learning_moment_speak_clearly",
}


def get_learning_moment_prompts(response_language: str = "English") -> dict:
    """Render each category improvement prompt in the requested response language."""
    return {category: render_prompt(path, response_language=response_language)
            for category, path in _CATEGORY_FILES.items()}
