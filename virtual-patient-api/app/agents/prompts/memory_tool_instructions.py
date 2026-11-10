"""
Memory Tool Instructions for Virtual Patient Agent
Contains the detailed instructions for memory management tools
"""

from app.core.functional_config import load_prompt


MANAGE_MEMORY_INSTRUCTIONS = load_prompt("memory_tool_instructions/manage_memory_instructions")

SEARCH_MEMORY_INSTRUCTIONS = load_prompt("memory_tool_instructions/search_memory_instructions")

BACKGROUND_LEARNING_INSTRUCTIONS = load_prompt("memory_tool_instructions/background_learning_instructions")
