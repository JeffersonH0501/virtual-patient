"""Add new fields to progress_summaries table

Revision ID: 004_add_progress_summary_fields
Revises: 003_update_rude_unfriendly
Create Date: 2025-11-07 00:46:29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '004_add_progress_summary_fields'
down_revision = '003_update_rude_unfriendly'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add weight_in_kg column
    op.add_column('progress_summaries', 
                  sa.Column('weight_in_kg', sa.Float(), nullable=True))
    
    # Add habits column (JSON for structured habit data)
    op.add_column('progress_summaries', 
                  sa.Column('habits', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    
    # Add work_information column
    op.add_column('progress_summaries', 
                  sa.Column('work_information', sa.Text(), nullable=True))
    
    # Add medical_history column (JSON for structured medical history data)
    op.add_column('progress_summaries', 
                  sa.Column('medical_history', postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    # Remove the added columns
    op.drop_column('progress_summaries', 'medical_history')
    op.drop_column('progress_summaries', 'work_information')
    op.drop_column('progress_summaries', 'habits')
    op.drop_column('progress_summaries', 'weight_in_kg')

