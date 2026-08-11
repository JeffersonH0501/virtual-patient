"""
Clinical Case Language Utilities
Handles retrieval and management of multilingual clinical case content
"""

from typing import Optional, Dict, Any, List
from app.models.clinical_case import ClinicalCaseDB
from app.utils.language import get_supported_language_codes

# List of translatable fields
TRANSLATABLE_FIELDS = [
    'title', 'description', 'chief_complaint', 'present_illness',
    'personal_medical_history', 'surgical_history', 'family_history',
    'medications', 'habits', 'allergies', 'concerns',
    'physical_requirements', 'socioeconomic_status', 'patient_context',
    'female_name', 'male_name'
]

# List of non-translatable fields
NON_TRANSLATABLE_FIELDS = [
    'id', 'case_key', 'case_type', 'organization_id', 'active', 'icon',
    'age', 'weight_in_kg', 'created_at', 'updated_at',
    'female_photo', 'male_photo', 'gender_restriction'
]

def get_field_in_language(
    clinical_case: ClinicalCaseDB, 
    field_name: str, 
    language_code: str = "en"
) -> str:
    """
    Get a specific field in the requested language
    
    Args:
        clinical_case: Clinical case database object
        field_name: Name of the field to retrieve
        language_code: Language code (e.g., 'en', 'es')
        
    Returns:
        Field content in the requested language
    """
    # If English, return the base field
    if language_code == "en":
        return getattr(clinical_case, field_name, "") or ""
    
    # Get translations
    translation_field = f"{field_name}_translations"
    translations = getattr(clinical_case, translation_field, {}) or {}
    
    # Return translation if available, otherwise return base field
    return translations.get(language_code, getattr(clinical_case, field_name, "") or "")

def set_field_translation(
    clinical_case: ClinicalCaseDB, 
    field_name: str,
    language_code: str,
    translated_text: str
) -> None:
    """
    Set a specific field translation
    
    Args:
        clinical_case: Clinical case database object
        field_name: Name of the field to translate
        language_code: Language code (e.g., 'es')
        translated_text: Translated text content
    """
    if language_code == "en":
        # For English, update the base field
        setattr(clinical_case, field_name, translated_text)
        return
    
    # Get existing translations
    translation_field = f"{field_name}_translations"
    existing_translations = getattr(clinical_case, translation_field, {}) or {}
    
    # Add new translation
    existing_translations[language_code] = translated_text
    setattr(clinical_case, translation_field, existing_translations)

def get_clinical_case_in_language(
    clinical_case: ClinicalCaseDB, 
    language_code: str = "en"
) -> Dict[str, Any]:
    """
    Get entire clinical case content in the requested language
    
    Args:
        clinical_case: Clinical case database object
        language_code: Language code (e.g., 'en', 'es')
        
    Returns:
        Dictionary with all fields in the requested language
    """
    result = {}
    
    # Get translatable fields in the requested language
    for field in TRANSLATABLE_FIELDS:
        result[field] = get_field_in_language(clinical_case, field, language_code)
    
    # Add non-translatable fields
    for field in NON_TRANSLATABLE_FIELDS:
        result[field] = getattr(clinical_case, field, None)
    
    return result

def get_available_languages(clinical_case: ClinicalCaseDB) -> List[str]:
    """
    Get list of available languages for a clinical case
    
    Args:
        clinical_case: Clinical case database object
        
    Returns:
        List of language codes that have translations
    """
    available_languages = {"en"}  # English is always available
    
    # Check all translation fields
    for field in TRANSLATABLE_FIELDS:
        translation_field = f"{field}_translations"
        translations = getattr(clinical_case, translation_field, {}) or {}
        available_languages.update(translations.keys())
    
    return list(available_languages)

def is_translation_complete(clinical_case: ClinicalCaseDB, language_code: str) -> bool:
    """
    Check if all fields are translated for a specific language
    
    Args:
        clinical_case: Clinical case database object
        language_code: Language code to check
        
    Returns:
        True if all fields are translated, False otherwise
    """
    if language_code == "en":
        return True
    
    for field in TRANSLATABLE_FIELDS:
        original_text = getattr(clinical_case, field, "")
        if original_text:  # Only check fields that have content
            translated_text = get_field_in_language(clinical_case, field, language_code)
            if translated_text == original_text:  # No translation available
                return False
    
    return True

def get_translation_status(clinical_case: ClinicalCaseDB) -> Dict[str, Any]:
    """
    Get translation status for a clinical case
    
    Args:
        clinical_case: Clinical case database object
        
    Returns:
        Dictionary with translation status information
    """
    available_languages = get_available_languages(clinical_case)
    supported_languages = get_supported_language_codes()
    
    status = {
        "case_id": clinical_case.id,
        "available_languages": available_languages,
        "supported_languages": supported_languages,
        "translation_completeness": {}
    }
    
    # Check completeness for each supported language
    for lang in supported_languages:
        status["translation_completeness"][lang] = is_translation_complete(clinical_case, lang)
    
    return status
