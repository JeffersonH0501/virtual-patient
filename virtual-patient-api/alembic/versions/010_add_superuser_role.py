"""Add superuser role and create superuser account

Revision ID: 010_add_superuser
Revises: 009_create_default_org
Create Date: 2025-11-17 00:36:01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from passlib.context import CryptContext

# revision identifiers, used by Alembic.
revision = '010_add_superuser'
down_revision = '009_create_default_org'
branch_labels = None
depends_on = None

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def upgrade() -> None:
    """Add superuser role to enum and create superuser account"""
    connection = op.get_bind()
    
    try:
        # First, add 'superuser' to the user_role enum
        # PostgreSQL requires creating a new enum type and migrating data
        print("🔄 Adding 'superuser' to user_role enum...")
        
        # Check if superuser already exists in enum
        result = connection.execute(text("""
            SELECT unnest(enum_range(NULL::user_role))::text as role_value
        """))
        existing_roles = [row[0] for row in result.fetchall()]
        
        if 'superuser' not in existing_roles:
            # Create new enum type with superuser
            connection.execute(text("""
                CREATE TYPE user_role_new AS ENUM ('teacher', 'student', 'superuser')
            """))
            
            # Drop the default constraint temporarily
            connection.execute(text("""
                ALTER TABLE users 
                ALTER COLUMN role DROP DEFAULT
            """))
            
            # Migrate data from old enum to new enum
            connection.execute(text("""
                ALTER TABLE users 
                ALTER COLUMN role TYPE user_role_new 
                USING role::text::user_role_new
            """))
            
            # Re-add the default constraint with the new type
            connection.execute(text("""
                ALTER TABLE users 
                ALTER COLUMN role SET DEFAULT 'student'::user_role_new
            """))
            
            # Drop old enum and rename new one
            connection.execute(text("DROP TYPE user_role"))
            connection.execute(text("ALTER TYPE user_role_new RENAME TO user_role"))
            
            print("✅ Added 'superuser' to user_role enum")
        else:
            print("ℹ️  'superuser' already exists in user_role enum")
        
        # Check if superuser account already exists
        result = connection.execute(text("""
            SELECT id, username FROM users 
            WHERE username = 'andrea.superuser'
            LIMIT 1
        """))
        existing_user = result.fetchone()
        
        if existing_user:
            print(f"ℹ️  Superuser account already exists with ID: {existing_user[0]}")
            # Update role to superuser if it's not already
            connection.execute(text("""
                UPDATE users 
                SET role = 'superuser'::user_role
                WHERE username = 'andrea.superuser'
            """))
            print("✅ Updated existing user to superuser role")
        else:
            # Hash the password
            hashed_password = pwd_context.hash("a1b2c3d4")
            
            # Create superuser account
            connection.execute(text("""
                INSERT INTO users (username, email, full_name, hashed_password, disabled, preferred_language, role)
                VALUES (:username, :email, :full_name, :hashed_password, :disabled, :preferred_language, CAST(:role AS user_role))
            """), {
                'username': 'andrea.superuser',
                'email': 'andrea.superuser@virtualpatient.com',
                'full_name': 'Andrea Superuser',
                'hashed_password': hashed_password,
                'disabled': False,
                'preferred_language': 'en',
                'role': 'superuser'
            })
            
            print("✅ Created superuser account: andrea.superuser")
            print("   Password: a1b2c3d4")
        
        connection.commit()
        
    except Exception as e:
        connection.rollback()
        print(f"❌ Error adding superuser role: {e}")
        raise


def downgrade() -> None:
    """Remove superuser role from enum and delete superuser account"""
    connection = op.get_bind()
    
    try:
        # Delete superuser account
        connection.execute(text("""
            DELETE FROM users WHERE username = 'andrea.superuser'
        """))
        print("✅ Deleted superuser account")
        
        # Remove 'superuser' from enum
        # This is complex in PostgreSQL - we need to recreate the enum without superuser
        print("🔄 Removing 'superuser' from user_role enum...")
        
        # First, update any superuser users to student (shouldn't be any after deletion, but just in case)
        connection.execute(text("""
            UPDATE users 
            SET role = 'student'::user_role
            WHERE role = 'superuser'::user_role
        """))
        
        # Create new enum type without superuser
        connection.execute(text("""
            CREATE TYPE user_role_new AS ENUM ('teacher', 'student')
        """))
        
        # Drop the default constraint temporarily
        connection.execute(text("""
            ALTER TABLE users 
            ALTER COLUMN role DROP DEFAULT
        """))
        
        # Migrate data
        connection.execute(text("""
            ALTER TABLE users 
            ALTER COLUMN role TYPE user_role_new 
            USING role::text::user_role_new
        """))
        
        # Re-add the default constraint with the new type
        connection.execute(text("""
            ALTER TABLE users 
            ALTER COLUMN role SET DEFAULT 'student'::user_role_new
        """))
        
        # Drop old enum and rename new one
        connection.execute(text("DROP TYPE user_role"))
        connection.execute(text("ALTER TYPE user_role_new RENAME TO user_role"))
        
        print("✅ Removed 'superuser' from user_role enum")
        
        connection.commit()
        
    except Exception as e:
        connection.rollback()
        print(f"❌ Error removing superuser role: {e}")
        raise

