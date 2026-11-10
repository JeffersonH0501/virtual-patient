"""Retain private calibration videos and outcomes for interview inspection."""
from alembic import op
import sqlalchemy as sa

revision = "003_calibration_captures"
down_revision = "002_canonical_feature_families"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "calibration_captures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("medical_interview_id", sa.Integer(), sa.ForeignKey("medical_interviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("capture_metadata", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("medical_interview_id", "fingerprint"),
    )
    op.create_index("ix_calibration_captures_medical_interview_id", "calibration_captures", ["medical_interview_id"])


def downgrade():
    op.drop_table("calibration_captures")
