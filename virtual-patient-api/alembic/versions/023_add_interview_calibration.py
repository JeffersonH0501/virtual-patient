"""Add the pre-interview calibration lifecycle.

Revision ID: 023_interview_calibration
Revises: 022_pyfeat_primary
"""

from alembic import op
import sqlalchemy as sa


revision = "023_interview_calibration"
down_revision = "022_pyfeat_primary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "medical_interviews",
        "start_time",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE medical_interviews
        SET start_time = created_at
        WHERE start_time IS NULL
    """))
    op.alter_column(
        "medical_interviews",
        "start_time",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )
