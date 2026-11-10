"""
Clinical Case Service
Handles database operations for clinical cases
"""
from typing import Optional, Any, Dict, List
from sqlalchemy.orm import Session
from app.models.clinical_case import (
    ClinicalCaseDB, ClinicalCase, CaseType
)
from app.utils.clinical_case_language import (
    get_clinical_case_in_language, 
    get_available_languages,
    get_translation_status,
)

class ClinicalCaseController:
    """Service for managing clinical case operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_clinical_case(self, clinical_case_id: int) -> Optional[ClinicalCaseDB]:
        """Get a clinical case by ID"""
        return self.db.query(ClinicalCaseDB).filter(ClinicalCaseDB.id == clinical_case_id).first()
    
    def get_clinical_case_summary(self, clinical_case_id: int) -> str:
        """
        Get a formatted summary of the clinical case for the virtual patient
        """
        clinical_case = self.get_clinical_case(clinical_case_id)
        
        if not clinical_case:
            return "Patient information not available"
        
        # Build a comprehensive summary from clinical case data
        summary_parts = []
        
        if clinical_case.chief_complaint:
            summary_parts.append(f"Chief complaint: {clinical_case.chief_complaint}")
        
        if clinical_case.present_illness:
            summary_parts.append(f"Present illness: {clinical_case.present_illness}")
        
        if clinical_case.family_history:
            summary_parts.append(f"Family history: {clinical_case.family_history}")
        
        if clinical_case.medications:
            summary_parts.append(f"Medications: {clinical_case.medications}")
        
        if clinical_case.allergies:
            summary_parts.append(f"Allergies: {clinical_case.allergies}")
        
        if clinical_case.personal_medical_history:
            summary_parts.append(f"Medical history: {clinical_case.personal_medical_history}")
        
        if clinical_case.habits:
            summary_parts.append(f"Habits: {clinical_case.habits}")
        
        if clinical_case.concerns:
            summary_parts.append(f"Concerns: {clinical_case.concerns}")
        
        if summary_parts:
            return ". ".join(summary_parts)
        else:
            return f"Patient: Age: {clinical_case.age or 'Unknown'}"
    
    @staticmethod
    def create_clinical_case_summary(clinical_case: ClinicalCaseDB) -> str:
        """
        Create clinical case summary from the clinical case object (SQLAlchemy model)
        This is a static helper method that doesn't require a database session
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
    
    def get_all_clinical_cases(self) -> list[ClinicalCaseDB]:
        """Get all active clinical cases"""
        return self.db.query(ClinicalCaseDB).filter(ClinicalCaseDB.active == True, ClinicalCaseDB.case_type == CaseType.DEFAULT).all()
    
    
    # Multilingual methods
    def get_clinical_case_in_language(
        self, 
        case_id: int, 
        language_code: str = "en"
    ) -> Optional[ClinicalCase]:
        """
        Get clinical case in the specified language
        
        Args:
            case_id: Clinical case ID
            language_code: Language code (e.g., 'en', 'es')
            
        Returns:
            Clinical case data in the requested language
        """
        clinical_case = self.get_clinical_case(case_id)
        if not clinical_case:
            return None
        
        # Get the case data in the requested language
        case_data = get_clinical_case_in_language(clinical_case, language_code)
        
        # Convert to ClinicalCase Pydantic model
        return ClinicalCase(**case_data)
    
    def get_all_clinical_cases_in_language(
        self, 
        language_code: str = "en"
    ) -> List[ClinicalCase]:
        """
        Get all active clinical cases in the specified language
        
        Args:
            language_code: Language code (e.g., 'en', 'es')
            
        Returns:
            List of clinical case data in the requested language
        """
        clinical_cases = self.get_all_clinical_cases()
        result = []
        for case in clinical_cases:
            case_data = get_clinical_case_in_language(case, language_code)
            result.append(ClinicalCase(**case_data))
        return result
    
    
    
    def get_available_languages(self, case_id: int) -> List[str]:
        """
        Get available languages for a clinical case
        
        Args:
            case_id: Clinical case ID
            
        Returns:
            List of available language codes
        """
        clinical_case = self.get_clinical_case(case_id)
        if not clinical_case:
            return ["en"]
        
        return get_available_languages(clinical_case)
    
    def get_translation_status(self, case_id: int) -> Dict[str, Any]:
        """
        Get translation status for a clinical case
        
        Args:
            case_id: Clinical case ID
            
        Returns:
            Dictionary with translation status information
        """
        clinical_case = self.get_clinical_case(case_id)
        if not clinical_case:
            return {}
        
        return get_translation_status(clinical_case)
