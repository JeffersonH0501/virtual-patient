"""Add case_key column and update descriptions using key field

Revision ID: 011_add_case_key
Revises: 010_add_superuser
Create Date: 2025-01-XX XX:XX:XX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from pathlib import Path
import json


# revision identifiers, used by Alembic.
revision = '011_add_case_key'
down_revision = '010_add_superuser'
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
    """Add case_key column and update descriptions using key field"""
    # Get database connection
    connection = op.get_bind()
    
    try:
        # Step 1: Add case_key column if it doesn't exist
        print("🔄 Adding case_key column to clinical_cases table...")
        # Check if column exists first
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'clinical_cases' AND column_name = 'case_key'
        """))
        column_exists = result.fetchone() is not None
        
        if not column_exists:
            # Use op.add_column() - Alembic's proper way to add columns (handles transactions correctly)
            op.add_column('clinical_cases', sa.Column('case_key', sa.String(), nullable=True))
            print("✅ Added case_key column")
            
            # Verify it was added
            result = connection.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'clinical_cases' AND column_name = 'case_key'
            """))
            if result.fetchone() is None:
                raise Exception("Failed to add case_key column - column does not exist after addition")
        else:
            print("ℹ️  case_key column already exists")
        
        # Step 2: Load all case files and create key -> case_name mapping
        case_names = ["copd", "diabetes", "dyslipidemia", "hypothyroidism", "joint_pain"]
        key_to_case_name = {}
        
        for case_name in case_names:
            en_data = load_case_data(case_name, "en")
            if en_data and 'key' in en_data:
                case_key = en_data.get('key')
                key_to_case_name[case_key] = case_name
                print(f"   Mapped key '{case_key}' -> case '{case_name}'")
        
        # Step 3: Update case_key for existing cases and update descriptions
        print("\n🔄 Updating case_key and descriptions...")
        result = connection.execute(text("""
            SELECT id, title 
            FROM clinical_cases 
            WHERE case_type = 'default'
        """))
        
        default_cases = result.fetchall()
        updated_count = 0
        
        for case_id, case_title in default_cases:
            # Try to find the case by loading all cases and matching by key or title
            case_name = None
            case_key = None
            
            # Load all cases and find matching key
            for test_case_name in case_names:
                en_data = load_case_data(test_case_name, "en")
                if en_data:
                    # First try to match by key if available
                    test_key = en_data.get('key')
                    if test_key and test_key in key_to_case_name:
                        # Check if title matches (for existing cases without key)
                        if en_data.get('title', '') == case_title or en_data.get('title', '').lower() in case_title.lower():
                            case_key = test_key
                            case_name = test_case_name
                            break
                    # Fallback: match by title
                    elif en_data.get('title', '') == case_title or en_data.get('title', '').lower() in case_title.lower():
                        case_key = en_data.get('key')
                        case_name = test_case_name
                        break
            
            if not case_name:
                print(f"⚠️  Could not match case: {case_title} (ID: {case_id})")
                continue
            
            if not case_key:
                print(f"⚠️  No key found for case: {case_name}, will update without key")
                case_key = None  # Will be set to NULL in database
            
            # Load English and Spanish data
            en_data = load_case_data(case_name, "en")
            es_data = load_case_data(case_name, "es")
            
            if not en_data or not es_data:
                print(f"⚠️  Failed to load data for case: {case_name}")
                continue
            
            # Get descriptions
            description_en = en_data.get('description', '')
            description_es = es_data.get('description', '')
            
            if not description_en or not description_es:
                print(f"⚠️  Missing description for case: {case_name}")
                continue
            
            # Create description translations dict
            description_translations = {"es": description_es}
            
            print(f"\n🔄 Updating case: {case_name} (ID: {case_id}, key: {case_key})")
            print(f"   Title: {case_title}")
            print(f"   New EN: {description_en}")
            print(f"   New ES: {description_es[:60]}...")
            
            # Update only case_key and description
            connection.execute(text("""
                UPDATE clinical_cases
                SET 
                    case_key = :case_key,
                    description = :description_en,
                    description_translations = CAST(:description_translations AS jsonb),
                    updated_at = NOW()
                WHERE id = :case_id
            """), {
                'case_id': case_id,
                'case_key': case_key,
                'description_en': description_en,
                'description_translations': json.dumps(description_translations),
            })
            
            updated_count += 1
            print(f"   ✅ Updated")
        
        print(f"\n✅ Successfully updated {updated_count} clinical case(s)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise


def downgrade() -> None:
    """Remove case_key column"""
    try:
        op.drop_column('clinical_cases', 'case_key')
        print("✅ Removed case_key column")
    except Exception as e:
        print(f"⚠️  Error removing case_key column: {e}")

