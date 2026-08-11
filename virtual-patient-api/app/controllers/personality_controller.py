from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_
from fastapi import HTTPException, status
from app.models.personality import PersonalityDB, Personality, PersonalityCreate, PersonalityUpdate, PersonalityListResponse

class PersonalityController:
    def __init__(self, db: Session):
        self.db = db
    
    def create_personality(self, personality_data: PersonalityCreate) -> Personality:
        """Create a new personality"""
        # Check if namespace_key already exists
        existing = self.db.query(PersonalityDB).filter(
            PersonalityDB.namespace_key == personality_data.namespace_key
        ).first()
        
        if existing:
            raise ValueError(f"Personality with namespace_key '{personality_data.namespace_key}' already exists")
        
        personality = PersonalityDB(
            name=personality_data.name,
            namespace_key=personality_data.namespace_key,
            description=personality_data.description,
            name_translations=personality_data.name_translations or {}
        )

        self.db.add(personality)
        self.db.commit()
        self.db.refresh(personality)

        return Personality.from_orm(personality)

    def get_personality(self, personality_id: int) -> Optional[Personality]:
        """Get personality by ID"""
        personality = self.db.query(PersonalityDB).filter(PersonalityDB.id == personality_id).first()
        return Personality.from_orm(personality) if personality else None
    
    def get_personality_by_namespace_key(self, namespace_key: str) -> Optional[Personality]:
        """Get personality by namespace key"""
        personality = self.db.query(PersonalityDB).filter(PersonalityDB.namespace_key == namespace_key).first()
        return Personality.from_orm(personality) if personality else None

    def get_all_personalities(self, skip: int = 0, limit: int = 100) -> List[Personality]:
        """Get all personalities with pagination"""
        personalities = self.db.query(PersonalityDB).offset(skip).limit(limit).all()
        return [Personality.from_orm(personality) for personality in personalities]

    def update_personality(self, personality_id: int, personality_data: PersonalityUpdate) -> Optional[Personality]:
        """Update personality"""
        personality = self.db.query(PersonalityDB).filter(PersonalityDB.id == personality_id).first()
        if not personality:
            return None
        
        # Check if namespace_key is being updated and if it already exists
        if personality_data.namespace_key and personality_data.namespace_key != personality.namespace_key:
            existing = self.db.query(PersonalityDB).filter(
                and_(
                    PersonalityDB.namespace_key == personality_data.namespace_key,
                    PersonalityDB.id != personality_id
                )
            ).first()
            
            if existing:
                raise ValueError(f"Personality with namespace_key '{personality_data.namespace_key}' already exists")
        
        # Update fields
        update_data = personality_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(personality, field, value)

        self.db.commit()
        self.db.refresh(personality)

        return Personality.from_orm(personality)

    def delete_personality(self, personality_id: int) -> bool:
        """Delete personality"""
        personality = self.db.query(PersonalityDB).filter(PersonalityDB.id == personality_id).first()
        if not personality:
            return False
        
        self.db.delete(personality)
        self.db.commit()
        return True

    def search_personalities(self, query: str, skip: int = 0, limit: int = 100) -> List[Personality]:
        """Search personalities by name or description"""
        personalities = self.db.query(PersonalityDB).filter(
            PersonalityDB.name.ilike(f"%{query}%") | 
            PersonalityDB.description.ilike(f"%{query}%")
        ).offset(skip).limit(limit).all()
        
        return [Personality.from_orm(personality) for personality in personalities]

    def _get_translated_name(self, personality: PersonalityDB, preferred_language: str = "en") -> str:
        """Get the name in the preferred language, fallback to default name"""
        if not personality.name_translations or preferred_language == "en":
            return personality.name
        
        translated_name = personality.name_translations.get(preferred_language)
        return translated_name if translated_name else personality.name
    
    @staticmethod
    def translate_personality_name_in_dict(personality_data: Dict[str, Any], preferred_language: str = "en") -> None:
        """Translate personality name in a dictionary (modifies in place)"""
        if not personality_data:
            return
        
        name = personality_data.get('name', '')
        name_translations = personality_data.get('name_translations', {})
        
        # If no translations or language is English, keep default name
        if not name_translations or preferred_language == "en":
            return
        
        # Get translated name, fallback to default if not found
        translated_name = name_translations.get(preferred_language)
        if translated_name:
            personality_data['name'] = translated_name

    def get_all_personalities_simplified(self, preferred_language: str = "en", skip: int = 0, limit: int = 100) -> List[PersonalityListResponse]:
        """Get all personalities with simplified response (id and name only) in preferred language"""
        # Filter out confused_inquisitive personality by namespace_key
        personalities = self.db.query(PersonalityDB).filter(
            PersonalityDB.namespace_key != "confused_inquisitive"
        ).offset(skip).limit(limit).all()
        
        result = []
        for personality in personalities:
            translated_name = self._get_translated_name(personality, preferred_language)
            result.append(PersonalityListResponse(
                id=personality.id,
                name=translated_name
            ))
        
        return result

    def search_personalities_simplified(self, query: str, preferred_language: str = "en", skip: int = 0, limit: int = 100) -> List[PersonalityListResponse]:
        """Search personalities with simplified response (id and name only) in preferred language"""
        personalities = self.db.query(PersonalityDB).filter(
            PersonalityDB.namespace_key != "confused_inquisitive",
            PersonalityDB.name.ilike(f"%{query}%") | 
            PersonalityDB.description.ilike(f"%{query}%")
        ).offset(skip).limit(limit).all()
        
        result = []
        for personality in personalities:
            translated_name = self._get_translated_name(personality, preferred_language)
            result.append(PersonalityListResponse(
                id=personality.id,
                name=translated_name
            ))
        
        return result

    def get_personality_simplified(self, personality_id: int, preferred_language: str = "en") -> Optional[PersonalityListResponse]:
        """Get personality by ID with simplified response (id and name only) in preferred language"""
        personality = self.db.query(PersonalityDB).filter(PersonalityDB.id == personality_id).first()
        if not personality:
            return None
        
        translated_name = self._get_translated_name(personality, preferred_language)
        return PersonalityListResponse(
            id=personality.id,
            name=translated_name
        )

    def get_personality_by_namespace_key_simplified(self, namespace_key: str, preferred_language: str = "en") -> Optional[PersonalityListResponse]:
        """Get personality by namespace key with simplified response (id and name only) in preferred language"""
        personality = self.db.query(PersonalityDB).filter(PersonalityDB.namespace_key == namespace_key).first()
        if not personality:
            return None
        
        translated_name = self._get_translated_name(personality, preferred_language)
        return PersonalityListResponse(
            id=personality.id,
            name=translated_name
        )
