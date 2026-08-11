from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.medical_interview import (
    InterviewMessageDB, InterviewMessage, InterviewMessageCreate,
    SenderType, MedicalInterviewDB
)

class MessageController:
    def __init__(self, db: Session):
        self.db = db

    def create_message(self, interview_id: int, message_data: InterviewMessageCreate) -> InterviewMessage:
        """Create a new message"""
        message = InterviewMessageDB(
            interview_id=interview_id,
            content=message_data.content,
            sender_type=message_data.sender_type,
            message_metadata=message_data.message_metadata or {},
            audio_url=message_data.audio_url
        )
        
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        
        # Use model_validate for Pydantic v2, fallback to from_orm for v1
        try:
            return InterviewMessage.model_validate(message)
        except AttributeError:
            # Fallback for Pydantic v1
            return InterviewMessage.from_orm(message)
    
    def create_user_message(self, interview_id: int, content: str, message_metadata: Optional[Dict[str, Any]] = None) -> InterviewMessage:
        """Create a user message"""
        return self.create_message(
            interview_id,
            InterviewMessageCreate(
                content=content,
                sender_type=SenderType.USER,
                message_metadata=message_metadata
            )
        )
    
    def create_patient_message(self, interview_id: int, content: str, message_metadata: Optional[Dict[str, Any]] = None, audio_url: Optional[str] = None) -> InterviewMessage:
        """Create a patient message (AI response)"""
        return self.create_message(
            interview_id,
            InterviewMessageCreate(
                content=content,
                sender_type=SenderType.PATIENT,
                message_metadata=message_metadata,
                audio_url=audio_url
            )
        )
    
    def get_interview_messages(self, interview_id: int, limit: Optional[int] = None) -> List[InterviewMessage]:
        """Get all messages for an interview"""
        query = self.db.query(InterviewMessageDB).filter(
            InterviewMessageDB.interview_id == interview_id
        ).order_by(InterviewMessageDB.created_at)
        
        if limit:
            query = query.limit(limit)
        
        messages = query.all()
        # Use model_validate for Pydantic v2, fallback to from_orm for v1
        try:
            return [InterviewMessage.model_validate(message) for message in messages]
        except AttributeError:
            # Fallback for Pydantic v1
            return [InterviewMessage.from_orm(message) for message in messages]
    
    def get_message(self, message_id: int) -> Optional[InterviewMessage]:
        """Get a specific message by ID"""
        message = self.db.query(InterviewMessageDB).filter(InterviewMessageDB.id == message_id).first()
        if message:
            # Use model_validate for Pydantic v2, fallback to from_orm for v1
            try:
                return InterviewMessage.model_validate(message)
            except AttributeError:
                # Fallback for Pydantic v1
                return InterviewMessage.from_orm(message)
        return None
    
    def get_conversation_history(self, interview_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get conversation history formatted for GPT context"""
        messages = self.get_interview_messages(interview_id, limit)
        
        history = []
        for message in messages:
            history.append({
                "role": SenderType.USER if message.sender_type == SenderType.USER else SenderType.CHATBOT,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
            })
        
        return history
    
    def process_message_exchange(
        self, 
        interview_id: str, 
        user_message: str,
        chatbot_response: str,
        summary_updates: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a complete message exchange (user message + chatbot response)"""
        
        # Create user message
        user_msg = self.create_user_message(interview_id, user_message)
        
        # Create chatbot message
        chatbot_msg = self.create_chatbot_message(
            interview_id, 
            chatbot_response,
            message_metadata={"response_time_ms": summary_updates.get("response_time_ms") if summary_updates else None}
        )
        
        return {
            "messages": [user_msg, chatbot_msg],
            "new_information": summary_updates.get("new_information", []) if summary_updates else []
        }
    
    def validate_interview_exists(self, interview_id: str) -> bool:
        """Validate that the interview exists"""
        interview = self.db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == interview_id).first()
        return interview is not None 