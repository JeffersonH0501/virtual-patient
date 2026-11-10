"""Persist owner self-assessments without changing teacher assignments."""
from alembic import op
import sqlalchemy as sa

revision = "004_self_ratings"
down_revision = "003_calibration_captures"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "self_ratings",
        sa.Column("interview_id", sa.Integer(), sa.ForeignKey("medical_interviews.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("rubric_version", sa.String(80), nullable=False),
        sa.Column("rubric_snapshot", sa.JSON(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("overall_score", sa.Float()),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("self_ratings")
