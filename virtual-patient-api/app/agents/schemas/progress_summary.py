from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class SymptomSchema(BaseModel):
    """Schema for individual symptom"""
    symptom: str = Field(..., description="Name of the symptom")
    status: Optional[str] = Field(None, description="Status of the symptom (Active, Resolved, etc.)")
    severity: Optional[str] = Field(None, description="Severity of the symptom")
    onset: Optional[str] = Field(None, description="When the symptom started")
    location: Optional[str] = Field(None, description="Location of the symptom")
    triggers: Optional[str] = Field(None, description="What triggers the symptom")

class MedicationSchema(BaseModel):
    """Schema for individual medication"""
    medication: str = Field(..., description="Name of the medication")
    duration: Optional[str] = Field(None, description="How long taking the medication")
    frequency: Optional[str] = Field(None, description="How often taking the medication")
    dosage: Optional[str] = Field(None, description="Dosage of the medication")
    purpose: Optional[str] = Field(None, description="Purpose or reason for taking the medication")

class IllnessSchema(BaseModel):
    """Schema for individual illness/medical condition"""
    illness: str = Field(..., description="Name of the illness or medical condition")
    status: Optional[str] = Field(None, description="Status of the illness (Active, Controlled, Resolved, etc.)")
    diagnosis_date: Optional[str] = Field(None, description="When the illness was diagnosed")
    severity: Optional[str] = Field(None, description="Severity of the illness")
    treatment: Optional[str] = Field(None, description="Current treatment for the illness")
    notes: Optional[str] = Field(None, description="Additional notes about the illness")

class FamilyHistorySchema(BaseModel):
    """Schema for individual family history entry"""
    relationship: str = Field(..., description="Relationship to patient (e.g., 'Father', 'Mother', 'Maternal Grandmother')")
    condition: str = Field(..., description="Medical condition or disease")
    notes: Optional[str] = Field(None, description="Additional notes about the family member's condition")

class HabitSchema(BaseModel):
    """Schema for individual habit"""
    habit: str = Field(..., description="Name of the habit (e.g., 'smoking', 'drinking', 'exercising', 'workaholism', etc.)")
    duration: Optional[str] = Field(None, description="How long the patient has had this habit")
    frequency: Optional[str] = Field(None, description="How often the patient engages in this habit")

class MedicalHistorySchema(BaseModel):
    """Schema for individual medical history event"""
    type: str = Field(..., description="Type of medical history event (e.g., 'surgery', 'accident', 'hospitalization', 'procedure', 'injury', etc.)")
    date: Optional[str] = Field(None, description="When the event occurred (approximate time, a year ago, 2 years ago, etc.)")
 
class ProgressSummarySchema(BaseModel):
    """Schema for medical interview progress summary"""
    
    # Patient Demographics
    age: Optional[int] = Field(None, description="Patient's age")

    weight_in_kg: Optional[float] = Field(None, description="Patient's weight in kilograms")
    
    # Current Symptoms
    current_symptoms: Optional[List[SymptomSchema]] = Field(
        None, 
        description="List of current symptoms with details"
    )
    
    # Allergies
    allergies: Optional[List[str]] = Field(
        None, 
        description="List of allergies as simple strings"
    )
    
    # Medications
    medications: Optional[List[MedicationSchema]] = Field(
        None, 
        description="List of medications with details"
    )
    
    # Diet Information
    diet_information: Optional[str] = Field(
        None, 
        description="Description of dietary restrictions, meals, supplements, eating habits"
    )
    
    # Current Illnesses
    current_illnesses: Optional[List[IllnessSchema]] = Field(
        None, 
        description="Current medical conditions and their status"
    )
    
    # Family History
    family_history: Optional[List[FamilyHistorySchema]] = Field(
        None, 
        description="List of family medical history entries with structured information"
    )
    
    # Summary Text
    summary_text: Optional[str] = Field(
        None, 
        description="Overall summary of the interview progress and key findings"
    )

    habits: Optional[List[HabitSchema]] = Field(
        None, 
        description="List of habits the patient has with details (habit name, duration, frequency)"
    )

    work_information: Optional[str] = Field(
        None, 
        description="Short description of the patient's work"
    )

    medical_history: Optional[List[MedicalHistorySchema]] = Field(
        None, 
        description="List of medical history events with details (surgeries, accidents, hospitalizations, procedures, etc.)"
    )
