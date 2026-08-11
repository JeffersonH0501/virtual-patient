"""
Data normalization helpers for the virtual patient agent system.
"""

from typing import Dict, Any


def normalize_summary_data(data: dict) -> dict:
    """
    Normalize summary data to ensure it matches the ProgressSummarySchema format.
    Converts single dictionaries to lists where required.
    
    Args:
        data: Dictionary containing summary data that may have incorrect types
        
    Returns:
        Dictionary with normalized data types matching the schema requirements
    """
    normalized = data.copy()
    
    # Ensure current_symptoms is a list of SymptomSchema objects
    if 'current_symptoms' in normalized and normalized['current_symptoms']:
        if isinstance(normalized['current_symptoms'], dict):
            # Convert single dict to list
            normalized['current_symptoms'] = [normalized['current_symptoms']]
        elif not isinstance(normalized['current_symptoms'], list):
            normalized['current_symptoms'] = []
        
        # Ensure each symptom has required "symptom" field
        for i, symptom in enumerate(normalized['current_symptoms']):
            if isinstance(symptom, dict) and 'symptom' not in symptom:
                # If symptom field is missing, try to infer from other fields
                if 'name' in symptom:
                    symptom['symptom'] = symptom.pop('name')
                elif 'description' in symptom:
                    symptom['symptom'] = symptom.pop('description')
                else:
                    # Remove invalid symptom entries
                    normalized['current_symptoms'][i] = None
        
        # Remove None entries
        normalized['current_symptoms'] = [s for s in normalized['current_symptoms'] if s is not None]
    
    # Ensure current_illnesses is a list of IllnessSchema objects
    if 'current_illnesses' in normalized and normalized['current_illnesses']:
        if isinstance(normalized['current_illnesses'], dict):
            # Convert single dict to list
            normalized['current_illnesses'] = [normalized['current_illnesses']]
        elif not isinstance(normalized['current_illnesses'], list):
            normalized['current_illnesses'] = []
        
        # Ensure each illness has required "illness" field
        for i, illness in enumerate(normalized['current_illnesses']):
            if isinstance(illness, dict) and 'illness' not in illness:
                # If illness field is missing, try to infer from other fields
                if 'name' in illness:
                    illness['illness'] = illness.pop('name')
                elif 'condition' in illness:
                    illness['illness'] = illness.pop('condition')
                elif 'disease' in illness:
                    illness['illness'] = illness.pop('disease')
                else:
                    # Remove invalid illness entries
                    normalized['current_illnesses'][i] = None
        
        # Remove None entries
        normalized['current_illnesses'] = [i for i in normalized['current_illnesses'] if i is not None]
    
    # Ensure allergies is a list of strings
    if 'allergies' in normalized and normalized['allergies']:
        if isinstance(normalized['allergies'], str):
            # Convert single string to list
            normalized['allergies'] = [normalized['allergies']]
        elif isinstance(normalized['allergies'], dict):
            # Convert single dict to list of strings (extract values or keys)
            if 'name' in normalized['allergies']:
                normalized['allergies'] = [normalized['allergies']['name']]
            elif 'allergy' in normalized['allergies']:
                normalized['allergies'] = [normalized['allergies']['allergy']]
            else:
                normalized['allergies'] = [str(v) for v in normalized['allergies'].values() if v]
        elif isinstance(normalized['allergies'], list):
            # Ensure all items in the list are strings
            normalized['allergies'] = [str(item) if not isinstance(item, str) else item for item in normalized['allergies']]
        else:
            normalized['allergies'] = []
    
    # Ensure diet_information is a string
    if 'diet_information' in normalized and normalized['diet_information']:
        if isinstance(normalized['diet_information'], dict):
            # Convert dict to string (join values or use description field)
            if 'description' in normalized['diet_information']:
                normalized['diet_information'] = normalized['diet_information']['description']
            else:
                normalized['diet_information'] = ' '.join([str(v) for v in normalized['diet_information'].values() if v])
        elif isinstance(normalized['diet_information'], list):
            # Convert list to string (join items)
            normalized['diet_information'] = ' '.join([str(item) for item in normalized['diet_information'] if item])
        elif not isinstance(normalized['diet_information'], str):
            normalized['diet_information'] = str(normalized['diet_information'])
    
    # Ensure family_history is a list of FamilyHistorySchema objects
    if 'family_history' in normalized and normalized['family_history']:
        if isinstance(normalized['family_history'], dict):
            # Convert single dict to list
            normalized['family_history'] = [normalized['family_history']]
        elif isinstance(normalized['family_history'], str):
            # Convert string to list with basic structure
            # This is a fallback for backward compatibility
            normalized['family_history'] = [{
                'relationship': 'Unknown',
                'condition': normalized['family_history'],
                'notes': 'Converted from string format'
            }]
        elif not isinstance(normalized['family_history'], list):
            normalized['family_history'] = []

        
        # Remove None entries
        normalized['family_history'] = [entry for entry in normalized['family_history'] if entry is not None]
    
    # Ensure medications is a list of MedicationSchema objects
    if 'medications' in normalized and normalized['medications']:
        if isinstance(normalized['medications'], dict):
            # Convert single dict to list
            normalized['medications'] = [normalized['medications']]
        elif not isinstance(normalized['medications'], list):
            normalized['medications'] = []
        
        # Ensure each medication has required "medication" field
        for i, medication in enumerate(normalized['medications']):
            if isinstance(medication, dict) and 'medication' not in medication:
                # If medication field is missing, try to infer from other fields
                if 'name' in medication:
                    medication['medication'] = medication.pop('name')
                elif 'drug' in medication:
                    medication['medication'] = medication.pop('drug')
                else:
                    # Remove invalid medication entries
                    normalized['medications'][i] = None
        
        # Remove None entries
        normalized['medications'] = [m for m in normalized['medications'] if m is not None]
    
    return normalized
