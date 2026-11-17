"""Replace per-exchange recording blocks with per-turn media.

Drops ``interview_recording_blocks`` and creates ``interview_turn_media``, where
each student turn owns its own immutable capture file. ``turn_video_analyses``
keeps its existing ``storage_key`` column, which now points at that per-turn
file instead of being null with a ``block_source`` window reference.
"""
from alembic import op

import app.models  # noqa: F401
from app.core.database import Base

revision = "003_per_turn_media"
down_revision = "002_interview_performance_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["interview_turn_media"].create(bind=bind, checkfirst=True)
    # A clean install builds 001 from the current models, which no longer define blocks.
    op.execute("DROP TABLE IF EXISTS interview_recording_blocks")


def downgrade() -> None:
    # Recreate the former block table from the historical column shape. The ORM
    # no longer defines it, so the DDL is spelled out here for reversibility.
    import sqlalchemy as sa

    op.drop_table("interview_turn_media")
    op.create_table(
        "interview_recording_blocks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("recording_id", sa.String(length=36),
                  sa.ForeignKey("interview_recordings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("capture_attempt_id", sa.String(length=36),
                  sa.ForeignKey("interview_recording_segments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("storage_key", sa.String(length=500), nullable=False, unique=True),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("metadata_hash", sa.String(length=64), nullable=False),
        sa.Column("block_metadata", sa.JSON(), nullable=False),
        sa.Column("encoded_timing", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("capture_attempt_id", "order", name="uq_recording_block_order"),
        sa.CheckConstraint('"order" >= 0 AND (duration_ms IS NULL OR duration_ms > 0) AND size_bytes > 0',
                           name="ck_recording_block_extent"),
    )
