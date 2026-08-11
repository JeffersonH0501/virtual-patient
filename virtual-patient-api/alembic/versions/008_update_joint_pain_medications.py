"""Update medications field for joint_pain case

Revision ID: 008_update_joint_pain_medications
Revises: 007_add_gender_restriction
Create Date: 2025-11-09 11:40:57

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from pathlib import Path
import json


# revision identifiers, used by Alembic.
revision = '008_joint_pain_meds'
down_revision = '007_add_gender_restriction'
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


def upgrade() -> None:
    """Update medications field for joint_pain case"""
    # Get database connection
    connection = op.get_bind()
    
    try:
        # Load English and Spanish data for joint_pain case
        en_data = load_case_data("joint_pain", "en")
        es_data = load_case_data("joint_pain", "es")
        
        if not en_data or not es_data:
            print("❌ Failed to load joint_pain case data")
            return
        
        # Get medications values
        medications_en = en_data.get('medications', '')
        medications_es = es_data.get('medications', '')
        
        if not medications_en or not medications_es:
            print("❌ Medications data not found in case files")
            return
        
        # Create translations dictionary
        medications_translations = {
            "es": medications_es
        }
        
        # Find the joint_pain case by title (English or Spanish)
        result = connection.execute(text("""
            SELECT id 
            FROM clinical_cases 
            WHERE title ILIKE '%joint pain%' 
               OR title ILIKE '%dolor articular%'
               OR title ILIKE '%Joint Pain%'
               OR title ILIKE '%Dolor Articular%'
            LIMIT 1
        """))
        
        case_row = result.fetchone()
        
        if not case_row:
            print("❌ Joint pain case not found in database")
            return
        
        case_id = case_row[0]
        
        # Update medications field and translations
        connection.execute(text("""
            UPDATE clinical_cases
            SET 
                medications = :medications_en,
                medications_translations = CAST(:medications_translations AS JSONB)
            WHERE id = :case_id
        """), {
            'medications_en': medications_en,
            'medications_translations': json.dumps(medications_translations),
            'case_id': case_id
        })
        
        print(f"✅ Updated medications for joint_pain case (ID: {case_id})")
        
    except Exception as e:
        print(f"❌ Error updating joint_pain medications: {e}")
        raise


def downgrade() -> None:
    """Revert medications field update for joint_pain case"""
    # This is a data update, so downgrade is not easily reversible
    # We could store the previous values, but for simplicity, we'll leave it as a no-op
    pass

