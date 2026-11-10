"""Add durable capture acknowledgements without changing existing recordings."""
from alembic import op
import sqlalchemy as sa

revision = "009_capture_operations"
down_revision = "008_recorded_interview_durations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("capture_operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("interview_id", sa.Integer(), sa.ForeignKey("medical_interviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation_id", sa.String(36), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.UniqueConstraint("interview_id", "operation_id", name="uq_capture_operation"))


def downgrade():
    op.drop_table("capture_operations")
