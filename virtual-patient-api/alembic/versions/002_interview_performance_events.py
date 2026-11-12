"""Add interview-scoped performance events."""
from alembic import op

import app.models  # noqa: F401
from app.core.database import Base

revision = "002_interview_performance_events"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["interview_performance_events"].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    op.drop_table("interview_performance_events")
