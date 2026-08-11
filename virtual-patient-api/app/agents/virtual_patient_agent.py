import os
import time
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from langchain.chat_models import init_chat_model
from langgraph.func import entrypoint
from langgraph.prebuilt import create_react_agent
from langgraph.store.postgres import PostgresStore
from langchain.embeddings import init_embeddings
from langgraph.checkpoint.memory import MemorySaver
from langgraph.utils.config import get_store
from langgraph.store.memory import InMemoryStore 
from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore
from langgraph.store.base import BaseStore
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_core.messages import SystemMessage, HumanMessage, RemoveMessage, AIMessage
from langchain_core.runnables.graph import MermaidDrawMethod
from IPython.display import display, Image
from psycopg import Connection
from app.core.database import SessionLocal
from app.utils.clinical_case import create_clinical_case_summary

from app.core.database import SQLALCHEMY_DATABASE_URL
from app.models.clinical_case import CaseType, ClinicalCaseDB

from app.agents.prompts.interview_prompt import (create_interview_prompt, INTERVIEW_PROMPT)
from app.agents.enhanced_memory_manager import EnhancedMemoryManager

load_dotenv()

# Module-level cache for clinical case summaries (persists across requests/instances)
# Key: clinical_case_id, Value: summary string
_clinical_case_summary_cache = {}

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
AZURE_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_EMBEDDING_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")

# Initialize LLM with Azure OpenAI
llm = init_chat_model(
    "azure_openai:gpt-4.1",
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    azure_deployment=AZURE_OPENAI_DEPLOYMENT_NAME,
    api_version=AZURE_OPENAI_API_VERSION
)

# Initialize Azure OpenAI embeddings
embeddings = init_embeddings(
    "azure_openai:text-embedding-3-small",
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    azure_deployment=AZURE_EMBEDDING_DEPLOYMENT,
    api_version=AZURE_OPENAI_API_VERSION
)

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
        print(f"\n🔧 [BACKGROUND] Starting memory processing for interview {interview_id}")
        
        # Create a new PostgresStore connection for this background task
        with PostgresStore.from_conn_string(
            SQLALCHEMY_DATABASE_URL,
            index={
                "dims": 1536,
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
            
            print(f"✅ [BACKGROUND] Memory processing completed for interview {interview_id}")
            
    except Exception as e:
        # Don't raise - this is a background task and shouldn't affect the main response
        print(f"⚠️ [BACKGROUND] Memory processing failed for interview {interview_id}: {e}")
        import traceback
        traceback.print_exc()


class VirtualPatientAgent:
    """
    Enhanced memory manager agent that implements both hot path and background memory management
    using PostgreSQL storage with semantic search capabilities.
    """
    
    def __init__(self, store: BaseStore, checkpointer: BaseCheckpointSaver, interview_id: str):
        # Set up PostgreSQL store with semantic search capabilities
        
        self.store = store
        self.llm = llm
        self.checkpointer = checkpointer
        self.interview_id = interview_id
    
        # Initialize enhanced memory manager
        self.enhanced_memory = EnhancedMemoryManager(store, interview_id, llm)
        
        print(f"Enhanced Memory Manager initialized for interview: {interview_id}")
        
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
        print("\n" + "─"*60)
        print("⏱️  PRE-MODEL HOOK TIMING (inside agent invoke)")
        print("─"*60)
        
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
            print(f"⚠️ Memory retrieval timeout or error: {e}")
            # Use empty context on timeout
            memory_context = {"background_memories": [], "response_guidance": ""}
        memory_retrieval_time = time.time() - memory_start
        print(f"⏱️  Memory Retrieval: {memory_retrieval_time:.3f}s")
        
        # Format memories for the prompt
        format_start = time.time()
        memories = self.enhanced_memory.format_enhanced_memories(memory_context)
        format_time = time.time() - format_start
        print(f"⏱️  Memory Formatting: {format_time:.3f}s")
        
        # Get clinical case information from the agent's stored clinical case
        summary_start = time.time()
        clinical_case = getattr(self, '_current_clinical_case', None)
        
        # Use cached summary if available
        clinical_case_summary = self._get_clinical_case_summary_cached(clinical_case)
        summary_time = time.time() - summary_start
        print(f"⏱️  Clinical Case Summary: {summary_time:.3f}s")
        
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
        print(f"⏱️  Prompt Creation: {prompt_time:.3f}s")
        print("─"*60)
        
        # Print the complete interview prompt for debugging
        print("\n" + "="*80)
        print("📋 COMPLETE INTERVIEW PROMPT:")
        print("="*80)
        print(interview_prompt)
        print("="*80 + "\n")
    
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
        
        print(f"Patient attributes set: Name={name}, Gender={gender}")
    
    async def process_medical_interview_message(
        self, 
        messages: List[Dict[str, str]], 
        clinical_case: ClinicalCaseDB,
        thread_id: Optional[str] = None
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
        print("\n" + "="*80)
        print("⏱️  PERFORMANCE TIMING - INTERVIEW PROCESSING")
        print("="*80)
        
        # Store the clinical case in the agent instance for access in pre_model_hook
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
        print(f"⏱️  Setup & Config: {setup_time:.3f}s")
        
        print(f"Invoking agent with {len(messages)} messages")
        print(f"🔍 AGENT DEBUG: interview_id: {self.interview_id}")
        print(f"🔍 AGENT DEBUG: thread_id: {thread_id}")
        print(f"🔍 AGENT DEBUG: clinical_case.id: {clinical_case.id}")
        
        agent_start = time.time()
        response = self.hot_path_agent.invoke(
            {"messages": messages},
            config=config
        )

        agent_time = time.time() - agent_start
        print(f"⏱️  Hot Path Agent Invoke: {agent_time:.3f}s")
        print(f"     └─ This includes: memory retrieval, prompt creation, and LLM call")

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
        if doctor_content and last_message:
            print(f"🧠 Scheduling background memory processing...")
            asyncio.create_task(
                process_background_memories_standalone(
                    interview_id=self.interview_id,
                    doctor_question=doctor_content,
                    patient_response=last_message
                )
            )
         
        # Print total time (without memory processing blocking)
        total_time = time.time() - total_start_time
        print("\n" + "-"*80)
        print(f"⏱️  TOTAL PROCESSING TIME: {total_time:.3f}s")
        print(f"     ├─ Setup & Config: {setup_time:.3f}s ({(setup_time/total_time)*100:.1f}%)")
        print(f"     ├─ Hot Path Agent: {agent_time:.3f}s ({(agent_time/total_time)*100:.1f}%)")
        print(f"     └─ Background memory processing scheduled (non-blocking)")
        print("="*80 + "\n")
       
        return response
    
    def _get_clinical_case_summary_from_object(self, clinical_case: ClinicalCaseDB) -> str:
        """
        Get clinical case summary from the clinical case object using the utility function
        """
        try:
            return create_clinical_case_summary(clinical_case)
                
        except Exception as e:
            print(f"Error getting clinical case summary from object: {e}")
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
            print(f"📦 Using cached clinical case summary (ID: {clinical_case_id})")
            return _clinical_case_summary_cache[clinical_case_id]
        
        # Generate new summary and cache it at module level
        print(f"🔄 Generating new clinical case summary (ID: {clinical_case_id})")
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

# run this the first time you run the app
def run_pg_setup():
    with Connection.connect(SQLALCHEMY_DATABASE_URL, autocommit=True) as conn:
        store = PostgresStore(conn=conn)
        checkpointer = PostgresSaver(conn=conn)
        store.setup()
        checkpointer.setup()
        print("PostgresStore and PostgresSaver setup completed.")


