from app.core.functional_config import load_prompt

def get_thread_extractor_instructions() -> str:
    """
    Get instructions for the thread extractor used in the workflow.
    
    Returns:
        String containing the instructions for the thread extractor
    """
    return load_prompt("progress_summary/thread_extractor_instructions")
