from __future__ import annotations
from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime
from sqlalchemy import Boolean, Column, String, DateTime, Text, ForeignKey, Enum, Float, Integer, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum

# Enum for case types
class CaseType(str, enum.Enum):
    DEFAULT = "default"
    CUSTOM = "custom"

# SQLAlchemy Model
class ClinicalCaseDB(Base):
    __tablename__ = "clinical_cases"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    case_key = Column(String, nullable=True)  # Unique key for default cases (e.g., 'diabetes', 'copd')
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)  # Description shown in UI
    case_type = Column(Enum(CaseType, name='case_type', values_callable=lambda obj: [e.value for e in obj]), nullable=False, default=CaseType.DEFAULT)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    active = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Only for custom cases
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    icon = Column(String, nullable=True)  # Icon name for the case
    age = Column(Integer, nullable=True)
    weight_in_kg = Column(Float, nullable=True)  # Patient weight in kilograms
    physical_requirements = Column(String, nullable=True)
    socioeconomic_status = Column(String, nullable=True)
    female_photo = Column(String, nullable=True)
    male_photo = Column(String, nullable=True)
    female_name = Column(String, nullable=True)
    male_name = Column(String, nullable=True)
    gender_restriction = Column(String, nullable=True)  # Optional: "male", "female", or None (both allowed)
    patient_context = Column(String, nullable=True)
    chief_complaint = Column(String, nullable=True)
    present_illness = Column(String, nullable=True)
    personal_medical_history = Column(String, nullable=True)
    surgical_history = Column(String, nullable=True)
    family_history = Column(String, nullable=True)
    medications = Column(String, nullable=True)
    habits = Column(String, nullable=True)
    allergies = Column(String, nullable=True)
    concerns = Column(String, nullable=True)

    # Translation columns for multilingual support
    title_translations = Column(JSON, nullable=True, default={})
    description_translations = Column(JSON, nullable=True, default={})
    chief_complaint_translations = Column(JSON, nullable=True, default={})
    present_illness_translations = Column(JSON, nullable=True, default={})
    personal_medical_history_translations = Column(JSON, nullable=True, default={})
    surgical_history_translations = Column(JSON, nullable=True, default={})
    family_history_translations = Column(JSON, nullable=True, default={})
    medications_translations = Column(JSON, nullable=True, default={})
    habits_translations = Column(JSON, nullable=True, default={})
    allergies_translations = Column(JSON, nullable=True, default={})
    concerns_translations = Column(JSON, nullable=True, default={})
    physical_requirements_translations = Column(JSON, nullable=True, default={})
    socioeconomic_status_translations = Column(JSON, nullable=True, default={})
    patient_context_translations = Column(JSON, nullable=True, default={})
    female_name_translations = Column(JSON, nullable=True, default={})
    male_name_translations = Column(JSON, nullable=True, default={})

    # Relationship to organization (only for custom cases)
    organization = relationship("OrganizationDB", back_populates="clinical_cases")
    
    # Relationship to user who created the case (only for custom cases)
    creator = relationship("UserDB", foreign_keys=[created_by])

