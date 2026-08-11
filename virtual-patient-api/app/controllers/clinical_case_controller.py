"""
Clinical Case Service
Handles database operations for clinical cases
"""
import traceback
from typing import Optional, Any, Dict, List, Tuple
import asyncio
from sqlalchemy.orm import Session
from app.models.clinical_case import (
    ClinicalCaseDB, ClinicalCase, ClinicalCaseBase, 
    ClinicalCaseCreate, ClinicalCaseUpdate, CaseType
)
from app.core.database import get_db
from app.utils.clinical_case_language import (
    get_clinical_case_in_language, 
    set_field_translation,
    get_available_languages,
    get_translation_status,
    TRANSLATABLE_FIELDS
)
from app.agents.translator_agent import TranslatorAgent
from app.agents.schemas.clinical_case import ClinicalCaseTranslatableFields

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
        return self.db.query(ClinicalCaseDB).filter(ClinicalCaseDB.active == True).all()
    
    def get_clinical_cases_by_organization(
        self, 
        organization_id: int, 
        current_user_id: Optional[int] = None
    ) -> list[ClinicalCaseDB]:
        """
        Get clinical cases for a specific organization
        
        Args:
            organization_id: Organization ID
            current_user_id: Current user ID (if provided, includes inactive cases created by this user)
            
        Returns:
            List of clinical cases for the organization
        """
        query = self.db.query(ClinicalCaseDB).filter(
            ClinicalCaseDB.organization_id == organization_id
        )
        
        # Filter by active status, but include inactive cases if current_user is the creator
        if current_user_id:
            query = query.filter(
                (ClinicalCaseDB.active == True) | 
                ((ClinicalCaseDB.active == False) & (ClinicalCaseDB.created_by == current_user_id))
            )
        else:
            query = query.filter(ClinicalCaseDB.active == True)
        
        return query.all()
    
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
    
    def get_clinical_cases_by_organization_in_language(
        self, 
        organization_id: int, 
        language_code: str = "en",
        current_user_id: Optional[int] = None
    ) -> List[ClinicalCase]:
        """
        Get clinical cases for a specific organization in the specified language
        
        Args:
            organization_id: Organization ID
            language_code: Language code (e.g., 'en', 'es')
            current_user_id: Current user ID (if provided, includes inactive cases created by this user)
            
        Returns:
            List of clinical case data in the requested language
        """
        clinical_cases = self.get_clinical_cases_by_organization(organization_id, current_user_id)
        result = []
        for case in clinical_cases:
            case_data = get_clinical_case_in_language(case, language_code)
            result.append(ClinicalCase(**case_data))
        return result
    
    def update_field_translation(
        self, 
        case_id: int, 
        field_name: str, 
        language_code: str, 
        translated_text: str
    ) -> Optional[ClinicalCaseDB]:
        """
        Update a specific field translation for a clinical case
        
        Args:
            case_id: Clinical case ID
            field_name: Name of the field to translate
            language_code: Target language code (e.g., 'es')
            translated_text: Translated text content
            
        Returns:
            Updated clinical case
        """
        clinical_case = self.get_clinical_case(case_id)
        if not clinical_case:
            return None
        
        set_field_translation(clinical_case, field_name, language_code, translated_text)
        self.db.commit()
        self.db.refresh(clinical_case)
        return clinical_case
    
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
    
    async def _translate_clinical_case_fields(
        self,
        translatable_data: Dict[str, Any]
    ) -> Tuple[ClinicalCaseTranslatableFields, ClinicalCaseTranslatableFields]:
        """
        Helper method to translate clinical case fields to English and Spanish in parallel
        
        Args:
            translatable_data: Dictionary of translatable field names and values
            
        Returns:
            Tuple of (english_fields, spanish_fields) - both are required
            
        Raises:
            ValueError: If no translatable data provided or translation fails
        """
        if not translatable_data:
            raise ValueError("No translatable data provided for translation")
        
        translator = TranslatorAgent()
        translatable_fields = ClinicalCaseTranslatableFields(**translatable_data)
        
        # Translate to both English and Spanish in parallel based on original input
        async def translate_to_english():
            try:
                result = await translator.translate_clinical_case_fields(
                    translatable_fields,
                    "English"
                )
                print(f"✅ Translated to English (grammar fixed)")
                # Verify that we got a valid result
                if result is None:
                    raise ValueError("English translation returned None")
                # Verify that we got actual translated values
                has_translations = False
                for field in TRANSLATABLE_FIELDS:
                    value = getattr(result, field, None)
                    if value and value.strip():
                        has_translations = True
                        break
                if not has_translations:
                    raise ValueError("English translation returned empty values for all fields")
                return result
            except Exception as e:
                print(f"❌ English translation failed: {e}")
                print(f"❌ Traceback: {traceback.format_exc()}")
                raise ValueError(f"Failed to translate clinical case to English: {str(e)}") from e
        
        async def translate_to_spanish():
            try:
                result = await translator.translate_clinical_case_fields(
                    translatable_fields,
                    "Spanish"
                )
                print(f"✅ Translated to Spanish")
                if result is None:
                    raise ValueError("Spanish translation returned None")
                return result
            except Exception as e:
                print(f"❌ Spanish translation failed: {e}")
                print(f"❌ Traceback: {traceback.format_exc()}")
                raise ValueError(f"Failed to translate clinical case to Spanish: {str(e)}") from e
        
        # Execute both translations in parallel
        english_fields, spanish_fields = await asyncio.gather(
            translate_to_english(),
            translate_to_spanish()
        )
        
        return english_fields, spanish_fields
    
    def _apply_translations_to_data(
        self,
        target_data: Dict[str, Any],
        english_fields: ClinicalCaseTranslatableFields,
        spanish_fields: ClinicalCaseTranslatableFields,
        fields_to_update: Optional[set] = None,
        existing_translations: Optional[Dict[str, Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Helper method to apply English and Spanish translations to a data dictionary
        
        Args:
            target_data: Target data dictionary to update
            english_fields: Translated English fields (grammar fixed) - REQUIRED
            spanish_fields: Translated Spanish fields - REQUIRED
            fields_to_update: Optional set of field names to update (if None, updates all fields)
            existing_translations: Optional dict of existing translations to merge with (for updates)
            
        Returns:
            Updated data dictionary with English in base fields and Spanish in translations
            
        Raises:
            ValueError: If english_fields or spanish_fields are None or invalid
        """
        if english_fields is None:
            raise ValueError("English translation is required but was None")
        if spanish_fields is None:
            raise ValueError("Spanish translation is required but was None")
        
        result_data = target_data.copy()
        
        # Determine which fields to update
        fields_to_process = fields_to_update if fields_to_update is not None else set(TRANSLATABLE_FIELDS)
        
        # Update base fields with English translations (grammar fixed)
        for field in TRANSLATABLE_FIELDS:
            if field in fields_to_process:
                english_value = getattr(english_fields, field, None)
                if english_value and english_value.strip():
                    result_data[field] = english_value
                else:
                    # If English translation is missing for a field that had original data, log warning
                    original_value = target_data.get(field)
                    if original_value:
                        print(f"⚠️ Warning: English translation for {field} is empty, but original value exists")
        
        # Add Spanish translation dictionaries
        for field in TRANSLATABLE_FIELDS:
            if field in fields_to_process:
                translation_key = f"{field}_translations"
                spanish_value = getattr(spanish_fields, field, None)
                
                if spanish_value and spanish_value.strip():
                    # If updating and existing translations provided, merge with them
                    if existing_translations and translation_key in existing_translations:
                        merged_translations = existing_translations[translation_key].copy()
                        merged_translations["es"] = spanish_value
                        result_data[translation_key] = merged_translations
                    else:
                        # For new cases, create new translation dict
                        result_data[translation_key] = {"es": spanish_value}
                else:
                    # If updating and existing translations provided, keep them
                    if existing_translations and translation_key in existing_translations:
                        result_data[translation_key] = existing_translations[translation_key]
                    else:
                        result_data[translation_key] = {}
        
        return result_data
    
    def _build_case_data_with_translations(
        self,
        base_data: Dict[str, Any],
        english_fields: ClinicalCaseTranslatableFields,
        spanish_fields: ClinicalCaseTranslatableFields
    ) -> Dict[str, Any]:
        """
        Helper method to build case data with English base fields and Spanish translations
        
        Args:
            base_data: Base case data dictionary
            english_fields: Translated English fields (grammar fixed) - REQUIRED
            spanish_fields: Translated Spanish fields - REQUIRED
            
        Returns:
            Case data dictionary with English in base fields and Spanish in translations
            
        Raises:
            ValueError: If english_fields or spanish_fields are None or invalid
        """
        return self._apply_translations_to_data(
            base_data,
            english_fields,
            spanish_fields,
            fields_to_update=None,  # Update all fields
            existing_translations=None  # No existing translations for new cases
        )
    
    async def create_clinical_case_with_translations(
        self,
        clinical_case: ClinicalCaseCreate,
        created_by_user_id: Optional[int] = None
    ) -> ClinicalCaseDB:
        """
        Create a clinical case with automatic translation to English and Spanish
        
        Args:
            clinical_case: Clinical case data to create
            created_by_user_id: User ID who created the case (only for custom cases)
            
        Returns:
            Created clinical case with translations
        """
        # Extract translatable fields
        translatable_data = {}
        for field in TRANSLATABLE_FIELDS:
            value = getattr(clinical_case, field, None)
            if value:
                translatable_data[field] = value
        
        # Translate fields to English and Spanish
        if not translatable_data:
            raise ValueError("Cannot create clinical case: no translatable fields provided")
        
        print(f"🔄 Starting translation for clinical case...")
        print(f"📝 Original translatable data keys: {list(translatable_data.keys())}")
        
        try:
            english_fields, spanish_fields = await self._translate_clinical_case_fields(translatable_data)
        except ValueError as e:
            print(f"❌ Translation failed: {e}")
            raise ValueError(f"Failed to translate clinical case: {str(e)}") from e
        
        # Log translation results
        print(f"✅ English translation received")
        for field in TRANSLATABLE_FIELDS:
            value = getattr(english_fields, field, None)
        
        print(f"✅ Spanish translation received")
        for field in TRANSLATABLE_FIELDS:
            value = getattr(spanish_fields, field, None)
        
        # Build case data with English in base fields and Spanish in translations
        base_data = clinical_case.dict(exclude={f"{field}_translations" for field in TRANSLATABLE_FIELDS})
        # ID will be auto-generated by the database
        
        # Set active=False for custom cases by default
        if clinical_case.case_type == CaseType.CUSTOM:
            base_data['active'] = False
            if created_by_user_id:
                base_data['created_by'] = created_by_user_id
        
        case_data = self._build_case_data_with_translations(base_data, english_fields, spanish_fields)
        
        db_case = ClinicalCaseDB(**case_data)
        self.db.add(db_case)
        self.db.commit()
        self.db.refresh(db_case)
        
        return db_case
    
    async def update_clinical_case_with_translations(
        self,
        case_id: int,
        case_update: ClinicalCaseUpdate
    ) -> Optional[ClinicalCaseDB]:
        """
        Update a clinical case with automatic translation to English and Spanish
        
        Args:
            case_id: Clinical case ID to update
            case_update: Clinical case update data
            
        Returns:
            Updated clinical case with translations, or None if not found
        """
        db_case = self.db.query(ClinicalCaseDB).filter(ClinicalCaseDB.id == case_id).first()
        if db_case is None:
            return None
        
        # Get update data
        update_data = case_update.dict(exclude_unset=True)

        # Check which translatable fields are being updated
        updated_translatable_fields = {}
        for field in TRANSLATABLE_FIELDS:
            if field in update_data and update_data[field] is not None:
                updated_translatable_fields[field] = update_data[field]
        
        # Translate updated fields to English and Spanish (only if there are fields to translate)
        if updated_translatable_fields:
            try:
                english_fields, spanish_fields = await self._translate_clinical_case_fields(updated_translatable_fields)
            except ValueError as e:
                print(f"❌ Translation failed during update: {e}")
                raise ValueError(f"Failed to translate clinical case updates: {str(e)}") from e
            
            # Get existing translations from the database case
            existing_translations = {}
            for field in TRANSLATABLE_FIELDS:
                if field in updated_translatable_fields:
                    translation_key = f"{field}_translations"
                    existing_translations[translation_key] = getattr(db_case, translation_key, {}) or {}
            
            # Apply translations to update_data using the shared helper method
            update_data = self._apply_translations_to_data(
                update_data,
                english_fields,
                spanish_fields,
                fields_to_update=set(updated_translatable_fields.keys()),
                existing_translations=existing_translations
            )
        
        # Update only provided fields
        for field, value in update_data.items():
            setattr(db_case, field, value)
        
        self.db.commit()
        self.db.refresh(db_case)
        return db_case
