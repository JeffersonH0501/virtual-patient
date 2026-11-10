"""Pedagogical generation after scoring; never a scoring prompt."""

from app.core.functional_config import load_prompt

PROMPT_VERSION = "learning_moments_v3"
PROMPT = load_prompt("learning_moments/prompt")
