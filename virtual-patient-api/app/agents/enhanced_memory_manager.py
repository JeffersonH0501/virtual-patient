"""
Enhanced Memory Manager for Virtual Patient Agent
Implements three types of memory: Semantic, and Procedural
Based on the DiamantAI multi-agent memory architecture
"""

import os
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.store.base import BaseStore
from enum import Enum
from langmem import create_manage_memory_tool, create_search_memory_tool, create_memory_store_manager
from .prompts.memory_tool_instructions import MANAGE_MEMORY_INSTRUCTIONS, SEARCH_MEMORY_INSTRUCTIONS, BACKGROUND_LEARNING_INSTRUCTIONS

class SemanticMemory:
    """
    Stores factual information about the patient - medical facts that exist independent of specific experiences.
    Similar to how you know "Paris is the capital of France" without remembering when you learned it.
    """
    
    def __init__(self, store: BaseStore, interview_id: str):
        self.store = store
        self.interview_id = interview_id
        self.namespace = ("semantic_memory_store", interview_id)
        
        # Create semantic memory tools
        self.manage_tool = create_manage_memory_tool(
            namespace=self.namespace,
            store=self.store,
            instructions=MANAGE_MEMORY_INSTRUCTIONS
        )
        
        self.search_tool = create_search_memory_tool(
            namespace=self.namespace,
            store=self.store,
            instructions=SEARCH_MEMORY_INSTRUCTIONS
        )
    
    def store_patient_fact(self, fact_type: str, content: str, metadata: Dict[str, Any] = None):
        """Store a medical fact about the patient"""
        fact_data = {
            "type": fact_type,  # symptoms, medications, allergies, family_history, etc.
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        key = f"{fact_type}_{datetime.now().timestamp()}"
        self.store.put(self.namespace, key, fact_data)
    
    def search_facts(self, query: str, fact_type: str = None, limit: int = 5) -> List[Any]:
        """Search for patient facts"""
        results = self.store.search(self.namespace, query=query, limit=limit)

        
        return results
    

class InteractionRole(Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"


class ProceduralMemory:
    """
    Stores learned behaviors and processes - how to respond to different types of questions.
    Like muscle memory for conversation patterns and response strategies.
    Uses a shared namespace across all interviews for common patterns.
    """
    
    def __init__(self, store: BaseStore, interview_id: str):
        self.store = store
        self.interview_id = interview_id
        # Use shared namespace for procedural memory patterns
        self.namespace = ("procedural_memory_store",)
        
        # Note: Default patterns are now initialized once via the initialization script
        # and shared across all interviews
    
    def store_response_pattern(self, trigger: str, pattern: str, example: str = ""):
        """Store a learned response pattern"""
        pattern_data = {
            "trigger": trigger,
            "pattern": pattern,
            "example": example,
            "learned_at": datetime.now().isoformat(),
            "usage_count": 1
        }
        
        key = f"pattern_{trigger}"
        self.store.put(self.namespace, key, pattern_data)
    
    def get_response_guidance(self, question: str) -> Optional[Dict[str, Any]]:
        """Get guidance on how to respond to a specific type of question"""
        results = self.store.search(self.namespace, query=question, limit=2)
        
        if results and hasattr(results[0], 'value'):
            return results[0].value
        return None
    
    def update_pattern_usage(self, trigger: str):
        """Update usage count for a pattern (for learning which patterns work best)"""
        results = self.store.search(self.namespace, query=trigger, limit=1)
        
        if results and hasattr(results[0], 'value'):
            pattern = results[0].value
            pattern['usage_count'] = pattern.get('usage_count', 0) + 1
            pattern['last_used'] = datetime.now().isoformat()
            
            key = f"pattern_{trigger}"
            self.store.put(self.namespace, key, pattern)


class EnhancedMemoryManager:
    """
    Orchestrates all three types of memory for the virtual patient agent
    """
    
    def __init__(self, store: BaseStore, interview_id: str, llm=None):
        self.store = store
        self.interview_id = interview_id
        self.llm = llm

        self.procedural = ProceduralMemory(store, interview_id)
        
        # Initialize background memory manager for learning from interactions
        if llm:
            self.background_memory_manager = create_memory_store_manager(
                llm,
                namespace=("semantic_background_memory_store", interview_id),
                store=self.store,
                instructions=BACKGROUND_LEARNING_INSTRUCTIONS,
                enable_inserts=True,
                enable_deletes=True,
            )
        else:
            self.background_memory_manager = None
        
        print(f"Enhanced Memory Manager initialized for interview: {interview_id}")
        print(f"Memory namespaces: procedural, background")
    
    
    def get_contextual_memory(self, current_question: str, timeout: float = 1.0, limit: int = 2) -> Dict[str, Any]:
        """Get relevant memories for the current question
        
        Args:
            current_question: The question to search for
            timeout: Maximum time in seconds to wait for memory search (default: 1.0)
            limit: Maximum number of memories to retrieve (default: 2)
        """
        import time as time_module
        
        print(f"🔍 MEMORY DEBUG: Searching memories for interview_id: {self.interview_id}")
        
        # If no semantic facts found, try background memories
        # Reduce limit for faster search (especially important for vector search)
        background_memories = []
        if self.background_memory_manager:
            try:
                search_start = time_module.time()
                # Use reduced limit for faster searches (2 instead of 3)
                background_results = self.background_memory_manager.search(query=current_question, limit=limit)
                search_time = time_module.time() - search_start
                
                # If search took longer than timeout, log warning
                if search_time > timeout:
                    print(f"⚠️ Memory search took {search_time:.3f}s (target: <{timeout}s)")
                
                background_memories = [r.value for r in background_results if hasattr(r, 'value')]
                print(f"🔍 Found {len(background_memories)} background memories for: {current_question[:30]}... ({search_time:.3f}s)")
            except Exception as e:
                print(f"⚠️ Error searching background memories: {e}")
                # Continue without background memories - don't fail the whole request
        
        # Get procedural guidance (should be fast as it's local)
        procedural_guidance = self.procedural.get_response_guidance(current_question)
        
        return {
            "background_memories": background_memories,
            "response_guidance": procedural_guidance,
        }
    
    def format_enhanced_memories(self, memory_context: Dict[str, Any]) -> str:
        """Format enhanced memories for the prompt"""
        formatted_parts = []
    
        
        # Add background memories if no semantic facts found
        if memory_context.get("background_memories"):
            background_text = "Patient Medical Facts:\n"
            for memory in memory_context["background_memories"]:
                # Handle both Memory objects and dictionaries
                if hasattr(memory, 'value'):
                    content = memory.value.get('content', '') if isinstance(memory.value, dict) else str(memory.value)
                else:
                    content = memory.get('content', '') if isinstance(memory, dict) else str(memory)
                background_text += f"- {content}\n"
            formatted_parts.append(background_text)
        
        # Add procedural guidance
        if memory_context.get("response_guidance"):
            guidance = memory_context["response_guidance"]
            guidance_text = "Response Guidance:\n"
            guidance_text += f"Pattern: {guidance.get('pattern', '')}\n"
            if guidance.get('example'):
                guidance_text += f"Example: {guidance.get('example', '')}\n"
            formatted_parts.append(guidance_text)
        
        return "\n\n".join(formatted_parts) if formatted_parts else "No previous memories available"
    
    async def process_background_memories(self, doctor_question: str, patient_response: dict) -> None:
        """
        Process background memories for learning from interactions.
        This runs in the background to improve agent behavior.
        
        Args:
            doctor_question: The doctor's question
            patient_response: The patient's response
        """
        if self.background_memory_manager:
            try:
                to_process = {"messages": [{"role": "user", "content": doctor_question}] + [patient_response]}
                await self.background_memory_manager.ainvoke(to_process)
                print(f"✅ Background memory processed")
            except Exception as e:
                print(f"❌ Error processing background memory: {e}")
        else:
            print("⚠️ Background memory manager not initialized (no LLM provided)")
    