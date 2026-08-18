"""
Service for managing progress summaries in the database.
"""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.medical_interview.progress_summary import (
    ProgressSummaryDB, 
    ProgressSummary,
)
from app.agents.schemas.progress_summary import ProgressSummarySchema

class ProgressSummaryController:
    """Service for managing progress summaries"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_progress_summary(self, interview_id: int) -> Optional[ProgressSummary]:
        """Get the progress summary for an interview"""
        summary = self.db.query(ProgressSummaryDB).filter(
            ProgressSummaryDB.medical_interview_id == interview_id
        ).first()
        
        return ProgressSummary.model_validate(summary) if summary else None

    def get_progress_summary_record(
        self,
        interview_id: int,
    ) -> Optional[ProgressSummaryDB]:
        """Return the mutable database record for internal summary operations."""
        return self.db.query(ProgressSummaryDB).filter(
            ProgressSummaryDB.medical_interview_id == interview_id
        ).first()

    @staticmethod
    def to_schema(summary: ProgressSummary | ProgressSummaryDB) -> ProgressSummarySchema:
        """Convert every persisted clinical field to the agent summary schema."""
        return ProgressSummarySchema(
            age=summary.age,
            weight_in_kg=summary.weight_in_kg,
            current_symptoms=summary.current_symptoms,
            allergies=summary.allergies,
            medications=summary.medications,
            diet_information=summary.diet_information,
            current_illnesses=summary.current_illnesses,
            family_history=summary.family_history,
            habits=summary.habits,
            medical_history=summary.medical_history,
            work_information=summary.work_information,
            summary_text=summary.summary_text,
        )
    
    def create_progress_summary(
        self, 
        interview_id: int, 
        summary_data: ProgressSummarySchema,
        message_id: Optional[int] = None,
        source_language: str = "en",
        localized_versions: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ProgressSummary:
        """Create a new progress summary for an interview"""
        try:
            # Convert Pydantic schema to dict for database storage
            summary_dict = summary_data.model_dump()
            
            # Create database model
            db_summary = ProgressSummaryDB(
                medical_interview_id=interview_id,
                age=summary_dict.get('age'),
                weight_in_kg=summary_dict.get('weight_in_kg'),
                current_symptoms=summary_dict.get('current_symptoms'),
                allergies=summary_dict.get('allergies'),
                medications=summary_dict.get('medications'),
                diet_information=summary_dict.get('diet_information'),
                current_illnesses=summary_dict.get('current_illnesses'),
                family_history=summary_dict.get('family_history'),
                habits=summary_dict.get('habits'),
                medical_history=summary_dict.get('medical_history'),
                work_information=summary_dict.get('work_information'),
                summary_text=summary_dict.get('summary_text'),
                source_language=source_language,
                localized_versions=localized_versions or {},
                last_updated_message_id=message_id,
                update_count=1,
                confidence_score=0.8  # Default confidence score
            )
            
            self.db.add(db_summary)
            self.db.commit()
            self.db.refresh(db_summary)
            
            return ProgressSummary.model_validate(db_summary)
            
        except IntegrityError:
            self.db.rollback()
            raise ValueError(f"Progress summary already exists for interview {interview_id}")
    
    def update_progress_summary(
        self, 
        interview_id: int, 
        summary_data: ProgressSummarySchema,
        message_id: Optional[int] = None,
        source_language: str = "en",
        localized_versions: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ProgressSummary:
        """Update an existing progress summary for an interview"""
        # Get existing summary
        db_summary = self.db.query(ProgressSummaryDB).filter(
            ProgressSummaryDB.medical_interview_id == interview_id
        ).first()
        
        if not db_summary:
            # Create new summary if it doesn't exist
            return self.create_progress_summary(
                interview_id,
                summary_data,
                message_id,
                source_language,
                localized_versions,
            )
        
        # Convert Pydantic schema to dict for database storage
        summary_dict = summary_data.model_dump()
        
        # Update fields
        db_summary.age = summary_dict.get('age')
        db_summary.weight_in_kg = summary_dict.get('weight_in_kg')
        db_summary.current_symptoms = summary_dict.get('current_symptoms')
        db_summary.allergies = summary_dict.get('allergies')
        db_summary.medications = summary_dict.get('medications')
        db_summary.diet_information = summary_dict.get('diet_information')
        db_summary.current_illnesses = summary_dict.get('current_illnesses')
        db_summary.family_history = summary_dict.get('family_history')
        db_summary.habits = summary_dict.get('habits')
        db_summary.medical_history = summary_dict.get('medical_history')
        db_summary.work_information = summary_dict.get('work_information')
        db_summary.summary_text = summary_dict.get('summary_text')
        db_summary.source_language = source_language
        db_summary.localized_versions = localized_versions or {}
        db_summary.last_updated_message_id = message_id
        db_summary.update_count += 1
        #db_summary.updated_at = datetime.now(timezone.utc)
        
        self.db.commit()
        self.db.refresh(db_summary)
        
        return ProgressSummary.model_validate(db_summary)

    def cache_localized_summary(
        self,
        interview_id: int,
        language: str,
        summary_data: ProgressSummarySchema,
    ) -> ProgressSummary:
        """Persist one translated summary without changing the canonical fields."""
        db_summary = self.get_progress_summary_record(interview_id)
        if not db_summary:
            raise ValueError(f"Progress summary not found for interview {interview_id}")

        localized_versions = dict(db_summary.localized_versions or {})
        localized_versions[language] = summary_data.model_dump()
        db_summary.localized_versions = localized_versions
        self.db.commit()
        self.db.refresh(db_summary)
        return ProgressSummary.model_validate(db_summary)
    
    def delete_progress_summary(self, interview_id: int) -> bool:
        """Delete the progress summary for an interview"""
        summary = self.db.query(ProgressSummaryDB).filter(
            ProgressSummaryDB.medical_interview_id == interview_id
        ).first()
        
        if summary:
            self.db.delete(summary)
            self.db.commit()
            return True
        
        return False
    
    async def store_summary_async(
        self, 
        interview_id: int, 
        summary_data: ProgressSummarySchema,
        message_id: Optional[int] = None
    ) -> ProgressSummary:
        """Async wrapper for storing progress summary"""
        # For now, we'll use the sync method since SQLAlchemy operations are sync
        # In a real async implementation, you'd use async SQLAlchemy
        return self.update_progress_summary(interview_id, summary_data, message_id)
