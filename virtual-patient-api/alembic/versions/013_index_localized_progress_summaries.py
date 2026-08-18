"""Index cached localized progress summaries.

Revision ID: 013_index_localized_summaries
Revises: 012_localized_summaries
"""

from alembic import op


revision = "013_index_localized_summaries"
down_revision = "012_localized_summaries"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_progress_summaries_localized_versions"


def upgrade() -> None:
    """Create a GIN index for lookups by localized language key."""
    op.create_index(
        INDEX_NAME,
        "progress_summaries",
        ["localized_versions"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Remove the localized-summary GIN index."""
    op.drop_index(INDEX_NAME, table_name="progress_summaries")
