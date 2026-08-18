"""Set the progress-summary message reference to null on message deletion.

Revision ID: 018_progress_message_set_null
Revises: 017_pyfeat_benchmark
"""

from typing import Sequence, Union

from alembic import op


revision: str = "018_progress_message_set_null"
down_revision: Union[str, None] = "017_pyfeat_benchmark"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = "progress_summaries_last_updated_message_id_fkey"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "progress_summaries", type_="foreignkey")
    op.create_foreign_key(
        CONSTRAINT_NAME,
        "progress_summaries",
        "interview_messages",
        ["last_updated_message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "progress_summaries", type_="foreignkey")
    op.create_foreign_key(
        CONSTRAINT_NAME,
        "progress_summaries",
        "interview_messages",
        ["last_updated_message_id"],
        ["id"],
    )
