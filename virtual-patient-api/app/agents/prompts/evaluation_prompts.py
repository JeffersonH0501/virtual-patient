"""
Evaluation Prompts for Virtual Patient System
Contains prompts for evaluating doctor's performance in medical interviews
"""

from app.core.functional_config import load_prompt, render_prompt


from typing import Optional
from .evaluation_aspects import format_aspects_for_prompt

def get_show_interest_prompt(target_language: str = "English") -> str:
    aspects_text = format_aspects_for_prompt("show_interest")
    
    return render_prompt("evaluation_prompts/show_interest",
        aspects_text=aspects_text,
        target_language=target_language,
    )

def get_show_empathy_prompt(target_language: str = "English") -> str:
    aspects_text = format_aspects_for_prompt("show_empathy")
    
    return render_prompt("evaluation_prompts/show_empathy",
        aspects_text=aspects_text,
        target_language=target_language,
    )

def get_speak_clearly_prompt(target_language: str = "English") -> str:
    aspects_text = format_aspects_for_prompt("speak_clearly")
    
    return render_prompt("evaluation_prompts/speak_clearly",
        aspects_text=aspects_text,
        target_language=target_language,
    )

def get_open_communication_prompt(target_language: str = "English") -> str:
    aspects_text = format_aspects_for_prompt("open_communication")
    
    return render_prompt("evaluation_prompts/open_communication",
        aspects_text=aspects_text,
        target_language=target_language,
    )

def get_general_communication_prompt(target_language: str = "English") -> str:
    aspects_text = format_aspects_for_prompt("general_communication")
    
    return render_prompt("evaluation_prompts/general_communication",
        aspects_text=aspects_text,
        target_language=target_language,
    )

def get_completeness_prompt(target_language: str = "English", patient_gender: Optional[str] = None) -> str:
    aspects_text = format_aspects_for_prompt("completeness", numbered=False)
    
    # Gender-specific instructions
    gender_instructions = ""
    if patient_gender:
        gender_lower = patient_gender.lower()
        if gender_lower == "male":
            gender_instructions = load_prompt("evaluation_prompts/female_gender_instructions")
        elif gender_lower == "female":
            gender_instructions = load_prompt("evaluation_prompts/male_gender_instructions")
    
    return render_prompt("evaluation_prompts/completeness",
        gender_instructions=gender_instructions,
        aspects_text=aspects_text,
        target_language=target_language,
    )

def get_hypothesis_completeness_prompt(target_language: str = "English") -> str:
    """Get prompt for evaluating hypotheses against the original clinical case"""
    return render_prompt("evaluation_prompts/hypothesis_completeness",
        target_language=target_language,
    )
def get_completeness_verification_prompt(target_language: str = "English") -> str:
    """Get prompt for phase 2: verifying completeness evaluation against the full conversation"""
    return render_prompt("evaluation_prompts/completeness_verification",
        target_language=target_language,
    )

def get_evaluation_prompts(target_language: str = "English", patient_gender: Optional[str] = None) -> dict:
    """Get evaluation prompts with target language support"""
    return {
        "general_communication": get_general_communication_prompt(target_language),
        "open_communication": get_open_communication_prompt(target_language),
        "show_interest": get_show_interest_prompt(target_language),
        "show_empathy": get_show_empathy_prompt(target_language),
        "speak_clearly": get_speak_clearly_prompt(target_language),
        "completeness": get_completeness_prompt(target_language, patient_gender),
        "completeness_verification": get_completeness_verification_prompt(target_language),
        "hypothesis_completeness": get_hypothesis_completeness_prompt(target_language),
    }

# For backward compatibility
