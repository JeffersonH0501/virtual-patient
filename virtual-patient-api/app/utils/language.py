"""
Language utilities for the Virtual Patient API
"""

from typing import Any


PATIENT_RESPONSE_LANGUAGE_KEY = "patient_response_language"
SUPPORTED_LANGUAGE_CODES = ("en", "es")


def resolve_ui_language(
    requested_language: str | None,
    preferred_language: str | None = None,
) -> str:
    """Resolve a supported interface language with a stable English fallback."""
    if requested_language in SUPPORTED_LANGUAGE_CODES:
        return requested_language
    if preferred_language in SUPPORTED_LANGUAGE_CODES:
        return preferred_language
    return "en"

def convert_language_code_to_name(language_code: str) -> str:
    """
    Convert language code to full language name
    
    Args:
        language_code: Two-letter language code (e.g., 'en', 'es')
        
    Returns:
        Full language name (e.g., 'English', 'Spanish')
    """
    language_mapping = {
        "en": "English",
        "es": "Spanish"
    }
    return language_mapping.get(language_code, "English")

def get_supported_language_codes() -> list:
    """
    Get list of supported language codes
    
    Returns:
        List of supported language codes
    """
    return list(SUPPORTED_LANGUAGE_CODES)

def get_supported_language_names() -> list:
    """
    Get list of supported language names
    
    Returns:
        List of supported language names
    """
    return ["English", "Spanish"]


def with_patient_response_language(
    interview_metadata: dict[str, Any] | None,
    language_code: str,
) -> dict[str, Any]:
    """Return copied interview metadata with its patient language recorded."""
    metadata = dict(interview_metadata or {})
    metadata[PATIENT_RESPONSE_LANGUAGE_KEY] = language_code
    return metadata


def resolve_patient_response_language(
    interview_metadata: dict[str, Any] | None,
    legacy_language_code: str = "en",
) -> str:
    """Resolve the interview language while supporting legacy interviews."""
    configured_language = (interview_metadata or {}).get(
        PATIENT_RESPONSE_LANGUAGE_KEY
    )
    if configured_language in SUPPORTED_LANGUAGE_CODES:
        return configured_language
    if legacy_language_code in SUPPORTED_LANGUAGE_CODES:
        return legacy_language_code
    return "en"
