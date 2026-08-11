"""
Summary Router
Handles summary processing endpoints
"""

import asyncio
import time
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.agents.schemas.progress_summary import ProgressSummarySchema

from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.models.user import User
from app.models.medical_interview.interview_message import InterviewMessage
from app.models.medical_interview.progress_summary import ProgressSummary
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.controllers.summary_controller import SummaryController
from app.controllers.progress_summary_controller import ProgressSummaryController
from app.controllers.message_controller import MessageController
from app.agents.schemas.progress_summary import ProgressSummarySchema
from app.utils.language import convert_language_code_to_name

router = APIRouter(prefix="/medical-interviews", tags=["summary"])


class ProcessSummaryResponse(BaseModel):
    """Response model for summary processing"""
    summary_result: Optional[ProgressSummarySchema] = None


class GetSummaryResponse(BaseModel):
    """Response model for getting summary"""
    summary: Optional[ProgressSummary] = None


@router.post("/{interview_id}/summary", response_model=ProcessSummaryResponse)
async def process_summary(
    interview_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Process the progress summary for an interview.
    
    This endpoint:
    1. Validates the user has access to the interview
    2. Checks if existing summary is up-to-date (compares summary.updated_at with last message.created_at)
    3. If summary is current, returns existing summary from database
    4. If summary is outdated or doesn't exist, processes new summary:
       - Gets all interview messages for context
       - Calls the summary workflow to generate and translate the summary
       - Persists the summary to the database (async)
    5. Returns the summary result
    
    - **interview_id**: Unique identifier for the interview
    
    No request body needed - uses all messages from the interview automatically.
    Returns the processed summary with translation, or cached summary if up-to-date.
    """
    start_time = time.time()
    
    print(f"Processing summary for Interview ID: {interview_id}")
    print(f"Current user: {current_user}")

    interview_controller = MedicalInterviewController(db)
    message_controller = MessageController(db)
    summary_controller = SummaryController()
    progress_summary_controller = ProgressSummaryController(db)

    try:
        # Validate user has access to the interview and get clinical case
        interview, clinical_case = interview_controller.validate_interview_access_with_case(interview_id, current_user)
        
        # Check if summary is up-to-date before processing
        existing_summary = progress_summary_controller.get_progress_summary(interview_id)
        interview_messages = message_controller.get_interview_messages(interview_id)
        
        if existing_summary and interview_messages:
            # Get the last message timestamp
            last_message = interview_messages[-1]  # Messages are ordered by created_at
            last_message_time = last_message.created_at
            summary_updated_time = existing_summary.updated_at
            print(f"🔍 DEBUG: Summary updated time: {summary_updated_time}")
            print(f"🔍 DEBUG: Last message time: {last_message_time}")
            
            # If summary was updated after the last message, return existing summary
            if summary_updated_time >= last_message_time:

                existing_summary_schema = ProgressSummarySchema(
                    age=existing_summary.age,
                    current_symptoms=existing_summary.current_symptoms,
                    allergies=existing_summary.allergies,
                    medications=existing_summary.medications,
                    diet_information=existing_summary.diet_information,
                    current_illnesses=existing_summary.current_illnesses,
                    family_history=existing_summary.family_history,
                    summary_text=existing_summary.summary_text
                )
                
                # Calculate and print total execution time
                end_time = time.time()
                total_time = end_time - start_time
                print(f"⏱️  TOTAL SUMMARY ENDPOINT EXECUTION TIME (CACHED): {total_time:.3f} seconds")
                
                return ProcessSummaryResponse(summary_result=existing_summary_schema)
            else:
                print(f"🔄 Summary is outdated, processing new summary")
        elif existing_summary and not interview_messages:
            print(f"ℹ️ No messages found, processing new summary")
        elif not existing_summary:
            print(f"ℹ️ No existing summary found, processing new summary")
        
        print(f"Total interview messages: {len(interview_messages)}")
        
        # Format messages for the summary workflow
        formatted_messages = []
        for msg in interview_messages:
            formatted_messages.append({
                "role": "user" if msg.sender_type == "user" else "assistant",
                "content": msg.content
            })
        
        # Get user's preferred language and convert to full language name
        user_language_code = current_user.preferred_language or "en"
        user_language_name = convert_language_code_to_name(user_language_code)
        
        print(f"🔍 DEBUG: User language code: '{user_language_code}'")
        print(f"🔍 DEBUG: User language name: '{user_language_name}'")
        print(f"🔍 DEBUG: User preferred_language field: '{current_user.preferred_language}'")
        
        # Call the summary workflow
        workflow_result = await summary_controller.process_summary(
            interview_id=interview_id,
            messages=formatted_messages,
            clinical_case=clinical_case,
            user_preferred_language=user_language_name
        )
        
        # Extract summary for response
        summary_result = workflow_result.get("summary_result")
        translated_summary = workflow_result.get("translated_summary")
        
        print(f"🔍 DEBUG: Workflow result keys: {workflow_result.keys()}")
        print(f"🔍 DEBUG: Summary result type: {type(summary_result)}")
        print(f"🔍 DEBUG: Translated summary type: {type(translated_summary)}")
        print(f"🔍 DEBUG: Translated summary is None: {translated_summary is None}")
        
        if summary_result:
            print(f"✅ Generated summary for interview {interview_id}")
        if translated_summary:
            print(f"✅ Translated summary for interview {interview_id}")
        
        # Schedule async database operations (non-blocking)
        _schedule_async_summary_operations(
            progress_summary_controller,
            interview_id, 
            summary_result, 
            translated_summary
        )
        
        # Calculate and print total execution time
        end_time = time.time()
        total_time = end_time - start_time
        print(f"⏱️  TOTAL SUMMARY ENDPOINT EXECUTION TIME: {total_time:.3f} seconds")
        
        return ProcessSummaryResponse(
            summary_result=translated_summary
        )
        
    except Exception as e:
        # Calculate and print total execution time even on error
        end_time = time.time()
        total_time = end_time - start_time
        print(f"⏱️  TOTAL SUMMARY ENDPOINT EXECUTION TIME (ERROR): {total_time:.3f} seconds")
        
        print(f"Error in process_summary endpoint: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing summary: {str(e)}"
        )


@router.get("/{interview_id}/summary", response_model=GetSummaryResponse)
async def get_summary(
    interview_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the progress summary for an interview.
    
    This endpoint:
    1. Validates the user has access to the interview
    2. Retrieves the progress summary from the database
    3. Returns the summary data if found
    
    - **interview_id**: Unique identifier for the interview
    
    Returns the progress summary if it exists, otherwise returns summary=null.
    """
    print(f"Getting summary for Interview ID: {interview_id}")
    print(f"Current user: {current_user.id}")

    interview_controller = MedicalInterviewController(db)
    progress_summary_controller = ProgressSummaryController(db)

    try:
        # Validate user has access to the interview
        if not interview_controller.validate_interview_access(interview_id, current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this interview"
            )
        
        # Get the progress summary from the database
        summary = progress_summary_controller.get_progress_summary(interview_id)
        
        if summary:
            print(f"✅ Found summary for interview {interview_id}")
            return GetSummaryResponse(summary=summary)
        else:
            print(f"ℹ️ No summary found for interview {interview_id}")
            return GetSummaryResponse(summary=None)
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 403 Forbidden)
        raise
    except Exception as e:
        print(f"Error in get_summary endpoint: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving summary: {str(e)}"
        )


