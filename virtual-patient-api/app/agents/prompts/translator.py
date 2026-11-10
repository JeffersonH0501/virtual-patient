from app.core.functional_config import load_prompt

# Basic translation from language A to language B
BASIC_TRANSLATE_PROMPT = load_prompt("translator/basic_translate_prompt", "target_language", "message")

# Structured translation prompt (used for both ProgressSummarySchema and ClinicalCaseTranslatableFields)
STRUCTURED_TRANSLATE_PROMPT = load_prompt("translator/structured_translate_prompt", "target_language", "structured_data")