from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, JSON, Text
from sqlalchemy.sql import func
from app.core.database import Base

# SQLAlchemy Model
class PersonalityDB(Base):
    __tablename__ = "personalities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    namespace_key = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Translation fields
    name_translations = Column(JSON, nullable=True, default={})

# Pydantic Models
class PersonalityBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Name of the personality")
    namespace_key: str = Field(..., min_length=1, max_length=100, description="Unique namespace key for the personality")
    description: Optional[str] = Field(None, description="Description of the personality")
    name_translations: Optional[Dict[str, str]] = Field(default_factory=dict, description="Translations for the name field")

class PersonalityCreate(PersonalityBase):
    pass

class PersonalityUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Name of the personality")
    namespace_key: Optional[str] = Field(None, min_length=1, max_length=100, description="Unique namespace key for the personality")
    description: Optional[str] = Field(None, description="Description of the personality")
    name_translations: Optional[Dict[str, str]] = Field(None, description="Translations for the name field")

class Personality(PersonalityBase):
    id: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True
        populate_by_name = True

class PersonalitySimplified(BaseModel):
    """Simplified personality model for use in other models"""
    id: int
    name: str
    namespace_key: str
    description: Optional[str] = None
    name_translations: Optional[Dict[str, str]] = Field(default_factory=dict, description="Translations for the name field")

    class Config:
        from_attributes = True
        populate_by_name = True

class PersonalityListResponse(BaseModel):
    """Simplified personality model for GET endpoints - only id and name"""
    id: int
    name: str

    class Config:
        from_attributes = True
        populate_by_name = True
