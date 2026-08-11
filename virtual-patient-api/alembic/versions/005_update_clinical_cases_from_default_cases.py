"""Update clinical cases from default_cases

Revision ID: 005_update_clinical_cases_from_default_cases
Revises: 004_add_progress_summary_fields
Create Date: 2025-01-XX XX:XX:XX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text
from pathlib import Path
import sys
import json


# revision identifiers, used by Alembic.
revision = '005_update_clinical_cases'
down_revision = '004_add_progress_summary_fields'
branch_labels = None
depends_on = None

# Add the project root to the Python path
project_root = Path(__file__).resolve().parents[2]


def load_case_data(case_name, language):
    """Load case data from file"""
    case_file = project_root / "scripts" / "default_cases" / f"{case_name}_{language}.py"
    
    if not case_file.exists():
        print(f"❌ Case file not found: {case_file}")
        return None
    
    # Read and execute the case file to get the case dictionary
    with open(case_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Create a safe namespace for execution
    namespace = {}
    exec(content, namespace)
    
    return namespace.get('case')


def create_translations_dict(en_data, es_data, field_name):
    """Create translations dictionary for a field"""
    if not en_data or not es_data:
        return {}
    
    en_value = en_data.get(field_name, '')
    es_value = es_data.get(field_name, '')
    
    if not en_value or not es_value:
        return {}
    
    return {
        "es": es_value
    }


def upgrade() -> None:
    """Update existing clinical cases with data from default_cases"""
    # Get database connection
    connection = op.get_bind()
    
    try:
        # Case names to update
        case_names = [
            "copd",
            "diabetes", 
            "dyslipidemia",
            "hypothyroidism",
            "joint_pain"
        ]
        
        # Mapping of English titles to case names (for matching)
        title_to_case_name = {}
        for case_name in case_names:
            en_data = load_case_data(case_name, "en")
            if en_data:
                title_to_case_name[en_data.get('title', '')] = case_name
        
        # Get all default clinical cases
        result = connection.execute(text("""
            SELECT id, title 
            FROM clinical_cases 
            WHERE case_type = 'default'
        """))
        
        default_cases = result.fetchall()
        updated_count = 0
        
        for case_id, case_title in default_cases:
            # Try to match by English title
            case_name = None
            for en_title, name in title_to_case_name.items():
                if case_title == en_title:
                    case_name = name
                    break
            
            if not case_name:
                # Try to match by checking if title contains case name keywords
                title_lower = case_title.lower()
                for name in case_names:
                    if name.replace('_', ' ') in title_lower or name in title_lower:
                        case_name = name
                        break
            
            if not case_name:
                continue
            
            # Load English and Spanish data
            en_data = load_case_data(case_name, "en")
            es_data = load_case_data(case_name, "es")
            
            if not en_data or not es_data:
                continue
            
            # Prepare translation dictionaries
            title_translations = create_translations_dict(en_data, es_data, 'title')
            description_translations = create_translations_dict(en_data, es_data, 'description')
            physical_requirements_translations = create_translations_dict(en_data, es_data, 'physical_requirements')
            socioeconomic_status_translations = create_translations_dict(en_data, es_data, 'socioeconomic_status')
            patient_context_translations = create_translations_dict(en_data, es_data, 'patient_context')
            female_name_translations = create_translations_dict(en_data, es_data, 'female_name')
            male_name_translations = create_translations_dict(en_data, es_data, 'male_name')
            chief_complaint_translations = create_translations_dict(en_data, es_data, 'chief_complaint')
            present_illness_translations = create_translations_dict(en_data, es_data, 'present_illness')
            personal_medical_history_translations = create_translations_dict(en_data, es_data, 'personal_medical_history')
            surgical_history_translations = create_translations_dict(en_data, es_data, 'surgical_history')
            family_history_translations = create_translations_dict(en_data, es_data, 'family_history')
            medications_translations = create_translations_dict(en_data, es_data, 'medications')
            habits_translations = create_translations_dict(en_data, es_data, 'habits')
            allergies_translations = create_translations_dict(en_data, es_data, 'allergies')
            concerns_translations = create_translations_dict(en_data, es_data, 'concerns')
            
            # Update the case using raw SQL
            connection.execute(text("""
                UPDATE clinical_cases
                SET 
                    title = :title,
                    description = :description,
                    icon = :icon,
                    age = :age,
                    weight_in_kg = :weight_in_kg,
                    physical_requirements = :physical_requirements,
                    socioeconomic_status = :socioeconomic_status,
                    female_photo = :female_photo,
                    male_photo = :male_photo,
                    female_name = :female_name,
                    male_name = :male_name,
                    patient_context = :patient_context,
                    chief_complaint = :chief_complaint,
                    present_illness = :present_illness,
                    personal_medical_history = :personal_medical_history,
                    surgical_history = :surgical_history,
                    family_history = :family_history,
                    medications = :medications,
                    habits = :habits,
                    allergies = :allergies,
                    concerns = :concerns,
                    title_translations = CAST(:title_translations AS jsonb),
                    description_translations = CAST(:description_translations AS jsonb),
                    physical_requirements_translations = CAST(:physical_requirements_translations AS jsonb),
                    socioeconomic_status_translations = CAST(:socioeconomic_status_translations AS jsonb),
                    patient_context_translations = CAST(:patient_context_translations AS jsonb),
                    female_name_translations = CAST(:female_name_translations AS jsonb),
                    male_name_translations = CAST(:male_name_translations AS jsonb),
                    chief_complaint_translations = CAST(:chief_complaint_translations AS jsonb),
                    present_illness_translations = CAST(:present_illness_translations AS jsonb),
                    personal_medical_history_translations = CAST(:personal_medical_history_translations AS jsonb),
                    surgical_history_translations = CAST(:surgical_history_translations AS jsonb),
                    family_history_translations = CAST(:family_history_translations AS jsonb),
                    medications_translations = CAST(:medications_translations AS jsonb),
                    habits_translations = CAST(:habits_translations AS jsonb),
                    allergies_translations = CAST(:allergies_translations AS jsonb),
                    concerns_translations = CAST(:concerns_translations AS jsonb),
                    updated_at = NOW()
                WHERE id = :case_id
            """), {
                'case_id': case_id,
                'title': en_data.get('title', ''),
                'description': en_data.get('description', ''),
                'icon': en_data.get('icon', ''),
                'age': en_data.get('age'),
                'weight_in_kg': en_data.get('weight_in_kg'),
                'physical_requirements': en_data.get('physical_requirements', ''),
                'socioeconomic_status': en_data.get('socioeconomic_status', ''),
                'female_photo': en_data.get('female_photo', ''),
                'male_photo': en_data.get('male_photo', ''),
                'female_name': en_data.get('female_name', ''),
                'male_name': en_data.get('male_name', ''),
                'patient_context': en_data.get('patient_context', ''),
                'chief_complaint': en_data.get('chief_complaint', ''),
                'present_illness': en_data.get('present_illness', ''),
                'personal_medical_history': en_data.get('personal_medical_history', ''),
                'surgical_history': en_data.get('surgical_history', ''),
                'family_history': en_data.get('family_history', ''),
                'medications': en_data.get('medications', ''),
                'habits': en_data.get('habits', ''),
                'allergies': en_data.get('allergies', ''),
                'concerns': en_data.get('concerns', ''),
                'title_translations': json.dumps(title_translations),
                'description_translations': json.dumps(description_translations),
                'physical_requirements_translations': json.dumps(physical_requirements_translations),
                'socioeconomic_status_translations': json.dumps(socioeconomic_status_translations),
                'patient_context_translations': json.dumps(patient_context_translations),
                'female_name_translations': json.dumps(female_name_translations),
                'male_name_translations': json.dumps(male_name_translations),
                'chief_complaint_translations': json.dumps(chief_complaint_translations),
                'present_illness_translations': json.dumps(present_illness_translations),
                'personal_medical_history_translations': json.dumps(personal_medical_history_translations),
                'surgical_history_translations': json.dumps(surgical_history_translations),
                'family_history_translations': json.dumps(family_history_translations),
                'medications_translations': json.dumps(medications_translations),
                'habits_translations': json.dumps(habits_translations),
                'allergies_translations': json.dumps(allergies_translations),
                'concerns_translations': json.dumps(concerns_translations),
            })
            
            updated_count += 1
        
    except Exception as e:
        raise Exception(f"Migration failed: {e}")


def downgrade() -> None:
    """This migration updates data, so downgrade is not applicable"""
    # Data updates cannot be easily reversed
    pass

