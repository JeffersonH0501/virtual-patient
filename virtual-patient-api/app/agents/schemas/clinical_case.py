"""
Schema for Clinical Case translation
"""
from typing import Optional, Dict
from pydantic import BaseModel


class ClinicalCaseTranslatableFields(BaseModel):
    """Schema for translatable fields of a clinical case"""
    title: Optional[str] = None
    description: Optional[str] = None
    chief_complaint: Optional[str] = None
    present_illness: Optional[str] = None
    personal_medical_history: Optional[str] = None
    surgical_history: Optional[str] = None
    family_history: Optional[str] = None
    medications: Optional[str] = None
    habits: Optional[str] = None
    allergies: Optional[str] = None
    concerns: Optional[str] = None
    physical_requirements: Optional[str] = None
    socioeconomic_status: Optional[str] = None
    patient_context: Optional[str] = None
    female_name: Optional[str] = None
    male_name: Optional[str] = None

