"""Add opaque public identifiers to medical interviews.

Revision ID: 019_public_interview_id
Revises: 018_progress_message_set_null
"""

import secrets

from alembic import op
import sqlalchemy as sa


revision = "019_public_interview_id"
down_revision = "018_progress_message_set_null"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("medical_interviews", sa.Column("public_id", sa.String(length=11), nullable=True))

    connection = op.get_bind()
    interview_ids = connection.execute(sa.text("SELECT id FROM medical_interviews")).scalars()
    generated_ids: set[str] = set()
    for interview_id in interview_ids:
        public_id = secrets.token_urlsafe(8)
        while public_id in generated_ids:
            public_id = secrets.token_urlsafe(8)
        generated_ids.add(public_id)
        connection.execute(
            sa.text("UPDATE medical_interviews SET public_id = :public_id WHERE id = :interview_id"),
            {"public_id": public_id, "interview_id": interview_id},
        )

    op.alter_column("medical_interviews", "public_id", existing_type=sa.String(length=11), nullable=False)
    op.create_index("ix_medical_interviews_public_id", "medical_interviews", ["public_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_medical_interviews_public_id", table_name="medical_interviews")
    op.drop_column("medical_interviews", "public_id")
