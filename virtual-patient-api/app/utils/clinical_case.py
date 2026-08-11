"""
Clinical case utility functions
"""

from app.models.clinical_case import ClinicalCaseDB


def create_clinical_case_summary(clinical_case: ClinicalCaseDB) -> str:
    """
    Create clinical case summary from the clinical case object (SQLAlchemy model)
    This is a utility function that doesn't require a database session
    
    Args:
        clinical_case: ClinicalCaseDB object
        
    Returns:
        Formatted string summary of the clinical case
    """
    try:
        if not clinical_case:
            return "Patient information not available"
        
        # Build a comprehensive summary from clinical case data
        summary_parts = []
        
        # Basic patient information
        if clinical_case.age:
            summary_parts.append(f"Age: {clinical_case.age} years old")
        
        if clinical_case.weight_in_kg:
            summary_parts.append(f"Weight: {clinical_case.weight_in_kg} kg")
        
        if clinical_case.description and clinical_case.description.strip():
            summary_parts.append(f"Description: {clinical_case.description}")
        
        # Medical information
        if clinical_case.chief_complaint and clinical_case.chief_complaint.strip():
            summary_parts.append(f"Chief complaint: {clinical_case.chief_complaint}")
        
        if clinical_case.present_illness and clinical_case.present_illness.strip():
            summary_parts.append(f"Present illness: {clinical_case.present_illness}")
        
        if clinical_case.personal_medical_history and clinical_case.personal_medical_history.strip():
            summary_parts.append(f"Medical history: {clinical_case.personal_medical_history}")
        
        if clinical_case.surgical_history and clinical_case.surgical_history.strip():
            summary_parts.append(f"Surgical history: {clinical_case.surgical_history}")
        
        if clinical_case.family_history and clinical_case.family_history.strip():
            summary_parts.append(f"Family history: {clinical_case.family_history}")
        
        if clinical_case.medications and clinical_case.medications.strip():
            summary_parts.append(f"Medications: {clinical_case.medications}")
        
        if clinical_case.allergies and clinical_case.allergies.strip():
            summary_parts.append(f"Allergies: {clinical_case.allergies}")
        
        if clinical_case.habits and clinical_case.habits.strip():
            summary_parts.append(f"Habits: {clinical_case.habits}")
        
        # Social and contextual information
        if clinical_case.socioeconomic_status and clinical_case.socioeconomic_status.strip():
            summary_parts.append(f"Socioeconomic status: {clinical_case.socioeconomic_status}")
        
        
        if clinical_case.patient_context and clinical_case.patient_context.strip():
            summary_parts.append(f"Patient context: {clinical_case.patient_context}")
        
        if clinical_case.physical_requirements and clinical_case.physical_requirements.strip():
            summary_parts.append(f"Physical requirements: {clinical_case.physical_requirements}")
        
        if clinical_case.concerns and clinical_case.concerns.strip():
            summary_parts.append(f"Concerns: {clinical_case.concerns}")
        
        if summary_parts:
            return ". ".join(summary_parts)
        else:
            return "Patient information not available"
            
    except Exception as e:
        return "Patient information not available"