def _schedule_async_summary_operations(
    progress_summary_controller: ProgressSummaryController,
    interview_id: int,
    summary_result: Optional[Any],
    translated_summary: Optional[Any]
):
    """
    Schedule async database operations for summary persistence
    """
    async def _async_summary_operations():
        try:
            if summary_result:
                print(f"🔍 DEBUG: summary_result type: {type(summary_result)}")
                print(f"🔍 DEBUG: summary_result has dict method: {hasattr(summary_result, 'dict')}")
                print(f"🔍 DEBUG: summary_result is dict: {isinstance(summary_result, dict)}")
                
                # Create or update progress summary in database
                # Ensure we have a ProgressSummarySchema object
                if isinstance(summary_result, dict):
                    # Convert dict to ProgressSummarySchema
                    summary_schema = ProgressSummarySchema(**summary_result)
                elif hasattr(summary_result, 'dict'):
                    # Already a Pydantic model
                    summary_schema = summary_result
                else:
                    # Try to convert to ProgressSummarySchema
                    summary_schema = ProgressSummarySchema(**summary_result)
                
                # Check if summary already exists
                existing_summary = progress_summary_controller.get_progress_summary(interview_id)
                
                if existing_summary:
                    # Update existing summary
                    progress_summary_controller.update_progress_summary(
                        interview_id,
                        summary_schema
                    )
                    print(f"✅ Updated progress summary in database for interview {interview_id}")
                else:
                    # Create new summary
                    progress_summary_controller.create_progress_summary(
                        interview_id=interview_id,
                        summary_data=summary_schema
                    )
                    print(f"✅ Created progress summary in database for interview {interview_id}")
                
        except Exception as e:
            print(f"❌ Error in async summary operations: {e}")
    
    # Schedule the async operation
    asyncio.create_task(_async_summary_operations())
