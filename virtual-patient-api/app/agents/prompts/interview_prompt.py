"""
Interview prompt for virtual patient agent
"""

from app.core.functional_config import load_prompt

INTERVIEW_PROMPT = load_prompt("interview_prompt/interview_prompt", "name", "current_time", "summary", "context", double_braces=True)

def create_interview_prompt(
    name: str,
    summary: str,
    current_time: str,
    context: str,
    person: str,
    question: str
) -> str:
    """
    Create an interview prompt with the given parameters.
    
    Args:
        name: Name of the virtual patient
        summary: Summary of the patient
        current_time: Current time
        context: Relevant context
        person: Name of the person asking the question
        question: The question being asked
        
    Returns:
        Formatted prompt string
    """
    # Replace the template variables with actual values
    prompt = INTERVIEW_PROMPT.replace("{{name}}", name)
    prompt = prompt.replace("{{current_time}}", current_time)
    prompt = prompt.replace("{{summary}}", summary)
    prompt = prompt.replace("{{context}}", context)
    prompt = prompt.replace("{{person}}", person)
    prompt = prompt.replace("{{question}}", question)
    
    return prompt
