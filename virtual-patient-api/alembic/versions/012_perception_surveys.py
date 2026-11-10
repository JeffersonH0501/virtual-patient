"""Store one perception survey per participant."""
from alembic import op
import sqlalchemy as sa

revision = "012_perception_surveys"
down_revision = "011_partial_recording_blocks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("perception_surveys",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("comments", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'SUBMITTED')", name="ck_perception_survey_status"))


def downgrade():
    op.drop_table("perception_surveys")
