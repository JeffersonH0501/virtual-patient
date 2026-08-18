"""Add per-turn paraverbal observations.

Revision ID: 015_interview_turn_paraverbal
Revises: 014_interview_recordings
"""

from alembic import op
import sqlalchemy as sa


revision = "015_interview_turn_paraverbal"
down_revision = "014_interview_recordings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Store structured OpenSMILE-derived observations per interview turn."""
    op.add_column("interview_turns", sa.Column("paraverbal", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Remove per-turn paraverbal observations."""
    op.drop_column("interview_turns", "paraverbal")
