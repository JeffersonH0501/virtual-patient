"""
Virtual Patient Service
Handles integration with the virtual patient workflow agent
"""

import os
import time
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from langgraph.store.postgres import PostgresStore
from langgraph.checkpoint.postgres import PostgresSaver
from langchain.embeddings import init_embeddings
from app.core.database import SQLALCHEMY_DATABASE_URL
from app.models.clinical_case import ClinicalCaseDB
from app.models.user import User
from app.agents.virtual_patient_workflow import create_virtual_patient_workflow
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.message_controller import MessageController
from app.utils.language import convert_language_code_to_name


# Initialize Azure OpenAI embeddings for semantic search
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_EMBEDDING_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")

embeddings = init_embeddings(
    "azure_openai:text-embedding-3-small",
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    azure_deployment=AZURE_EMBEDDING_DEPLOYMENT,
    api_version=AZURE_OPENAI_API_VERSION
)



class VirtualPatientController:
    """
    Service for managing virtual patient interactions
    """
    
    def __init__(self):
        pass
    
    async def process_interview_message(
        self,
        interview_id: int,
        messages: List[Dict[str, str]],
        clinical_case: ClinicalCaseDB,
        thread_id: Optional[str] = None,
        user_preferred_language: str = "English",
        patient_gender: Optional[str] = None,
        patient_name: Optional[str] = None,
        personality: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a message through the virtual patient workflow
        
        Args:
            interview_id: The interview ID (used as thread_id if not provided)
            messages: List of message dictionaries with role and content
            clinical_case: The clinical case object
            thread_id: Optional thread ID (defaults to interview_id)
            user_preferred_language: User's preferred language for responses
            patient_gender: Patient gender ('male' or 'female') - chosen in UI
            patient_name: Patient name - chosen in UI
        
        Returns:
            Dictionary containing the workflow result
        """
        # Use interview_id as thread_id if not provided
        if not thread_id:
            thread_id = str(interview_id)
        
        # Use context managers for proper resource management
        with (
            PostgresStore.from_conn_string(
                SQLALCHEMY_DATABASE_URL,
                index={
                    "dims": 1536,
                    "embed": embeddings,
                }
            ) as store,
            PostgresSaver.from_conn_string(SQLALCHEMY_DATABASE_URL) as checkpointer,
        ):
            try:
                # Create virtual patient workflow with user's preferred language and patient attributes
                workflow = create_virtual_patient_workflow(
                    store=store, 
                    checkpointer=checkpointer, 
                    interview_id=str(interview_id),
                    current_language=user_preferred_language,
                    patient_gender=patient_gender,
                    patient_name=patient_name,
                    personality=personality
                )
                
                result = await workflow.process_interview_message(
                    question=messages[-1],
                    clinical_case=clinical_case,
                    thread_id=thread_id
                )
                return result
                
            except Exception as e:
                print(f"Error processing message through workflow: {e}")
                raise
    
    def format_messages_for_workflow(self, messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        Format database messages for the workflow
        
        Args:
            messages: List of InterviewMessage objects from database
            
        Returns:
            List of message dictionaries with role and content
        """
        formatted_messages = []
        for message in messages:
            if hasattr(message, 'sender_type'):
                # Handle InterviewMessage objects from database
                # sender_type is a string, not an enum
                role = "user" if message.sender_type == "user" else "assistant"
                content = message.content
            elif isinstance(message, dict):
                # Handle dictionary format (for testing)
                role = message.get("role", "user")
                content = message.get("content", "")
            else:
                # Fallback
                role = "user"
                content = str(message)
            
            formatted_messages.append({
                "role": role,
                "content": content
            })
        return formatted_messages
    
    async def process_user_message(
        self,
        interview_id: int,
        user_message_content: str,
        current_user: User,
        db: Session,
        message_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Complete workflow to process a user message through the virtual patient system.
        This method handles the entire flow from validation to getting the AI response.
        
        Used by:
        - Text message endpoint (HTTP POST)
        - LiveKit voice agent (real-time voice)
        
        Args:
            interview_id: The interview ID
            user_message_content: The user's message content
            current_user: The current user making the request
            db: Database session
            message_metadata: Optional metadata for the message
            
        Returns:
            Dictionary containing:
                - agent_response: The virtual patient's response text
                - workflow_result: Complete workflow result with all data
                - interview: The interview object
                - clinical_case: The clinical case object
                - user_message_object: The user message object (not saved to DB)
                - formatted_messages: All messages formatted for display
                - processing_time: Total processing time in seconds
        """
        start_time = time.time()
        
        print(f"\n{'='*60}")
        print(f"🔄 Processing user message for interview {interview_id}")
        print(f"👤 User: {current_user.username}")
        print(f"💬 Message: {user_message_content[:100]}...")
        print(f"{'='*60}\n")
        
        # Initialize controllers
        interview_controller = MedicalInterviewController(db)
        message_controller = MessageController(db)
        
        # 1. Validate interview access and get data
        interview, clinical_case = interview_controller.validate_interview_access_with_case(
            interview_id, current_user
        )
        print(f"✅ Interview validated: {interview.id}")
        print(f"📋 Clinical case: {clinical_case.title}")
        
        # 2. Get all interview messages for context
        interview_messages = message_controller.get_interview_messages(interview_id)
        print(f"📨 Retrieved {len(interview_messages)} existing messages")
        
        # 3. Create user message object (not saved to database yet)
        user_message_object = interview_controller.create_message_object(
            interview_id=interview_id,
            content=user_message_content,
            sender_type="user",
            message_metadata=message_metadata or {}
        )
        print(f"📝 User message object created")
        
        # 4. Add user message to context for workflow
        interview_messages.append(user_message_object)
        
        # 5. Format messages for the virtual patient workflow
        formatted_messages = self.format_messages_for_workflow(interview_messages)
        print(f"📋 Formatted {len(formatted_messages)} messages for workflow")
        
        # 6. Get user's preferred language
        user_language_code = current_user.preferred_language or "en"
        user_language_name = convert_language_code_to_name(user_language_code)
        print(f"🌍 User language: {user_language_name} ({user_language_code})")
        
        # 7. Process through virtual patient workflow
        thread_id = f"interview-{interview_id}"
        print(f"🧵 Thread ID: {thread_id}")
        
        workflow_start = time.time()
        workflow_result = await self.process_interview_message(
            interview_id=interview_id,
            messages=formatted_messages,
            clinical_case=clinical_case,
            thread_id=thread_id,
            user_preferred_language=user_language_name,
            patient_gender=interview.patient_gender,
            patient_name=interview.patient_name,
            personality=interview.personality.namespace_key if interview.personality else None
        )
        workflow_time = time.time() - workflow_start
        print(f"⏱️  Workflow processing time: {workflow_time:.3f}s")
        
        # 8. Extract the agent response
        agent_response = interview_controller.extract_agent_response(workflow_result)
        
        if not agent_response:
            # Fallback: create a default response
            agent_response = "I understand your question. Let me think about how to respond based on my medical knowledge and the context of our conversation."
            print("⚠️  Warning: No agent response found, using fallback response")
        else:
            print(f"✅ Agent response extracted: {agent_response[:100]}...")
        
        # 9. Create agent message object for display
        agent_message_object = interview_controller.create_agent_message_object(
            interview_id, agent_response, thread_id
        )
        
        # 10. Add agent response to messages for return
        interview_messages.append(agent_message_object)
        
        total_time = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"✅ Message processing completed")
        print(f"⏱️  Total processing time: {total_time:.3f}s")
        print(f"{'='*60}\n")
        
        # Return comprehensive result
        return {
            "agent_response": agent_response,
            "workflow_result": workflow_result,
            "interview": interview,
            "clinical_case": clinical_case,
            "user_message_object": user_message_object,
            "agent_message_object": agent_message_object,
            "formatted_messages": interview_messages,
            "thread_id": thread_id,
            "processing_time": total_time,
            "new_information": workflow_result.get("interview_result", {}).get("new_information", [])
        }
