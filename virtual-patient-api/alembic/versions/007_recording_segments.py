"""Add recording segments while preserving existing recordings and turn timing."""

from alembic import op
import sqlalchemy as sa

revision = "007_recording_segments"
down_revision = "006_case_description_wording"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "interview_recording_segments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recording_id", sa.String(36), sa.ForeignKey("interview_recordings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("offset_ms", sa.BigInteger(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("capture_config", sa.JSON(), nullable=False),
        sa.Column("calibration", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("recording_id", "sequence", name="uq_recording_segment_sequence"),
        sa.CheckConstraint("sequence >= 0 AND offset_ms >= 0", name="ck_recording_segment_position"),
        sa.CheckConstraint("(duration_ms IS NULL AND sealed_at IS NULL) OR "
                           "(duration_ms >= 0 AND duration_ms IS NOT NULL AND sealed_at IS NOT NULL)",
                           name="ck_recording_segment_seal"),
    )
    op.create_index("uq_recording_active_segment", "interview_recording_segments", ["recording_id"],
                    unique=True, postgresql_where=sa.text("sealed_at IS NULL"))
    for table in ("interview_media_assets", "interview_turns"):
        op.add_column(table, sa.Column("segment_id", sa.String(36), nullable=True))
        op.create_foreign_key(f"fk_{table}_segment_id", table, "interview_recording_segments",
                              ["segment_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_interview_turns_segment_id", "interview_turns", ["segment_id"])
    op.drop_constraint("uq_recording_media_kind", "interview_media_assets", type_="unique")
    op.create_index("uq_recording_legacy_media_kind", "interview_media_assets", ["recording_id", "kind"],
                    unique=True, postgresql_where=sa.text("segment_id IS NULL"))
    op.create_index("uq_recording_segment_media_kind", "interview_media_assets", ["segment_id", "kind"],
                    unique=True, postgresql_where=sa.text("segment_id IS NOT NULL"))


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM interview_recording_segments LIMIT 1")).scalar():
        raise RuntimeError("Cannot downgrade while segmented interview recordings exist")
    op.drop_index("uq_recording_segment_media_kind", table_name="interview_media_assets")
    op.drop_index("uq_recording_legacy_media_kind", table_name="interview_media_assets")
    op.create_unique_constraint("uq_recording_media_kind", "interview_media_assets", ["recording_id", "kind"])
    op.drop_index("ix_interview_turns_segment_id", table_name="interview_turns")
    for table in ("interview_media_assets", "interview_turns"):
        op.drop_constraint(f"fk_{table}_segment_id", table, type_="foreignkey")
        op.drop_column(table, "segment_id")
    op.drop_table("interview_recording_segments")
