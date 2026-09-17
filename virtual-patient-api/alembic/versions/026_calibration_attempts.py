"""Add durable multimodal calibration attempts and media.

Revision ID: 026_calibration_attempts
Revises: 025_single_name
"""

from alembic import op
import sqlalchemy as sa

revision = "026_calibration_attempts"
down_revision = "025_single_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calibration_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("medical_interview_id", sa.Integer(), sa.ForeignKey("medical_interviews.id", ondelete="CASCADE"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("failure_reason", sa.String(80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("calibration_version", sa.String(80), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=True),
        sa.Column("quality", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("NOT is_active OR (status = 'passed' AND medical_interview_id IS NOT NULL)", name="ck_calibration_active_passed_linked"),
    )
    op.create_index("ix_calibration_attempt_user", "calibration_attempts", ["user_id"])
    op.create_index("ix_calibration_attempt_interview", "calibration_attempts", ["medical_interview_id"])
    op.create_index(
        "uq_calibration_active_interview",
        "calibration_attempts",
        ["medical_interview_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
        sqlite_where=sa.text("is_active = 1"),
    )
    op.create_table(
        "calibration_media_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("calibration_attempt_id", sa.String(36), sa.ForeignKey("calibration_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False, unique=True),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("calibration_attempt_id", "kind", name="uq_calibration_media_kind"),
        sa.CheckConstraint("size_bytes > 0", name="ck_calibration_media_size"),
        sa.CheckConstraint("duration_ms >= 0", name="ck_calibration_media_duration"),
    )
    op.create_index("ix_calibration_media_attempt", "calibration_media_assets", ["calibration_attempt_id"])


def downgrade() -> None:
    op.drop_table("calibration_media_assets")
    op.drop_index("uq_calibration_active_interview", table_name="calibration_attempts")
    op.drop_table("calibration_attempts")
