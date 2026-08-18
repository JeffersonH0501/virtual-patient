"""Add language-aware progress summary caching.

Revision ID: 012_localized_summaries
Revises: 011_add_case_key
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "012_localized_summaries"
down_revision = "011_add_case_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add canonical-language metadata and localized summary payloads."""
    op.add_column(
        "progress_summaries",
        sa.Column(
            "source_language",
            sa.String(length=8),
            nullable=False,
            server_default="en",
        ),
    )
    op.add_column(
        "progress_summaries",
        sa.Column(
            "localized_versions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    """Remove localized summary caching fields."""
    op.drop_column("progress_summaries", "localized_versions")
    op.drop_column("progress_summaries", "source_language")
