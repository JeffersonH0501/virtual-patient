"""
Virtual Patient Workflow Agent
Uses StateGraph with summary node and thread extractor from langmem
Reuses existing VirtualPatientAgent
"""

import logging
import time
from typing import Optional, Dict, Any, List, TypedDict, Annotated
from operator import add
from langgraph.graph import StateGraph, END
from langgraph.store.base import BaseStore
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_core.messages import HumanMessage, AIMessage

from app.agents.virtual_patient_agent import VirtualPatientAgent
from app.agents.translator_agent import TranslatorAgent
from app.core.config import settings

from app.agents.schemas.progress_summary import ProgressSummarySchema

from app.models.clinical_case import ClinicalCaseDB


logger = logging.getLogger(__name__)

# State definition for the workflow
class State(TypedDict):
    messages: Annotated[List[HumanMessage | AIMessage], add]
    clinical_case: Annotated[ClinicalCaseDB, "The clinical case object"]
    thread_id: Annotated[Optional[str], "The thread ID for the conversation"]
    interview_id: Annotated[str, "The interview ID"]
    interview_result: Annotated[Optional[Dict[str, Any]], "The result from the interview node"]
    translated_patient_response: Annotated[Optional[str], "The translated patient response with personality"]
    error_message: Annotated[Optional[str], "Error message if any step fails"]

