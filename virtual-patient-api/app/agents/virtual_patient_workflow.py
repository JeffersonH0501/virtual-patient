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
from app.agents.translator_agent import TranslatorAgent, PatientResponseError
from app.core.config import settings
from app.core.async_work import run_sync_owned, cancel_and_drain

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
    client_request_id: Optional[str]

class VirtualPatientWorkflow:
    """
    Workflow-based virtual patient agent using StateGraph with summary node
    Reuses existing VirtualPatientAgent
    """
    
    def __init__(self, store: BaseStore, checkpointer: BaseCheckpointSaver, interview_id: str, 
                 current_language: str = "English", patient_gender: str = None, patient_name: str = None,
                 personality: str = None, *, persist_background_memory: bool = True):
        self.store = store
        self.checkpointer = checkpointer
        self.interview_id = interview_id
        self.current_language = current_language
        self.patient_gender = patient_gender
        self.patient_name = patient_name
        self.personality = personality
        
        # Create the existing VirtualPatientAgent
        self.agent = VirtualPatientAgent(
            store=store, checkpointer=checkpointer, interview_id=interview_id,
            persist_background_memory=persist_background_memory,
        )
        
        # Create the translator agent
        self.translator_agent = TranslatorAgent()
        
        # Create the workflow
        self.workflow = self._create_workflow()
        
    
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
            thread_id=state["thread_id"],
            client_request_id=state.get("client_request_id"),
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
        return {"interview_result": result}

    async def translate_patient_response_node(self, state: State) -> State:
        """Node that translates patient responses with personality to target language"""
        start_time = time.time()
        
        # Check if there's an error from previous nodes
        if state.get("error_message"):
            raise PatientResponseError("Patient response generation failed")
        
        # Get the interview result to find the patient's response
        interview_result = state.get("interview_result", {})
        interview_messages = interview_result.get("messages", [])
        
        if not interview_messages:
            return state
        
        # Get the last AI message (patient's response)
        last_ai_message = interview_messages[-1] if interview_messages else None
        if not last_ai_message:
            return state
        
        patient_response = last_ai_message.content
        if interview_result.get("_request_translation_finalized"):
            return {"messages": [last_ai_message], "translated_patient_response": patient_response}
        
        # Build conversation history from previous PATIENT messages only (last 3)
        # This helps avoid repetition by showing what the patient already said
        conversation_history = []
        for msg in interview_messages[:-1]:  # Exclude the last message (current response)
            if isinstance(msg, AIMessage):  # Only include patient (assistant) messages
                conversation_history.append({"role": "assistant", "content": msg.content})
        
        # Keep only the last 3 patient messages
        conversation_history = conversation_history[-3:] if len(conversation_history) > 3 else conversation_history
        
        
        translation_start = time.time()
        
        # Translate patient response with personality to target language
        if self.current_language.lower() != "english" or self.personality:
            state["translated_patient_response"] = await self.translator_agent.translate_patient_with_personality(
                patient_message=patient_response,
                target_language=self.current_language if self.current_language.lower() != "english" else "English",
                personality_key=self.personality,
                patient_gender=self.patient_gender,
                patient_name=self.patient_name,
                conversation_history=conversation_history,
            )
        else:
            state["translated_patient_response"] = patient_response
        
        # Add the translated AI response with personality to state["messages"]
        if state["translated_patient_response"]:
            # Create AIMessage with translated response and add to state messages
            translated_ai_message = AIMessage(content=state["translated_patient_response"])
            
            # Update the interview result with the translated patient response
            if interview_messages:
                interview_messages[-1].content = state["translated_patient_response"]
                updated_interview_result = state["interview_result"].copy()
                updated_interview_result["messages"] = interview_messages
            
            end_time = time.time()
            total_time = end_time - start_time
            
            # Return the AI message to be added to state["messages"]
            return {
                "messages": [translated_ai_message],  # Add to state messages (original + AI response with personality)
                "translated_patient_response": state["translated_patient_response"],
                "interview_result": updated_interview_result if interview_messages else state.get("interview_result")
            }
        
        end_time = time.time()
        total_time = end_time - start_time
        return {"translated_patient_response": state["translated_patient_response"]}


    async def finalize_node(self, state: State) -> State:
        """Final node that ensures all parallel operations are complete"""
        start_time = time.time()
        
        # Check if there's an error state and return it
        if state.get("error_message"):
            raise PatientResponseError("Patient response generation failed")
        
        
        end_time = time.time()
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
        self, question, clinical_case, thread_id=None, client_request_id=None,
        *, history=(),
    ):
        """Keep owned background work inside the failed request's lifetime."""
        try:
            result = await self._process_interview_message(
                question, clinical_case, thread_id, client_request_id, history=history,
            )
            result["_background_task"] = getattr(self.agent, "background_task", None)
            return result
        except BaseException:
            await cancel_and_drain(getattr(self.agent, "background_task", None))
            raise

    async def _process_interview_message(
        self, 
        question: Dict[str, str], 
        clinical_case: ClinicalCaseDB,
        thread_id: Optional[str] = None,
        client_request_id: Optional[str] = None,
        *, history=(),
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
            "translated_patient_response": None,
            "client_request_id": client_request_id,
        }
        
        # Add new message to state
        initial_state["messages"] = [*history, *([new_question] if new_question else [])]
        
        result = await self.workflow.ainvoke(initial_state, config=config)
        
        # Update the agent's checkpointer with the translated patient response
        # This ensures the checkpointer stores the final translated message, not the intermediate one
        translated_response = result.get("translated_patient_response")
        if translated_response and not (result.get("interview_result") or {}).get("_request_translation_finalized"):
            await self._update_checkpointer_with_translated_message(
                thread_id=thread_id,
                translated_response=translated_response,
                config=config,
                client_request_id=client_request_id,
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
        config: Dict[str, Any],
        client_request_id: Optional[str] = None,
    ) -> None:
        """
        Update the agent's checkpointer with the translated patient response.
        
        The qualified saver is synchronous; keep its calls off the event loop.
        """
        try:
            
            checkpoint_config = {**config, "configurable": {
                key: value for key, value in config["configurable"].items()
                if key != "clinical_case"
            }}
            state = await run_sync_owned(self.agent.hot_path_agent.get_state, checkpoint_config)
            if not state or not state.values:
                return
            
            # Get messages from state
            messages = state.values.get("messages", [])
            if not messages:
                return
            
            # Update the last AI message with translated content
            updated = False
            for i in range(len(messages) - 1, -1, -1):
                if isinstance(messages[i], AIMessage):
                    messages[i].content = translated_response
                    if client_request_id:
                        messages[i].additional_kwargs = {**messages[i].additional_kwargs,
                            "finalized_client_request_id": client_request_id}
                    updated = True
                    break
            
            if not updated:
                return
            
            await run_sync_owned(self.agent.hot_path_agent.update_state, checkpoint_config, {"messages": messages})
            
        except Exception as e:
            if client_request_id:
                raise
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
