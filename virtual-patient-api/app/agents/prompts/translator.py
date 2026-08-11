# Basic translation from language A to language B
BASIC_TRANSLATE_PROMPT = """You are a {target_language} translator. Translate the following message into {target_language}.

Rules:
    1. Only translate the text thats written after 'Message:' and nothing else
    2. If already in {target_language}, return as-is
    3. Use natural, fluent language
    4. Preserve the original meaning and tone
    5. Maintain medical accuracy

Message:
{message}
"""

# Structured translation prompt (used for both ProgressSummarySchema and ClinicalCaseTranslatableFields)
STRUCTURED_TRANSLATE_PROMPT = """You are a medical translator specializing in structured medical data. Translate the following structured data into {target_language} while preserving the exact structure and field names.

Translation Guidelines:
1. ONLY translate the content/values of the fields, NOT the field names or structure
2. Preserve all field names exactly as they are
3. Translate only the text content within string values
4. Keep all numbers, dates, and non-text data unchanged
5. Maintain medical accuracy and terminology
6. If a field is null or empty, keep it as null
7. Do not add, remove, or modify any field names
8. Do not change the data types (strings stay strings, numbers stay numbers, etc.)
9. For nested objects (symptoms, medications, illnesses), translate only the text content within each object
10. For arrays of strings (like allergies), translate each string element
11. Preserve medical terminology and proper names when appropriate
12. Use natural, fluent language in the target language

Target Language: {target_language}

Structured Data to Translate:
{structured_data}

Return the translated data with the same structure and field names, but with translated content.
"""