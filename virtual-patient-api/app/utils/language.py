"""
Language utilities for the Virtual Patient API
"""

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
    return ["en", "es"]

def get_supported_language_names() -> list:
    """
    Get list of supported language names
    
    Returns:
        List of supported language names
    """
    return ["English", "Spanish"]