# Pydantic Models
class ClinicalCaseBase(BaseModel):
    case_key: Optional[str] = None  # Unique key for default cases (e.g., 'diabetes', 'copd')
    title: str
    description: str
    case_type: CaseType = CaseType.DEFAULT
    organization_id: Optional[int] = None
    active: Optional[bool] = False
    created_by: Optional[int] = None  # Only for custom cases
    icon: Optional[str] = None
    age: Optional[int] = None
    weight_in_kg: Optional[float] = None
    physical_requirements: Optional[str] = None
    socioeconomic_status: Optional[str] = None
    female_photo: Optional[str] = None
    male_photo: Optional[str] = None
    female_name: Optional[str] = None
    male_name: Optional[str] = None
    gender_restriction: Optional[str] = None  # Optional: "male", "female", or None (both allowed)
    patient_context: Optional[str] = None
    chief_complaint: Optional[str] = None
    present_illness: Optional[str] = None
    personal_medical_history: Optional[str] = None
    surgical_history: Optional[str] = None
    family_history: Optional[str] = None
    medications: Optional[str] = None
    habits: Optional[str] = None
    allergies: Optional[str] = None
    concerns: Optional[str] = None

    # Translation fields
    title_translations: Optional[Dict[str, str]] = {}
    description_translations: Optional[Dict[str, str]] = {}
    chief_complaint_translations: Optional[Dict[str, str]] = {}
    present_illness_translations: Optional[Dict[str, str]] = {}
    personal_medical_history_translations: Optional[Dict[str, str]] = {}
    surgical_history_translations: Optional[Dict[str, str]] = {}
    family_history_translations: Optional[Dict[str, str]] = {}
    medications_translations: Optional[Dict[str, str]] = {}
    habits_translations: Optional[Dict[str, str]] = {}
    allergies_translations: Optional[Dict[str, str]] = {}
    concerns_translations: Optional[Dict[str, str]] = {}
    physical_requirements_translations: Optional[Dict[str, str]] = {}
    socioeconomic_status_translations: Optional[Dict[str, str]] = {}
    patient_context_translations: Optional[Dict[str, str]] = {}
    female_name_translations: Optional[Dict[str, str]] = {}
    male_name_translations: Optional[Dict[str, str]] = {}

class ClinicalCaseCreate(ClinicalCaseBase):
    pass

class ClinicalCaseUpdate(BaseModel):
    case_key: Optional[str] = None  # Unique key for default cases (e.g., 'diabetes', 'copd')
    title: Optional[str] = None
    description: Optional[str] = None
    case_type: Optional[CaseType] = None
    organization_id: Optional[int] = None
    active: Optional[bool] = None
    created_by: Optional[int] = None  # Only for custom cases
    icon: Optional[str] = None
    age: Optional[int] = None
    weight_in_kg: Optional[float] = None
    physical_requirements: Optional[str] = None
    socioeconomic_status: Optional[str] = None
    # New fields for gender-specific data
    female_photo: Optional[str] = None
    male_photo: Optional[str] = None
    female_name: Optional[str] = None
    male_name: Optional[str] = None
    gender_restriction: Optional[str] = None  # Optional: "male", "female", or None (both allowed)
    patient_context: Optional[str] = None
    chief_complaint: Optional[str] = None
    present_illness: Optional[str] = None
    personal_medical_history: Optional[str] = None
    surgical_history: Optional[str] = None
    family_history: Optional[str] = None
    medications: Optional[str] = None
    habits: Optional[str] = None
    allergies: Optional[str] = None
    concerns: Optional[str] = None

class CreatedByUser(BaseModel):
    """User who created the clinical case (only for custom cases)"""
    id: int
    first_name: str
    last_name: str
    
    class Config:
        from_attributes = True

class ClinicalCase(ClinicalCaseBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by_user: Optional[CreatedByUser] = None  # Populated from creator relationship

    class Config:
        from_attributes = True

class ClinicalCaseSimplified(BaseModel):
    """Simplified clinical case model with only essential fields"""
    id: int
    case_key: Optional[str] = None  # Unique key for default cases (e.g., 'diabetes', 'copd')
    title: str
    description: str
    case_type: CaseType
    organization_id: Optional[int] = None
    active: bool
    icon: Optional[str] = None
    age: Optional[int] = None
    weight_in_kg: Optional[float] = None
    female_photo: Optional[str] = None
    male_photo: Optional[str] = None
    female_name: Optional[str] = None
    male_name: Optional[str] = None
    gender_restriction: Optional[str] = None

    class Config:
        from_attributes = True

class ClinicalCaseWithOrganization(ClinicalCase):
    organization: Optional["Organization"] = None

    class Config:
        from_attributes = True

# Import here to avoid circular imports
from app.models.organization import Organization

ClinicalCaseWithOrganization.model_rebuild() 