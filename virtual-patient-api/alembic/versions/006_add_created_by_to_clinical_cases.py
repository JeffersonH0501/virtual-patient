"""add created_by to clinical_cases

Revision ID: 006_add_created_by
Revises: 005_update_clinical_cases
Create Date: 2024-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006_add_created_by'
down_revision = '005_update_clinical_cases'
branch_labels = None
depends_on = None


def upgrade():
    # Add created_by column to clinical_cases table
    op.add_column('clinical_cases', sa.Column('created_by', sa.Integer(), nullable=True))
    
    # Add foreign key constraint to users table
    op.create_foreign_key(
        'fk_clinical_cases_created_by_users',
        'clinical_cases',
        'users',
        ['created_by'],
        ['id']
    )
    
    # Note about autoincrement: The id column in the model now has autoincrement=True
    # In PostgreSQL, integer primary keys automatically use sequences (SERIAL/BIGSERIAL)
    # If the column was created without a sequence, we need to add one.
    # However, existing records will NOT be affected - they keep their current IDs.
    # The sequence will just continue from the highest existing ID for new records.
    
    # Check if a sequence already exists for the id column
    # If not, create one and set it to the max existing ID + 1
    op.execute("""
        DO $$
        BEGIN
            -- Check if sequence exists
            IF NOT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = 'clinical_cases_id_seq'
            ) THEN
                -- Create sequence starting from max existing ID + 1
                CREATE SEQUENCE clinical_cases_id_seq OWNED BY clinical_cases.id;
                SELECT setval('clinical_cases_id_seq', COALESCE((SELECT MAX(id) FROM clinical_cases), 0) + 1, false);
                ALTER TABLE clinical_cases ALTER COLUMN id SET DEFAULT nextval('clinical_cases_id_seq');
            ELSE
                -- Sequence exists, just ensure it's set correctly
                PERFORM setval(
                    'clinical_cases_id_seq',
                    COALESCE((SELECT MAX(id) FROM clinical_cases), 0) + 1,
                    false
                );
            END IF;
        END $$;
    """)


def downgrade():
    # Drop foreign key constraint
    op.drop_constraint('fk_clinical_cases_created_by_users', 'clinical_cases', type_='foreignkey')
    
    # Drop created_by column
    op.drop_column('clinical_cases', 'created_by')

