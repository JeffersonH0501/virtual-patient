"""Add audio_url to interview_messages table

Revision ID: 002_audio_url
Revises: 001_add_teacher_feedback_table
Create Date: 2025-01-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_audio_url'
down_revision = '001_add_teacher_feedback_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add audio_url column to interview_messages table
    op.add_column('interview_messages', 
                  sa.Column('audio_url', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove audio_url column from interview_messages table
    op.drop_column('interview_messages', 'audio_url')

