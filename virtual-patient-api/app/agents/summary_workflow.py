"""
Summary Workflow Agent
Handles progress summary generation and translation separately from the main interview workflow
"""

import time
from typing import Optional, Dict, Any, List, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.store.base import BaseStore
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_core.messages import HumanMessage, AIMessage

from langmem import create_thread_extractor

from app.agents.translator_agent import TranslatorAgent
from app.agents.prompts.progress_summary import get_thread_extractor_instructions
from app.agents.schemas.progress_summary import ProgressSummarySchema
from app.agents.helpers import normalize_summary_data
from app.models.clinical_case import ClinicalCaseDB
from app.core.azure_openai import create_chat_model

# Initialize the globally selected Azure OpenAI v1 LLM.
llm = create_chat_model()

class SummaryState(TypedDict):
    """State for the summary workflow"""
    messages: Annotated[List[Any], "List of messages from the interview"]
    clinical_case: Annotated[ClinicalCaseDB, "Clinical case information"]
    interview_id: Annotated[str, "Interview ID"]
    current_summary: Annotated[Optional[Dict[str, Any]], "Current summary from store"]
    summary_result: Annotated[Optional[ProgressSummarySchema], "Generated summary"]
    translated_summary: Annotated[Optional[ProgressSummarySchema], "Translated summary"]


