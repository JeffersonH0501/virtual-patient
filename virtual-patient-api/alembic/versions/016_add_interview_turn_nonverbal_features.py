"""Add per-turn nonverbal visual observations.

Revision ID: 016_nonverbal_features
Revises: 015_interview_turn_paraverbal
"""

from alembic import op
import sqlalchemy as sa


revision = "016_nonverbal_features"
down_revision = "015_interview_turn_paraverbal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Store descriptive visual observations separately from paraverbal data."""
    op.add_column(
        "interview_turns",
        sa.Column("nonverbal_features", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Remove per-turn nonverbal visual observations."""
    op.drop_column("interview_turns", "nonverbal_features")
