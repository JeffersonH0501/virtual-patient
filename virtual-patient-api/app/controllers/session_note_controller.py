from typing import List
from sqlalchemy.orm import Session
from app.models.medical_interview import MedicalSessionNoteDB, MedicalSessionNote


class SessionNoteController:
    def __init__(self, db: Session):
        self.db = db
    
    def get_session_notes(self, interview_id: int) -> List[MedicalSessionNote]:
        """Get all session notes for an interview"""
        notes = self.db.query(MedicalSessionNoteDB).filter(
            MedicalSessionNoteDB.interview_id == interview_id
        ).order_by(MedicalSessionNoteDB.created_at).all()
        
        return [MedicalSessionNote.from_orm(note) for note in notes]

