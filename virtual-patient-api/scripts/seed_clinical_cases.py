#!/usr/bin/env python3
"""
Seed clinical cases in the database using the new multilingual structure.
- Removes existing default clinical cases
- Creates new cases with English as default and Spanish translations
"""

import sys
import json
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Import the clinical case model
from app.models.clinical_case import ClinicalCaseDB, CaseType
from app.core.config import settings

def get_database_url():
    """Return the centralized application database URL."""
    return settings.database_url

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

def seed_clinical_cases():
    """Main seeding function"""
    print("🏥 Seeding Clinical Cases")
    print("=" * 50)
    
    # Database connection
    database_url = get_database_url()
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    try:
        # Test database connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✅ Database connection successful")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False
    
    # Case names to seed
    case_names = [
        "copd",
        "diabetes", 
        "dyslipidemia",
        "hypothyroidism",
        "joint_pain"
    ]
    
    session = SessionLocal()
    
    try:
        # Step 1: Remove existing default clinical cases
        print("\n🗑️  Removing existing default clinical cases...")
        deleted_count = session.query(ClinicalCaseDB).filter(
            ClinicalCaseDB.case_type == CaseType.DEFAULT
        ).delete()
        session.commit()
        print(f"✅ Removed {deleted_count} existing default clinical cases")
        
        # Step 2: Create new cases with translations
        print("\n📝 Creating new clinical cases with translations...")
        
        for case_name in case_names:
            print(f"\n📋 Processing {case_name} case...")
            
            # Load English and Spanish data
            en_data = load_case_data(case_name, "en")
            es_data = load_case_data(case_name, "es")
            
            if not en_data:
                print(f"❌ Failed to load English data for {case_name}")
                continue
                
            if not es_data:
                print(f"❌ Failed to load Spanish data for {case_name}")
                continue
            
            # Create new clinical case with English as default
            new_case = ClinicalCaseDB(
                # Basic fields (English as default)
                title=en_data.get('title', ''),
                description=en_data.get('description', ''),
                case_type=CaseType.DEFAULT,
                organization_id=None,
                active=True,
                icon=en_data.get('icon', ''),
                age=en_data.get('age'),
                weight_in_kg=en_data.get('weight_in_kg'),
                physical_requirements=en_data.get('physical_requirements', ''),
                socioeconomic_status=en_data.get('socioeconomic_status', ''),
                female_photo=en_data.get('female_photo', ''),
                male_photo=en_data.get('male_photo', ''),
                female_name=en_data.get('female_name', ''),
                male_name=en_data.get('male_name', ''),
                patient_context=en_data.get('patient_context', ''),
                chief_complaint=en_data.get('chief_complaint', ''),
                present_illness=en_data.get('present_illness', ''),
                personal_medical_history=en_data.get('personal_medical_history', ''),
                surgical_history=en_data.get('surgical_history', ''),
                family_history=en_data.get('family_history', ''),
                medications=en_data.get('medications', ''),
                habits=en_data.get('habits', ''),
                allergies=en_data.get('allergies', ''),
                concerns=en_data.get('concerns', ''),
                
                # Translation fields (Spanish translations)
                title_translations=create_translations_dict(en_data, es_data, 'title'),
                description_translations=create_translations_dict(en_data, es_data, 'description'),
                physical_requirements_translations=create_translations_dict(en_data, es_data, 'physical_requirements'),
                socioeconomic_status_translations=create_translations_dict(en_data, es_data, 'socioeconomic_status'),
                patient_context_translations=create_translations_dict(en_data, es_data, 'patient_context'),
                female_name_translations=create_translations_dict(en_data, es_data, 'female_name'),
                male_name_translations=create_translations_dict(en_data, es_data, 'male_name'),
                chief_complaint_translations=create_translations_dict(en_data, es_data, 'chief_complaint'),
                present_illness_translations=create_translations_dict(en_data, es_data, 'present_illness'),
                personal_medical_history_translations=create_translations_dict(en_data, es_data, 'personal_medical_history'),
                surgical_history_translations=create_translations_dict(en_data, es_data, 'surgical_history'),
                family_history_translations=create_translations_dict(en_data, es_data, 'family_history'),
                medications_translations=create_translations_dict(en_data, es_data, 'medications'),
                habits_translations=create_translations_dict(en_data, es_data, 'habits'),
                allergies_translations=create_translations_dict(en_data, es_data, 'allergies'),
                concerns_translations=create_translations_dict(en_data, es_data, 'concerns'),
            )
            
            session.add(new_case)
            print(f"✅ Created {case_name} case with English default and Spanish translations")
        
        # Commit all changes
        session.commit()
        print(f"\n🎉 Successfully seeded {len(case_names)} clinical cases!")
        
        # Verify the seeding
        print("\n🔍 Verifying seeding...")
        total_cases = session.query(ClinicalCaseDB).filter(
            ClinicalCaseDB.case_type == CaseType.DEFAULT
        ).count()
        print(f"✅ Total default clinical cases in database: {total_cases}")
        
        # Show sample of created cases
        cases = session.query(ClinicalCaseDB).filter(
            ClinicalCaseDB.case_type == CaseType.DEFAULT
        ).all()
        
        print("\n📋 Created cases:")
        for case in cases:
            print(f"  - {case.title} (ID: {case.id})")
            if case.title_translations:
                print(f"    Spanish title: {case.title_translations.get('es', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Seeding failed: {e}")
        session.rollback()
        return False
        
    finally:
        session.close()

if __name__ == "__main__":
    print("🏥 Clinical Cases Seeding Script")
    print("=" * 50)
    
    success = seed_clinical_cases()
    
    if success:
        print("\n✅ Seeding completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Seeding failed!")
        sys.exit(1)
