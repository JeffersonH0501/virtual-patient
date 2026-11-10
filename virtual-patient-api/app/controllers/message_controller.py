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

    def create_message(self, interview_id: int, message_data: InterviewMessageCreate, *, commit: bool = True) -> InterviewMessage:
        """Create a new message"""
        message = InterviewMessageDB(
            interview_id=interview_id,
            content=message_data.content,
            sender_type=message_data.sender_type,
            message_metadata=message_data.message_metadata or {},
            audio_url=message_data.audio_url
        )
        
        self.db.add(message)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        self.db.refresh(message)
        
        return InterviewMessage.model_validate(message)
    
    def create_user_message(self, interview_id: int, content: str, message_metadata: Optional[Dict[str, Any]] = None, *, commit: bool = True) -> InterviewMessage:
        """Create a user message"""
        return self.create_message(
            interview_id,
            InterviewMessageCreate(
                content=content,
                sender_type=SenderType.USER,
                message_metadata=message_metadata
            ), commit=commit,
        )
    
    def create_patient_message(self, interview_id: int, content: str, message_metadata: Optional[Dict[str, Any]] = None, audio_url: Optional[str] = None, *, commit: bool = True) -> InterviewMessage:
        """Create a patient message (AI response)"""
        return self.create_message(
            interview_id,
            InterviewMessageCreate(
                content=content,
                sender_type=SenderType.PATIENT,
                message_metadata=message_metadata,
                audio_url=audio_url
            ), commit=commit,
        )
    
    def get_interview_messages(self, interview_id: int, limit: Optional[int] = None, *, offset: int = 0) -> List[InterviewMessage]:
        """Get all messages for an interview"""
        query = self.db.query(InterviewMessageDB).filter(
            InterviewMessageDB.interview_id == interview_id
        ).order_by(InterviewMessageDB.created_at, InterviewMessageDB.id)
        
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)
        
        messages = query.all()
        return [InterviewMessage.model_validate(message) for message in messages]
    
    def get_message(self, message_id: int) -> Optional[InterviewMessage]:
        """Get a specific message by ID"""
        message = self.db.query(InterviewMessageDB).filter(InterviewMessageDB.id == message_id).first()
        if message:
            return InterviewMessage.model_validate(message)
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
    
    
    def validate_interview_exists(self, interview_id: str) -> bool:
        """Validate that the interview exists"""
        interview = self.db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == interview_id).first()
        return interview is not None
