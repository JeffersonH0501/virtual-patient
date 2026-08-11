"""add gender_restriction to clinical_cases

Revision ID: 007_add_gender_restriction
Revises: 006_add_created_by
Create Date: 2024-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '007_add_gender_restriction'
down_revision = '006_add_created_by'
branch_labels = None
depends_on = None


def upgrade():
    # Add gender_restriction column to clinical_cases table
    op.add_column('clinical_cases', sa.Column('gender_restriction', sa.String(), nullable=True))
    
    # Set gender_restriction to 'female' for joint_pain case
    # Find the joint_pain case by title (English or Spanish)
    op.execute(text("""
        UPDATE clinical_cases 
        SET gender_restriction = 'female'
        WHERE title ILIKE '%joint pain%' 
           OR title ILIKE '%dolor articular%'
           OR title ILIKE '%Joint Pain%'
           OR title ILIKE '%Dolor Articular%'
    """))


def downgrade():
    # Drop gender_restriction column
    op.drop_column('clinical_cases', 'gender_restriction')

