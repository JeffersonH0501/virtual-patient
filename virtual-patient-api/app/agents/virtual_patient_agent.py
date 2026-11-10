import time
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from langgraph.prebuilt import create_react_agent
from app.core.memory_store import PostgresStore
from app.core.async_work import run_sync_owned
from copy import deepcopy
from langgraph.store.base import BaseStore
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from app.core.database import SessionLocal
from app.utils.clinical_case import create_clinical_case_summary

from app.core.database import SQLALCHEMY_DATABASE_URL
from app.core.azure_openai import (
    EMBEDDING_DIMENSIONS,
    create_chat_model,
    create_embeddings,
)
from app.models.clinical_case import ClinicalCaseDB

from app.agents.prompts.interview_prompt import create_interview_prompt
from app.agents.enhanced_memory_manager import EnhancedMemoryManager

# Module-level cache for clinical case summaries (persists across requests/instances)
# Key: clinical_case_id, Value: summary string
_clinical_case_summary_cache = {}

# Azure OpenAI clients use the globally selected LLM variant.
llm = create_chat_model()
embeddings = create_embeddings()

# Checkpointer for graph state persistence

async def process_background_memories_standalone(
    interview_id: str,
    doctor_question: str,
    patient_response: AIMessage
) -> None:
    """
    Standalone function to process background memories with its own database connection.
    This is called as a fire-and-forget task and manages its own resources.
    
    Args:
        interview_id: The interview ID for memory context
        doctor_question: The doctor's question content
        patient_response: The patient's response as AIMessage
    """
    try:
        
        # Create a new PostgresStore connection for this background task
        with PostgresStore.from_conn_string(
            SQLALCHEMY_DATABASE_URL,
            index={
                "dims": EMBEDDING_DIMENSIONS,
                "embed": embeddings,
            }
        ) as store:
            # Create memory manager with its own LLM and store
            memory_manager = EnhancedMemoryManager(store, interview_id, llm=llm)
            
            # Process background memories
            await memory_manager.process_background_memories(
                doctor_question, 
                patient_response
            )
            
            
    except Exception as e:
        # Don't raise - this is a background task and shouldn't affect the main response
        import traceback
        traceback.print_exc()


