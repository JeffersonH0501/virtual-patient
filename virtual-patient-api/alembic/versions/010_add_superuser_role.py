"""Add superuser role.

Revision ID: 010_add_superuser
Revises: 009_create_default_org
Create Date: 2025-11-17 00:36:01

"""
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '010_add_superuser'
down_revision = '009_create_default_org'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the superuser role to the user_role enum.

    No user account or credential is created by this migration. Administrative
    users must be provisioned separately through an authenticated operational
    process with credentials supplied outside source control.
    """
    connection = op.get_bind()

    try:
        result = connection.execute(text("""
            SELECT unnest(enum_range(NULL::user_role))::text AS role_value
        """))
        existing_roles = [row[0] for row in result.fetchall()]

        if 'superuser' not in existing_roles:
            connection.execute(text("""
                CREATE TYPE user_role_new AS ENUM ('teacher', 'student', 'superuser')
            """))
            connection.execute(text("""
                ALTER TABLE users ALTER COLUMN role DROP DEFAULT
            """))
            connection.execute(text("""
                ALTER TABLE users
                ALTER COLUMN role TYPE user_role_new
                USING role::text::user_role_new
            """))
            connection.execute(text("""
                ALTER TABLE users
                ALTER COLUMN role SET DEFAULT 'student'::user_role_new
            """))
            connection.execute(text("DROP TYPE user_role"))
            connection.execute(text("ALTER TYPE user_role_new RENAME TO user_role"))

        connection.commit()
    except Exception:
        connection.rollback()
        raise


def downgrade() -> None:
    """Remove the superuser role from the user_role enum."""
    connection = op.get_bind()

    try:
        # Preserve user records by demoting any existing superusers before the
        # enum value is removed.
        connection.execute(text("""
            UPDATE users
            SET role = 'student'::user_role
            WHERE role = 'superuser'::user_role
        """))
        connection.execute(text("""
            CREATE TYPE user_role_new AS ENUM ('teacher', 'student')
        """))
        connection.execute(text("""
            ALTER TABLE users ALTER COLUMN role DROP DEFAULT
        """))
        connection.execute(text("""
            ALTER TABLE users
            ALTER COLUMN role TYPE user_role_new
            USING role::text::user_role_new
        """))
        connection.execute(text("""
            ALTER TABLE users
            ALTER COLUMN role SET DEFAULT 'student'::user_role_new
        """))
        connection.execute(text("DROP TYPE user_role"))
        connection.execute(text("ALTER TYPE user_role_new RENAME TO user_role"))

        connection.commit()
    except Exception:
        connection.rollback()
        raise
