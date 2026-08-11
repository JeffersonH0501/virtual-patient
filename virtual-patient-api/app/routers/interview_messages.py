import asyncio
import time
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.models.user import User
from app.models.medical_interview import (
    InterviewMessage
)
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.message_controller import MessageController
from app.controllers.virtual_patient_controller import VirtualPatientController
from app.controllers.progress_summary_controller import ProgressSummaryController

router = APIRouter(
    prefix="/medical-interviews", 
    tags=["interview-messages"],
    responses={404: {"description": "Interview or message not found"}},
)

class SendMessageRequest(BaseModel):
    content: str
    message_metadata: Dict[str, Any] = {}

class SendMessageResponse(BaseModel):
    messages: List[InterviewMessage]
    new_message_ids: List[int] = []  # IDs of messages that were just created in this request

class MessagesWithSummaryResponse(BaseModel):
    messages: List[InterviewMessage]

@router.post("/{interview_id}/messages", response_model=SendMessageResponse)
async def send_message(
    interview_id: int,
    message_data: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Send a message to the virtual patient and receive an AI-generated response.

    This endpoint:
    1. Validates the user has access to the interview
    2. Creates the user message in the database
    3. Gets all interview messages for context
    4. Calls the virtual patient workflow agent
    5. Appends the agent response to the interview messages
    6. Returns the complete message exchange with updated summary
    
    - **interview_id**: Unique identifier for the interview (used as thread_id)
    - **content**: The message to send to the patient
    - **message_metadata**: Additional message metadata (optional)
    
    Returns the complete message exchange with updated summary.
    """
    start_time = time.time()
    
    virtual_patient_controller = VirtualPatientController()
    
    try:
        result = await virtual_patient_controller.process_user_message(
            interview_id=interview_id,
            user_message_content=message_data.content,
            current_user=current_user,
            db=db,
            message_metadata=message_data.message_metadata
        )
        
        # Extract what we need for the response
        agent_response = result["agent_response"]
        user_message_object = result["user_message_object"]
        agent_message_object = result["agent_message_object"]

        # Initialize controllers for database operations
        message_controller = MessageController(db)

        # Wait for async message creation to complete (so audio_url is available in response)
        new_message_ids = await _async_message_creation(
            message_controller,
            {
                "interview_id": interview_id,
                "content": agent_response,
                "message_metadata": agent_message_object.message_metadata if hasattr(agent_message_object, 'message_metadata') else {}
            },
            {
                "interview_id": interview_id,
                "content": user_message_object.content if hasattr(user_message_object, 'content') else message_data.content,
                "message_metadata": user_message_object.message_metadata if hasattr(user_message_object, 'message_metadata') else message_data.message_metadata
            }
        )
        
        # Reload messages from database to get the saved audio_url
        saved_messages = message_controller.get_interview_messages(interview_id)
        
        # Prepare response with messages from database (which includes audio_url)
        # Include the IDs of newly created messages so UI can identify them
        response = SendMessageResponse(
            messages=saved_messages,
            new_message_ids=new_message_ids
        )
        
        # Note: Background memory processing is handled within the agent (agent responsibility)
        
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"⏱️ TEXT ENDPOINT TOTAL TIME: {execution_time:.3f} seconds")
        
        return response
        
    except Exception as e:
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"⏱️ TEXT ENDPOINT TOTAL TIME (ERROR): {execution_time:.3f} seconds")
        
        print(f"Error in send_message endpoint: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing message: {str(e)}"
        )

@router.get("/{interview_id}/messages", response_model=MessagesWithSummaryResponse)
async def get_messages(
    interview_id: int,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get message history for an interview with progress summary.
    
    - **interview_id**: Unique identifier for the interview
    - **limit**: Maximum number of messages to return (default: 100)
    
    Returns a list of messages in chronological order along with the progress summary.
    """
    interview_controller = MedicalInterviewController(db)
    message_controller = MessageController(db)
    progress_summary_controller = ProgressSummaryController(db)
    
    # Validate access
    if not interview_controller.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )
    
    # Validate interview exists
    if not interview_controller.get_interview(interview_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    # Get messages and progress summary
    messages = message_controller.get_interview_messages(interview_id, limit)
    progress_summary = progress_summary_controller.get_progress_summary(interview_id)
    
    return MessagesWithSummaryResponse(
        messages=messages,
        progress_summary=progress_summary
    )

@router.get("/{interview_id}/messages/{message_id}", response_model=InterviewMessage)
async def get_message(
    interview_id: int,
    message_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific message by ID.
    
    - **interview_id**: Unique identifier for the interview
    - **message_id**: Unique identifier for the message
    
    Returns the specific message if it belongs to the interview.
    """
    interview_controller = MedicalInterviewController(db)
    message_controller = MessageController(db)
    
    # Validate access
    if not interview_controller.validate_interview_access(interview_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interview"
        )
    
    message = message_controller.get_message(message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Validate message belongs to this interview
    if message.interview_id != interview_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Message does not belong to this interview"
        )
    
    return message


def _schedule_async_message_operations(
    interview_controller: MedicalInterviewController,
    message_controller: MessageController,
    interview_id: int,
    agent_response: str,
    thread_id: str,
    user_message: InterviewMessage
) -> None:
    """
    Schedule async database operations for saving messages only.
    Summary processing is now handled by a separate endpoint.
    """
    try:
        # Prepare message operations data
        db_ops_data = interview_controller.prepare_async_message_operations(
            message_controller, interview_id, 
            agent_response, thread_id, user_message
        )
        
        # Schedule async message operations (fire and forget)
        asyncio.create_task(
            _async_message_creation(
                db_ops_data["message_service"],
                db_ops_data["agent_message_data"],
                db_ops_data["user_message_data"]
            )
        )
        print(f"🚀 Scheduled async message creation for interview {interview_id}")
        
    except Exception as e:
        print(f"Error scheduling async message operations: {e}")


async def _async_message_creation(
    message_service: MessageController,
    agent_message_data: Dict[str, Any],
    user_message_data: Dict[str, Any] = None
) -> List[int]:
    """
    Async helper function to create both user and agent messages in the database.
    This runs in the background when there's no summary to update.
    
    For patient messages, also generates TTS audio and uploads to Google Cloud Storage.
    
    Returns:
        List of message IDs that were created (user message + patient message)
    """
    new_message_ids = []
    
    try:
        # Create user message if provided
        if user_message_data:
            user_message = message_service.create_user_message(
                interview_id=user_message_data["interview_id"],
                content=user_message_data["content"],
                message_metadata=user_message_data["message_metadata"]
            )
            new_message_ids.append(user_message.id)
            print(f"💾 Successfully created user message in database: {user_message.id}")

        # Generate TTS audio and upload to GCS for patient messages
        audio_url = None
        try:
            from app.utils.tts_service import TTSService
            from app.utils.gcs_service import GCSService
            from app.models.medical_interview.medical_interview import MedicalInterviewDB

            tts_service = TTSService()
            gcs_service = GCSService()

            patient_content = agent_message_data["content"]
            interview_id = agent_message_data["interview_id"]

            # Get interview to access personality and gender
            interview = message_service.db.query(MedicalInterviewDB).filter(
                MedicalInterviewDB.id == interview_id
            ).first()
            
            # Extract personality namespace_key and gender
            personality_namespace_key = None
            gender = None
            
            if interview:
                gender = interview.patient_gender
                if interview.personality:
                    personality_namespace_key = interview.personality.namespace_key
                    print(f"🎭 Found personality: {personality_namespace_key}, gender: {gender}")
                else:
                    print(f"🎭 No personality found, using gender: {gender}")
            else:
                print(f"⚠️  Interview {interview_id} not found, using default voice")

            # Generate TTS audio with personality and gender-based voice selection
            audio_data = tts_service.generate_audio(
                text=patient_content,
                personality_namespace_key=personality_namespace_key,
                gender=gender
            )

            if audio_data and gcs_service.bucket:
                # Upload to GCS
                import uuid
                destination_path = f"audio/interview_{interview_id}/message_{uuid.uuid4().hex[:16]}.mp3"
                audio_url = gcs_service.upload_audio_bytes(
                    audio_data=audio_data,
                    destination_path=destination_path,
                    content_type="audio/mpeg",
                    make_public=True
                )
                
                if audio_url:
                    print(f"🔊 TTS audio generated and uploaded: {audio_url}")
                else:
                    print("⚠️  TTS audio generated but upload to GCS failed")
            elif audio_data:
                print("⚠️  TTS audio generated but GCS not configured (audio_url will be None)")
            else:
                print("⚠️  TTS audio generation failed (audio_url will be None)")
                
        except Exception as tts_error:
            print(f"⚠️  Error generating TTS audio (continuing without audio): {tts_error}")
            import traceback
            traceback.print_exc()
            # Continue without audio - message will be saved without audio_url
        
        # Create agent message with audio_url if available
        agent_message = message_service.create_patient_message(
            interview_id=agent_message_data["interview_id"],
            content=agent_message_data["content"],
            message_metadata=agent_message_data["message_metadata"],
            audio_url=audio_url
        )
        new_message_ids.append(agent_message.id)
        print(f"💾 Successfully created agent message in database: {agent_message.id}" + (f" with audio: {audio_url}" if audio_url else ""))
        
        return new_message_ids
    except Exception as e:
        print(f"❌ Error creating messages in background: {e}")
        import traceback
        traceback.print_exc()
        return new_message_ids  # Return whatever we managed to create 