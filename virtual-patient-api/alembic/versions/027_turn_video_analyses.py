"""Add durable per-turn video analysis jobs.

Revision ID: 027_turn_video_analyses
Revises: 026_calibration_attempts
"""

from alembic import op
import sqlalchemy as sa

revision = "027_turn_video_analyses"
down_revision = "026_calibration_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "turn_video_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("medical_interview_id", sa.Integer(), sa.ForeignKey("medical_interviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recording_id", sa.String(36), sa.ForeignKey("interview_recordings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turn_id", sa.String(36), sa.ForeignKey("interview_turns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("speaker", sa.String(20), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("roi_snapshots", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("end_ms >= start_ms", name="ck_turn_video_analysis_window"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_turn_video_analysis_size"),
        sa.UniqueConstraint("recording_id", "turn_id", name="uq_turn_video_analysis_recording_turn"),
        sa.UniqueConstraint("turn_id", name="uq_turn_video_analyses_turn_id"),
        sa.UniqueConstraint("storage_key", name="uq_turn_video_analyses_storage_key"),
    )
    op.create_index("ix_turn_video_analyses_interview", "turn_video_analyses", ["medical_interview_id"])
    op.create_index("ix_turn_video_analyses_recording", "turn_video_analyses", ["recording_id"])
    op.create_index("ix_turn_video_analyses_status", "turn_video_analyses", ["status"])


def downgrade() -> None:
    op.drop_index("ix_turn_video_analyses_status", table_name="turn_video_analyses")
    op.drop_index("ix_turn_video_analyses_recording", table_name="turn_video_analyses")
    op.drop_index("ix_turn_video_analyses_interview", table_name="turn_video_analyses")
    op.drop_table("turn_video_analyses")