class SummaryWorkflow:
    """
    Workflow for processing progress summaries separately from the main interview
    """
    
    def __init__(
        self, 
        store: BaseStore, 
        checkpointer: BaseCheckpointSaver,
        interview_id: str,
        current_language: str = "English"
    ):
        self.store = store
        self.checkpointer = checkpointer
        self.interview_id = interview_id
        self.current_language = current_language
        
        # Initialize translator agent
        self.translator_agent = TranslatorAgent()
        
        # Initialize summary extractor
        self.summary_extractor = create_thread_extractor(
            llm,
            schema=ProgressSummarySchema,
            instructions=get_thread_extractor_instructions()
        )
        
        # Create the workflow
        self.workflow = self._create_workflow()
        
        print(f"Summary Workflow initialized for interview: {interview_id}")
        print(f"Target language: '{current_language}'")
    
    async def get_current_summary_node(self, state: SummaryState) -> SummaryState:
        """Node that retrieves the current progress summary from the store"""
        start_time = time.time()
        
        try:
            # Get current summary from store
            current_summary_item = self.store.get(("progress_summary", self.interview_id), "current_summary")
            if current_summary_item:
                print(f"📋 Retrieved current summary from store for interview {self.interview_id}")
                current_summary = current_summary_item.value
            else:
                print(f"📋 No current summary found in store for interview {self.interview_id}")
                current_summary = None
            
            end_time = time.time()
            print(f"⏱️  GET_CURRENT_SUMMARY_NODE: {end_time - start_time:.3f} seconds")
            
            return {"current_summary": current_summary}
            
        except Exception as e:
            print(f"⚠️ Could not retrieve current summary: {e}")
            end_time = time.time()
            print(f"⏱️  GET_CURRENT_SUMMARY_NODE (ERROR): {end_time - start_time:.3f} seconds")
            return {"current_summary": None}

    async def create_summary_node(self, state: SummaryState) -> SummaryState:
        """Node that creates/updates a summary using the thread extractor"""
        start_time = time.time()
        
        # Get existing summary from memory namespace
        existing_summary = state.get("current_summary")
        
        # Get messages and clinical case from state
        messages = state.get('messages', [])
        clinical_case = state.get('clinical_case')
        
        # Create enhanced state with messages and existing summary
        enhanced_state = {
            "messages": messages,
            "existing_summary": existing_summary,
        }
        
        # Run the summary extraction with schema
        try:
            summary_result = await self.summary_extractor.ainvoke(enhanced_state)
            
            # Process and validate the summary data
            if summary_result:
                try:
                    summary_data = summary_result.dict() if hasattr(summary_result, 'dict') else summary_result
                    
                    # Normalize the data to ensure it matches the schema
                    normalized_data = normalize_summary_data(summary_data)
                    
                    # Validate the normalized data with the schema
                    validated_summary = ProgressSummarySchema(**normalized_data)
                    
                    # Update the summary_result with the validated data
                    summary_result = validated_summary
                    print(f"✅ Generated validated summary for interview {self.interview_id}")
                    
                    # Store the summary in the namespace for future retrieval
                    try:
                        self.store.put(("progress_summary", self.interview_id), "current_summary", summary_result.dict())
                        print(f"💾 Stored summary in namespace for interview {self.interview_id}")
                    except Exception as store_error:
                        print(f"⚠️ Could not store summary: {store_error}")
                    
                except Exception as e:
                    print(f"Could not validate summary: {e}")
        except Exception as e:
            print(f"Error in summary extraction: {e}")
            # Create a fallback summary with basic information
            summary_result = ProgressSummarySchema(
                summary_text=f"Interview progress summary - Error occurred during extraction: {str(e)}"
            )
        
        end_time = time.time()
        print(f"⏱️  CREATE_SUMMARY_NODE: {end_time - start_time:.3f} seconds")
        
        # Return only the fields we're updating
        return {"summary_result": summary_result}

    async def translate_summary_node(self, state: SummaryState) -> SummaryState:
        """Node that translates the progress summary to the target language"""
        start_time = time.time()
        
        summary_result = state.get("summary_result")
        
        if not summary_result:
            print("⚠️ No summary result found to translate")
            end_time = time.time()
            print(f"⏱️  TRANSLATE_SUMMARY_NODE: {end_time - start_time:.3f} seconds")
            return {"translated_summary": None}

        if self.current_language.strip().lower() == "english":
            return {"translated_summary": summary_result}
        
        try:
            # Convert to ProgressSummarySchema if it's not already
            if not isinstance(summary_result, ProgressSummarySchema):
                if isinstance(summary_result, dict):
                    summary_result = ProgressSummarySchema(**summary_result)
                else:
                    print(f"⚠️ Unexpected summary result type: {type(summary_result)}")
                    end_time = time.time()
                    print(f"⏱️  TRANSLATE_SUMMARY_NODE: {end_time - start_time:.3f} seconds")
                    return {"translated_summary": None}
            
            # Translate the summary using the translator agent
            print(f"🔄 Starting translation to {self.current_language}...")
            translated_summary = await self.translator_agent.translate_progress_summary(
                summary_result, 
                self.current_language
            )
            print(f"✅ Translation completed successfully")
            
            print(f"✅ Translated summary to {self.current_language}")
            end_time = time.time()
            print(f"⏱️  TRANSLATE_SUMMARY_NODE: {end_time - start_time:.3f} seconds")
            return {"translated_summary": translated_summary}
            
        except Exception as e:
            print(f"❌ Error translating summary: {e}")
            end_time = time.time()
            print(f"⏱️  TRANSLATE_SUMMARY_NODE (ERROR): {end_time - start_time:.3f} seconds")
            # Fallback to original summary if translation fails
            return {"translated_summary": summary_result}

    def _create_workflow(self) -> StateGraph:
        """Create the StateGraph workflow for summary processing"""
        
        # Create the state graph
        workflow = StateGraph(SummaryState)
        
        # Add nodes to the workflow
        workflow.add_node("get_current_summary", self.get_current_summary_node)
        workflow.add_node("create_summary", self.create_summary_node)
        workflow.add_node("translate_summary", self.translate_summary_node)
        
        # Define the workflow edges - linear flow
        workflow.add_edge("get_current_summary", "create_summary")
        workflow.add_edge("create_summary", "translate_summary")
        workflow.add_edge("translate_summary", END)
        
        # Set the entry point
        workflow.set_entry_point("get_current_summary")
        
        return workflow.compile()
    
    async def process_summary(
        self, 
        messages: List[Dict[str, str]], 
        clinical_case: ClinicalCaseDB
    ) -> Dict[str, Any]:
        """
        Process summary generation and translation
        
        Args:
            messages: List of message dictionaries with role and content
            clinical_case: The clinical case object
        
        Returns:
            Dictionary containing the summary result
        """
        # Convert messages to proper format
        formatted_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                if msg.get("role") == "user":
                    formatted_messages.append(HumanMessage(content=msg["content"]))
                elif msg.get("role") == "assistant":
                    formatted_messages.append(AIMessage(content=msg["content"]))
            else:
                formatted_messages.append(msg)
        
        # Create initial state
        initial_state = {
            "messages": formatted_messages,
            "clinical_case": clinical_case,
            "interview_id": self.interview_id,
            "current_summary": None,
            "summary_result": None,
            "translated_summary": None
        }
        
        # Run the workflow
        result = await self.workflow.ainvoke(initial_state)
        
        return {
            "summary_result": result.get("summary_result"),
            "translated_summary": result.get("translated_summary")
        }


def create_summary_workflow(
    store: BaseStore, 
    checkpointer: BaseCheckpointSaver,
    interview_id: str,
    current_language: str = "English"
) -> SummaryWorkflow:
    """
    Create a summary workflow instance
    
    Args:
        store: PostgresStore instance for memory
        checkpointer: PostgresSaver instance for checkpointing
        interview_id: Unique identifier for the interview
        current_language: Target language for translation
    
    Returns:
        SummaryWorkflow instance
    """
    return SummaryWorkflow(
        store=store,
        checkpointer=checkpointer,
        interview_id=interview_id,
        current_language=current_language
    )
