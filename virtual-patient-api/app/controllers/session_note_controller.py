from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.medical_interview import (
    MedicalSessionNoteDB, MedicalSessionNote, MedicalSessionNoteCreate
)


class SessionNoteController:
    def __init__(self, db: Session):
        self.db = db
    
    def create_session_note(self, interview_id: int, note_data: MedicalSessionNoteCreate) -> MedicalSessionNote:
        """Create a new session note"""
        note = MedicalSessionNoteDB(
            interview_id=interview_id,
            notes_content=note_data.notes_content
        )
        
        self.db.add(note)
        self.db.commit()
        self.db.refresh(note)
        
        return MedicalSessionNote.from_orm(note)
    
    def get_session_notes(self, interview_id: int) -> List[MedicalSessionNote]:
        """Get all session notes for an interview"""
        notes = self.db.query(MedicalSessionNoteDB).filter(
            MedicalSessionNoteDB.interview_id == interview_id
        ).order_by(MedicalSessionNoteDB.created_at).all()
        
        return [MedicalSessionNote.from_orm(note) for note in notes]
    
    def get_session_note(self, note_id: int) -> Optional[MedicalSessionNote]:
        """Get a specific session note by ID"""
        note = self.db.query(MedicalSessionNoteDB).filter(
            MedicalSessionNoteDB.id == note_id
        ).first()
        
        return MedicalSessionNote.from_orm(note) if note else None
    
    def update_session_note(self, note_id: int, notes_content: str) -> Optional[MedicalSessionNote]:
        """Update a session note"""
        note = self.db.query(MedicalSessionNoteDB).filter(
            MedicalSessionNoteDB.id == note_id
        ).first()
        
        if not note:
            return None
        
        note.notes_content = notes_content
        self.db.commit()
        self.db.refresh(note)
        
        return MedicalSessionNote.from_orm(note)
    
    def delete_session_note(self, note_id: int) -> bool:
        """Delete a session note"""
        note = self.db.query(MedicalSessionNoteDB).filter(
            MedicalSessionNoteDB.id == note_id
        ).first()
        
        if not note:
            return False
        
        self.db.delete(note)
        self.db.commit()
        return True
    
    def update_or_create_session_notes(self, interview_id: int, notes_data: List[MedicalSessionNoteCreate]) -> List[MedicalSessionNote]:
        """Update all session notes for an interview (replace existing notes)"""
        # Delete existing notes for this interview
        self.db.query(MedicalSessionNoteDB).filter(
            MedicalSessionNoteDB.interview_id == interview_id
        ).delete()
        
        # Create new notes
        notes = []
        for note_data in notes_data:
            note = self.create_session_note(interview_id, note_data)
            notes.append(note)
        
        return notes

