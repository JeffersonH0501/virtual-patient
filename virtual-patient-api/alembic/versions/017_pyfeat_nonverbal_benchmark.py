"""Add independent Py-Feat per-turn benchmark observations."""

from alembic import op
import sqlalchemy as sa


revision = "017_pyfeat_benchmark"
down_revision = "016_nonverbal_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("interview_turns", sa.Column("pyfeat_nonverbal_features", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("interview_turns", "pyfeat_nonverbal_features")