class VirtualPatientWorkflow:
    """
    Workflow-based virtual patient agent using StateGraph with summary node
    Reuses existing VirtualPatientAgent
    """
    
    def __init__(self, store: BaseStore, checkpointer: BaseCheckpointSaver, interview_id: str, 
                 current_language: str = "English", patient_gender: str = None, patient_name: str = None, personality: str = None):
        self.store = store
        self.checkpointer = checkpointer
        self.interview_id = interview_id
        self.current_language = current_language
        self.patient_gender = patient_gender
        self.patient_name = patient_name
        self.personality = personality
        
        # Create the existing VirtualPatientAgent
        self.agent = VirtualPatientAgent(store=store, checkpointer=checkpointer, interview_id=interview_id)
        
        # Create the translator agent
        self.translator_agent = TranslatorAgent()
        
        # Create the workflow
        self.workflow = self._create_workflow()
        
        print(f"Virtual Patient Workflow initialized for interview: {interview_id}")
        print(f"Target language: {current_language}")
        print(f"Patient personality: {personality}")
        print(f"Reusing existing VirtualPatientAgent with enhanced memory")
    
    async def create_interview_node(self, state: State) -> State:
        """
        Node that processes the interview using the existing VirtualPatientAgent.
        Uses state["messages"] with original messages.
        """
        start_time = time.time()
        
        # Use state["messages"] (includes all messages passed to workflow)
        # Convert to format expected by agent, using original messages as-is
        state_messages = state.get("messages", [])
        
        # Convert messages to format expected by agent
        messages = []
        for msg in state_messages:
            if isinstance(msg, HumanMessage):
                messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                messages.append({"role": "assistant", "content": msg.content})
        
        # Get clinical_case from state
        clinical_case = state.get("clinical_case")
        
        # Process the message using the existing agent with state messages
        # The agent will use the checkpointer to maintain conversation history
        agent_started_at = time.perf_counter()
        result = await self.agent.process_medical_interview_message(
            messages=messages,
            clinical_case=clinical_case,
            thread_id=state["thread_id"]
        )
        
        # Return only the fields we're updating
        end_time = time.time()
        if settings.patient_response_timing_logging:
            logger.info(
                "patient_response_timing interview_id=%s stage=workflow_interview_node "
                "agent_ms=%.1f total_ms=%.1f",
                self.interview_id,
                (time.perf_counter() - agent_started_at) * 1000,
                (end_time - start_time) * 1000,
            )
        print(f"⏱️  CREATE_INTERVIEW_NODE: {end_time - start_time:.3f} seconds")
        return {"interview_result": result}

    async def translate_patient_response_node(self, state: State) -> State:
        """Node that translates patient responses with personality to target language"""
        start_time = time.time()
        print(f"\n⏱️  TRANSLATE_PATIENT_RESPONSE_NODE: Starting...")
        
        # Check if there's an error from previous nodes
        if state.get("error_message"):
            print(f"⚠️ Error state detected, skipping patient response translation: {state['error_message']}")
            end_time = time.time()
            print(f"⏱️  TRANSLATE_PATIENT_RESPONSE_NODE (SKIPPED): {end_time - start_time:.3f} seconds")
            return state
        
        # Get the interview result to find the patient's response
        interview_result = state.get("interview_result", {})
        interview_messages = interview_result.get("messages", [])
        
        if not interview_messages:
            print("No interview messages found for patient response translation")
            return state
        
        # Get the last AI message (patient's response)
        last_ai_message = interview_messages[-1] if interview_messages else None
        if not last_ai_message:
            print("No patient response found for translation")
            return state
        
        patient_response = last_ai_message.content
        print(f"🎭 Translating patient response with personality: {patient_response}")
        
        # Build conversation history from previous PATIENT messages only (last 3)
        # This helps avoid repetition by showing what the patient already said
        conversation_history = []
        for msg in interview_messages[:-1]:  # Exclude the last message (current response)
            if isinstance(msg, AIMessage):  # Only include patient (assistant) messages
                conversation_history.append({"role": "assistant", "content": msg.content})
        
        # Keep only the last 3 patient messages
        conversation_history = conversation_history[-3:] if len(conversation_history) > 3 else conversation_history
        
        print(f"📚 Using last {len(conversation_history)} patient messages as context")
        
        translation_start = time.time()
        
        # Translate patient response with personality to target language
        if self.current_language.lower() != "english":
            print(f"⏱️  Translation mode: Non-English ({self.current_language})")
            try:
                translated_patient_response = await self.translator_agent.translate_patient_with_personality(
                    patient_message=patient_response,
                    target_language=self.current_language,
                    personality_key=self.personality,
                    patient_gender=self.patient_gender,
                    patient_name=self.patient_name,
                    conversation_history=conversation_history
                )
                translation_time = time.time() - translation_start
                print(f"✅ Translated patient response ({translation_time:.3f}s): {translated_patient_response}")
                state["translated_patient_response"] = translated_patient_response
                
            except Exception as e:
                translation_time = time.time() - translation_start
                print(f"❌ Error translating patient response ({translation_time:.3f}s): {e}")
                # Keep original response if translation fails
                state["translated_patient_response"] = patient_response
        else:
            # Already in target language, check if personality should be applied
            if self.personality:
                print(f"⏱️  Translation mode: English with personality")
                try:
                    # Apply personality to English response
                    translated_patient_response = await self.translator_agent.translate_patient_with_personality(
                        patient_message=patient_response,
                        target_language="English",
                        personality_key=self.personality,
                        patient_gender=self.patient_gender,
                        patient_name=self.patient_name,
                        conversation_history=conversation_history
                    )
                    translation_time = time.time() - translation_start
                    print(f"✅ Applied personality to English response ({translation_time:.3f}s): {translated_patient_response}")
                    state["translated_patient_response"] = translated_patient_response
                except Exception as e:
                    translation_time = time.time() - translation_start
                    print(f"❌ Error applying personality ({translation_time:.3f}s): {e}")
                    state["translated_patient_response"] = patient_response
            else:
                # No personality and English
                print(f"⏱️  Translation mode: English without personality (SKIPPED LLM)")
                state["translated_patient_response"] = patient_response
                translation_time = 0
        
        # Add the translated AI response with personality to state["messages"]
        if state["translated_patient_response"]:
            # Create AIMessage with translated response and add to state messages
            translated_ai_message = AIMessage(content=state["translated_patient_response"])
            
            # Update the interview result with the translated patient response
            if interview_messages:
                interview_messages[-1].content = state["translated_patient_response"]
                updated_interview_result = state["interview_result"].copy()
                updated_interview_result["messages"] = interview_messages
                print(f"🔄 Updated interview result with translated patient response")
            
            end_time = time.time()
            total_time = end_time - start_time
            print(f"⏱️  TRANSLATE_PATIENT_RESPONSE_NODE: {total_time:.3f}s total")
            print(f"     ├─ Context building: {translation_start - start_time:.3f}s")
            print(f"     └─ LLM translation: {translation_time:.3f}s")
            
            # Return the AI message to be added to state["messages"]
            return {
                "messages": [translated_ai_message],  # Add to state messages (original + AI response with personality)
                "translated_patient_response": state["translated_patient_response"],
                "interview_result": updated_interview_result if interview_messages else state.get("interview_result")
            }
        
        end_time = time.time()
        total_time = end_time - start_time
        print(f"⏱️  TRANSLATE_PATIENT_RESPONSE_NODE: {total_time:.3f}s total")
        print(f"     ├─ Context building: {translation_start - start_time:.3f}s")
        print(f"     └─ LLM translation: {translation_time:.3f}s")
        return {"translated_patient_response": state["translated_patient_response"]}


    async def finalize_node(self, state: State) -> State:
        """Final node that ensures all parallel operations are complete"""
        start_time = time.time()
        
        # Check if there's an error state and return it
        if state.get("error_message"):
            print(f"🔚 Finalizing workflow with error: {state['error_message']}")
            end_time = time.time()
            print(f"⏱️  FINALIZE_NODE (ERROR): {end_time - start_time:.3f} seconds")
            return {
                "translated_patient_response": state["error_message"]
            }
        
        print("🔚 Finalizing workflow - all operations complete")
        
        end_time = time.time()
        print(f"⏱️  FINALIZE_NODE: {end_time - start_time:.3f} seconds")
        return {}  # No state updates needed in finalize node

    def _create_workflow(self) -> StateGraph:
        """
        Create the StateGraph workflow with translation, interview, and patient translation nodes.

        """
        
        # Create the state graph
        workflow = StateGraph(State)
        
        # Add nodes to the workflow
        workflow.add_node("interview", self.create_interview_node)
        workflow.add_node("translate_patient_response", self.translate_patient_response_node)
        workflow.add_node("finalize", self.finalize_node)
        
        # Define the workflow edges - simple linear flow for fast response
        workflow.add_edge("interview", "translate_patient_response")
        workflow.add_edge("translate_patient_response", "finalize")
        workflow.add_edge("finalize", END)
        
        # Set the entry point
        workflow.set_entry_point("interview")
        
        # The agent's internal checkpointer (AsyncPostgresSaver) will maintain conversation history
        return workflow.compile()
    
    async def process_interview_message(
        self, 
        question: Dict[str, str], 
        clinical_case: ClinicalCaseDB,
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a medical interview message through the workflow.
        """
        # Ensure thread_id is set
        if not thread_id:
            thread_id = str(self.interview_id)
        
        # Set patient attributes in the agent if provided
        if self.patient_gender and self.patient_name:
            self.agent.set_patient_attributes(
                name=self.patient_name,
                gender=self.patient_gender,
                clinical_case=clinical_case
            )

        config = {
            "configurable": {
                "thread_id": thread_id,
                "interview_id": self.interview_id,
                "clinical_case": clinical_case
            }
        }

        # Prepare the new question message
        new_question = None
        if question.get("content"):
            new_question = HumanMessage(content=question.get("content"))
        
        # Create initial state with new message
        # Messages are passed directly to the agent which uses its own checkpointer
        initial_state = {
            "clinical_case": clinical_case,
            "thread_id": thread_id,
            "interview_id": self.interview_id,
            "interview_result": None,
            "translated_patient_response": None
        }
        
        # Add new message to state
        if new_question:
            initial_state["messages"] = [new_question]
        else:
            initial_state["messages"] = []
        
        result = await self.workflow.ainvoke(initial_state, config=config)
        
        # Update the agent's checkpointer with the translated patient response
        # This ensures the checkpointer stores the final translated message, not the intermediate one
        translated_response = result.get("translated_patient_response")
        if translated_response:
            await self._update_checkpointer_with_translated_message(
                thread_id=thread_id,
                translated_response=translated_response,
                config=config
            )
        
        return {
            "messages": result["messages"],  # Messages from workflow state
            "interview_result": result.get("interview_result"),
            "translated_patient_response": result.get("translated_patient_response")
        }
    
    async def _update_checkpointer_with_translated_message(
        self,
        thread_id: str,
        translated_response: str,
        config: Dict[str, Any]
    ) -> None:
        """
        Update the agent's checkpointer with the translated patient response.
        
        Uses AsyncPostgresSaver which supports aget_tuple and aput for async operations.
        See: https://langchain-ai.github.io/langgraph/how-tos/persistence_postgres/#use-async-connection
        """
        try:
            print("🔄 Updating agent checkpointer with translated patient response...")
            
            # Get current state from the agent's compiled graph
            # AsyncPostgresSaver supports aget_state which uses aget_tuple internally
            state = self.agent.hot_path_agent.get_state(config)
            if not state or not state.values:
                print("⚠️  No state found to update")
                return
            
            # Get messages from state
            messages = state.values.get("messages", [])
            if not messages:
                print("⚠️  No messages found in state")
                return
            
            # Update the last AI message with translated content
            updated = False
            for i in range(len(messages) - 1, -1, -1):
                if isinstance(messages[i], AIMessage):
                    messages[i].content = translated_response
                    print(f"✅ Updated last AI message in checkpointer")
                    updated = True
                    break
            
            if not updated:
                print("⚠️  No AI message found to update")
                return
            
            # Update state using compiled graph's update_state method
            # AsyncPostgresSaver supports aupdate_state which uses aput internally
            self.agent.hot_path_agent.update_state(config, {"messages": messages})
            print("✅ Checkpointer updated with translated patient response")
            
        except Exception as e:
            print(f"⚠️  Error updating checkpointer: {e}")
            import traceback
            traceback.print_exc()
    
    def search_patient_memories(self, query: str, limit: int = 5) -> str:
        """Search patient memories using the existing agent"""
        return self.agent.search_patient_memories(query, limit)

# Factory function to create the workflow agent
def create_virtual_patient_workflow(store: BaseStore, checkpointer: BaseCheckpointSaver, interview_id: str, 
                                  current_language: str = "English", patient_gender: str = None, patient_name: str = None, personality: str = None) -> VirtualPatientWorkflow:
    """Create a virtual patient workflow agent with translation support"""
    return VirtualPatientWorkflow(store=store, checkpointer=checkpointer, interview_id=interview_id, 
                                current_language=current_language, patient_gender=patient_gender, patient_name=patient_name, personality=personality)
