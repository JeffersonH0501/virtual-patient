"""Create default organization

Revision ID: 009_create_default_org
Revises: 008_joint_pain_meds
Create Date: 2025-11-09 12:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '009_create_default_org'
down_revision = '008_joint_pain_meds'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create default organization with ID 1 if it doesn't exist"""
    # Get database connection
    connection = op.get_bind()
    
    try:
        # Check if organization with ID 1 already exists
        result = connection.execute(text("""
            SELECT id, name FROM organizations 
            WHERE id = 1
            LIMIT 1
        """))
        
        existing_org = result.fetchone()
        
        if existing_org:
            print(f"ℹ️  Organization with ID 1 already exists: {existing_org[1]}")
        else:
            # Check if any organization exists
            count_result = connection.execute(text("SELECT COUNT(*) FROM organizations"))
            count = count_result.fetchone()[0]
            
            if count == 0:
                # Create default organization with explicit ID 1
                # First, reset the sequence to ensure ID 1 is used
                connection.execute(text("""
                    SELECT setval('organizations_id_seq', 1, false)
                """))
                
                # Insert with explicit ID 1
                connection.execute(text("""
                    INSERT INTO organizations (id, name, description, active)
                    VALUES (1, 'Default Medical Organization', 'Default organization for clinical cases', TRUE)
                """))
                
                # Reset sequence to continue from 2
                connection.execute(text("""
                    SELECT setval('organizations_id_seq', 2, false)
                """))
                
                print("✅ Created default organization with ID 1")
            else:
                # Organizations exist but ID 1 is not taken
                # We need to insert with ID 1, but this might cause issues if there are existing records
                # Check if we can safely insert
                max_id_result = connection.execute(text("SELECT MAX(id) FROM organizations"))
                max_id = max_id_result.fetchone()[0] or 0
                
                if max_id < 1:
                    # Safe to insert with ID 1
                    connection.execute(text("""
                        SELECT setval('organizations_id_seq', 1, false)
                    """))
                    
                    connection.execute(text("""
                        INSERT INTO organizations (id, name, description, active)
                        VALUES (1, 'Default Medical Organization', 'Default organization for clinical cases', TRUE)
                    """))
                    
                    # Set sequence to max_id + 1
                    connection.execute(text(f"""
                        SELECT setval('organizations_id_seq', {max_id + 1}, false)
                    """))
                    
                    print("✅ Created default organization with ID 1")
                else:
                    print("⚠️  Cannot create organization with ID 1: existing organizations have higher IDs")
                    # Create without explicit ID
                    connection.execute(text("""
                        INSERT INTO organizations (name, description, active)
                        VALUES ('Default Medical Organization', 'Default organization for clinical cases', TRUE)
                    """))
                    print("✅ Created default organization (auto-assigned ID)")
            
    except Exception as e:
        print(f"❌ Error creating default organization: {e}")
        raise


def downgrade() -> None:
    """Remove default organization"""
    # Get database connection
    connection = op.get_bind()
    
    try:
        # Remove default organization
        connection.execute(text("""
            DELETE FROM organizations 
            WHERE name = 'Default Medical Organization'
        """))
        print("✅ Removed default organization")
    except Exception as e:
        print(f"❌ Error removing default organization: {e}")
        raise

