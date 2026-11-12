"""Consolidated initial schema for the first experimental version.

Single baseline migration. It builds the entire application schema from the
SQLAlchemy ORM metadata, which is the source of truth (the same metadata Alembic
autogenerate and ``env.py`` target). Every model module is imported explicitly so
no table is missed, then ``Base.metadata.create_all`` materializes the tables,
enum types, indexes and constraints exactly as the models define them.

This replaces the previous historical chain (former revisions 001..015). It does
not carry any historical data transformation: a fresh database only needs this
file. LangGraph persistence tables (checkpoints/store) are created separately by
``ensure_langgraph_schema`` and are intentionally not managed here.
"""
from alembic import op

# Import every model module so all tables register on Base.metadata before
# create_all. ``app.models`` does not transitively import the processing-job
# model, so it is imported explicitly (mirrors alembic/env.py).
import app.models  # noqa: F401
import app.models.processing_job  # noqa: F401
from app.core.database import Base

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
