"""Preserve reusable block originals without changing legacy recordings."""
from alembic import op
import sqlalchemy as sa

revision = "010_recording_blocks"
down_revision = "009_capture_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("interview_recording_blocks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recording_id", sa.String(36), sa.ForeignKey("interview_recordings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("capture_attempt_id", sa.String(36), sa.ForeignKey("interview_recording_segments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False, unique=True),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("metadata_hash", sa.String(64), nullable=False),
        sa.Column("block_metadata", sa.JSON(), nullable=False),
        sa.Column("encoded_timing", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("capture_attempt_id", "order", name="uq_recording_block_order"),
        sa.CheckConstraint('"order" >= 0 AND duration_ms > 0 AND size_bytes > 0', name="ck_recording_block_extent"))
    op.create_index("ix_interview_recording_blocks_recording_id", "interview_recording_blocks", ["recording_id"])


def downgrade():
    op.drop_table("interview_recording_blocks")