class VirtualPatientAgent:
    """
    Enhanced memory manager agent that implements both hot path and background memory management
    using PostgreSQL storage with semantic search capabilities.
    """
    
    def __init__(self, store: BaseStore, checkpointer: BaseCheckpointSaver, interview_id: str,
                 *, persist_background_memory: bool = True):
        # Set up PostgreSQL store with semantic search capabilities
        
        self.store = store
        self.llm = llm
        self.checkpointer = checkpointer
        self.interview_id = interview_id
        self.persist_background_memory = persist_background_memory
    
        # Initialize enhanced memory manager
        self.enhanced_memory = EnhancedMemoryManager(store, interview_id, llm)
        
        
        # Initialize patient attributes (will be set by workflow)
        self._patient_name = 'Virtual Patient'
        self._patient_gender = None
        
        # Create the virtual patient agent for medical interview sessions
        self.hot_path_agent = create_react_agent(
            model=llm,
            tools=[],
            prompt=self._create_interview_prompt,
            store=self.store,
            checkpointer=self.checkpointer
        )

    
    def _create_interview_prompt(self, state):
        """Create prompt for virtual patient using interview structure - for pre_model_hook"""
        
        # Get the current question
        current_question = state["messages"][-1].content

        # Use enhanced memory system to get contextual memories (includes background memories if needed)
        # Add timeout to prevent long waits
        memory_start = time.time()
        try:
            memory_context = self.enhanced_memory.get_contextual_memory(
                current_question, 
                timeout=0.6  # 500ms timeout for memory search
            )
        except Exception as e:
            # Use empty context on timeout
            memory_context = {"background_memories": [], "response_guidance": ""}
        memory_retrieval_time = time.time() - memory_start
        
        # Format memories for the prompt
        format_start = time.time()
        memories = self.enhanced_memory.format_enhanced_memories(memory_context)
        format_time = time.time() - format_start
        
        # Get clinical case information from the agent's stored clinical case
        summary_start = time.time()
        clinical_case = getattr(self, '_current_clinical_case', None)
        
        # Use cached summary if available
        clinical_case_summary = self._get_clinical_case_summary_cached(clinical_case)
        summary_time = time.time() - summary_start
        
        # Get current time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get patient name from clinical case based on gender
        # This will be set by the workflow when gender is chosen in UI
        patient_name = getattr(self, '_patient_name', 'Virtual Patient')
        
        # Create interview prompt with structured data
        prompt_start = time.time()
        interview_prompt = create_interview_prompt(
            name=patient_name,
            summary=clinical_case_summary,
            current_time=current_time,
            context=memories or "No previous memories available",
            person="Doctor",
            question=current_question
        )
        prompt_time = time.time() - prompt_start
        
        # Print the complete interview prompt for debugging

        # Add the SystemMessage at the end
        system_message = SystemMessage(content=interview_prompt)
        
        # Return the messages with the System message for the current LLM call
        # But the state["messages"] has already been filtered to only contain AI and Human messages
        return [system_message, *state["messages"]]
    
    def set_patient_attributes(self, name: str, gender: str, clinical_case: ClinicalCaseDB):
        """
        Set patient name and gender based on UI selection
        
        Args:
            name: Patient name (from female_name or male_name based on gender)
            gender: Patient gender ('male' or 'female')
            clinical_case: Clinical case object to get gender-specific data
        """
        self._patient_name = name
        self._patient_gender = gender
        
        # Store the clinical case for reference
        self._current_clinical_case = clinical_case
        
    
    async def process_medical_interview_message(
        self, 
        messages: List[Dict[str, str]], 
        clinical_case: ClinicalCaseDB,
        thread_id: Optional[str] = None,
        client_request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a medical interview message using hot path memory management.
        
        Args:
            messages: List of conversation messages
            clinical_case: The clinical case object
            thread_id: Optional thread ID for conversation continuity
            
        Returns:
            Response from the agent with memory management
        """
        import time
        
        # Start total timer
        total_start_time = time.time()
        
        # Store the clinical case in the agent instance for access in pre_model_hook
        if isinstance(clinical_case, ClinicalCaseDB):
            clinical_case = ClinicalCaseDB(**{
                column.key: deepcopy(getattr(clinical_case, column.key))
                for column in ClinicalCaseDB.__table__.columns
            })
        self._current_clinical_case = clinical_case
        
        # Ensure thread_id is set (should always be provided by router)
        setup_start = time.time()
        if not thread_id:
            thread_id = str(self.interview_id)
        
        config = {
            "configurable": {
                "thread_id": thread_id,
                "interview_id": self.interview_id,
                "clinical_case": clinical_case
            },
            "recursion_limit": 100
        }
        setup_time = time.time() - setup_start
        
        
        agent_start = time.time()
        graph_input = {"messages": messages}
        if client_request_id:
            message_id = f"client-request-{client_request_id}"
            saved = await run_sync_owned(self.hot_path_agent.get_state, config)
            saved_messages = saved.values.get("messages", []) if saved.values else []
            original = next((message for message in saved_messages if message.id == message_id), None)
            if original is not None:
                last_question = next((message for message in reversed(saved_messages) if isinstance(message, HumanMessage)), None)
                if original is not last_question:
                    raise RuntimeError("The checkpoint advanced beyond the unpersisted exchange")
                if original.content != messages[-1]["content"]:
                    raise ValueError("Message request identifier has a different checkpointed question")
                if not saved.next:
                    if not saved_messages or not isinstance(saved_messages[-1], AIMessage):
                        raise RuntimeError("The checkpointed exchange is incomplete")
                    return {**saved.values, "_request_translation_finalized":
                        saved_messages[-1].additional_kwargs.get("finalized_client_request_id") == client_request_id}
                graph_input = None
            else:
                graph_input = {"messages": [*messages[:-1], {**messages[-1], "id": message_id}]}
        response = await run_sync_owned(self.hot_path_agent.invoke,
            graph_input,
            config=config
        )

        agent_time = time.time() - agent_start

        ##print(f"AGENT RESPONSE: \n\n {response} \n\n")

        # Process background memories asynchronously (fire-and-forget)
        doctor_content = None
        last_message = None
        if messages and len(messages) > 0:
            doctor_question = messages[-1]
            doctor_content = doctor_question.get('content', str(doctor_question))
            response_messages = response.get("messages", [])
            if doctor_content and response_messages:
                last_message = response_messages[-1]
        
        # Schedule background memory processing (non-blocking)
        # Uses standalone function with its own database connection
        if self.persist_background_memory and doctor_content and last_message:
            self.background_task = asyncio.create_task(
                process_background_memories_standalone(
                    interview_id=self.interview_id,
                    doctor_question=doctor_content,
                    patient_response=last_message
                )
            )
         
        # Print total time (without memory processing blocking)
        total_time = time.time() - total_start_time
       
        return response
    
    def _get_clinical_case_summary_from_object(self, clinical_case: ClinicalCaseDB) -> str:
        """
        Get clinical case summary from the clinical case object using the utility function
        """
        try:
            return create_clinical_case_summary(clinical_case)
                
        except Exception as e:
            return "Patient information not available"
    
    def _get_clinical_case_summary_cached(self, clinical_case: ClinicalCaseDB) -> str:
        """
        Get clinical case summary with module-level caching to avoid recreation on every call.
        Uses module-level cache so it persists across agent instances/requests.
        """
        if clinical_case is None:
            return "Patient information not available"
        
        # Get clinical case ID
        clinical_case_id = clinical_case.id if hasattr(clinical_case, 'id') else None
        
        if clinical_case_id is None:
            # Fallback to generating without cache if no ID
            return self._get_clinical_case_summary_from_object(clinical_case)
        
        # Check module-level cache first
        if clinical_case_id in _clinical_case_summary_cache:
            return _clinical_case_summary_cache[clinical_case_id]
        
        # Generate new summary and cache it at module level
        summary = self._get_clinical_case_summary_from_object(clinical_case)
        _clinical_case_summary_cache[clinical_case_id] = summary
        
        # Limit cache size to prevent memory issues (keep last 100 cases)
        if len(_clinical_case_summary_cache) > 10:
            oldest_key = next(iter(_clinical_case_summary_cache))
            del _clinical_case_summary_cache[oldest_key]
        
        return summary
    
    def search_patient_memories(
        self, 
        query: str,
        limit: int = 5
    ) -> str:
        """
        Search for patient memories using enhanced memory system.
        
        Args:
            query: Search query
            limit: Maximum number of results to return
            
        Returns:
            String of relevant memories
        """
        # Use enhanced memory system to get comprehensive memory context
        memory_context = self.enhanced_memory.get_contextual_memory(query)
        return self.enhanced_memory.format_enhanced_memories(memory_context)
    
    def collect_doctor_feedback(self, session_id: str, question: str, patient_response: str, 
                               doctor_feedback: str, feedback_type: str = "improvement") -> Dict[str, Any]:
        """
        Collect feedback from a doctor and process it for learning
        
        Args:
            session_id: Session identifier
            question: Original question asked
            patient_response: Response given by the patient
            doctor_feedback: Feedback from the doctor
            feedback_type: Type of feedback (improvement, correction, praise)
            
        Returns:
            Processing result with optimization status
        """
        return self.feedback_collector.collect_feedback(
            session_id=session_id,
            question=question,
            patient_response=patient_response,
            doctor_feedback=doctor_feedback,
            feedback_type=feedback_type
        )
