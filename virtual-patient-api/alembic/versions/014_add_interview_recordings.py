"""Add synchronized interview recordings and media timelines.

Revision ID: 014_interview_recordings
Revises: 013_index_localized_summaries
"""

from alembic import op
import sqlalchemy as sa


revision = "014_interview_recordings"
down_revision = "013_index_localized_summaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create private recording, media asset, and interview turn storage."""
    connection = op.get_bind()
    organization_id = connection.execute(
        sa.text("SELECT id FROM organizations ORDER BY id LIMIT 1")
    ).scalar()
    if organization_id is None:
        organization_id = connection.execute(
            sa.text(
                """
                INSERT INTO organizations (name, description, active)
                VALUES (
                    'Default Medical Organization',
                    'Default organization for existing users',
                    TRUE
                )
                RETURNING id
                """
            )
        ).scalar_one()

    op.add_column(
        "users",
        sa.Column("organization_id", sa.Integer(), nullable=True),
    )
    connection.execute(
        sa.text(
            "UPDATE users SET organization_id = :organization_id "
            "WHERE organization_id IS NULL"
        ),
        {"organization_id": organization_id},
    )
    op.create_foreign_key(
        "fk_users_organization_id",
        "users",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.alter_column("users", "organization_id", nullable=False)
    op.create_index("ix_users_organization_id", "users", ["organization_id"])

    op.create_table(
        "interview_recordings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("medical_interview_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("capture_config", sa.JSON(), nullable=False),
        sa.Column("consent_basis", sa.String(length=30), nullable=False),
        sa.Column("consent_policy_version", sa.String(length=80), nullable=False),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_recording_duration"),
        sa.ForeignKeyConstraint(["medical_interview_id"], ["medical_interviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("medical_interview_id"),
    )
    op.create_index(
        "ix_interview_recordings_medical_interview_id",
        "interview_recordings",
        ["medical_interview_id"],
        unique=True,
    )

    op.create_table(
        "interview_media_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recording_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("size_bytes >= 0", name="ck_media_asset_size"),
        sa.CheckConstraint("duration_ms >= 0", name="ck_media_asset_duration"),
        sa.ForeignKeyConstraint(["recording_id"], ["interview_recordings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recording_id", "kind", name="uq_recording_media_kind"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_interview_media_assets_recording_id", "interview_media_assets", ["recording_id"])

    op.create_table(
        "interview_turns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("medical_interview_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("speaker", sa.String(length=20), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("input_source", sa.String(length=40), nullable=False),
        sa.Column("timing_source", sa.String(length=40), nullable=False),
        sa.Column("timing_quality", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("start_ms >= 0", name="ck_interview_turn_start"),
        sa.CheckConstraint("end_ms >= start_ms", name="ck_interview_turn_end"),
        sa.ForeignKeyConstraint(["medical_interview_id"], ["medical_interviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["interview_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("medical_interview_id", "message_id", name="uq_interview_turn_message"),
        sa.UniqueConstraint("medical_interview_id", "sequence", name="uq_interview_turn_sequence"),
    )
    op.create_index("ix_interview_turns_medical_interview_id", "interview_turns", ["medical_interview_id"])
    op.create_index("ix_interview_turns_message_id", "interview_turns", ["message_id"])


def downgrade() -> None:
    """Remove synchronized recording storage."""
    op.drop_index("ix_interview_turns_message_id", table_name="interview_turns")
    op.drop_index("ix_interview_turns_medical_interview_id", table_name="interview_turns")
    op.drop_table("interview_turns")
    op.drop_index("ix_interview_media_assets_recording_id", table_name="interview_media_assets")
    op.drop_table("interview_media_assets")
    op.drop_index("ix_interview_recordings_medical_interview_id", table_name="interview_recordings")
    op.drop_table("interview_recordings")
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_constraint("fk_users_organization_id", "users", type_="foreignkey")
    op.drop_column("users", "organization_id")
