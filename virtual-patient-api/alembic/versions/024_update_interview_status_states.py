"""Reduce the interview_status enum to the four lifecycle states.

The interview lifecycle is limited to exactly four states:

    IN_PROGRESS -> PROCESSING -> COMPLETED
                             \\-> INTERRUPTED

SQLAlchemy persists the enum member *names* (not their string values), so the
PostgreSQL type stores upper-case labels (e.g. ``ACTIVE``, ``COMPLETED``). The
new type keeps the same convention: ``IN_PROGRESS``, ``PROCESSING``,
``COMPLETED``, ``INTERRUPTED``.

Mapping of the previous labels:
    ACTIVE     -> IN_PROGRESS
    COMPLETED  -> COMPLETED (unchanged)
    ABANDONED  -> INTERRUPTED
    PROCESSING -> new label (no previous equivalent)

PostgreSQL cannot remove or rename values of an existing enum in place, so the
type is rebuilt: a new type is created, the column is remapped onto it, the old
type is dropped and the new one takes its name.

Alembic manages the surrounding transaction (see ``env.py``), so this migration
must not call ``commit``/``rollback`` itself: doing so closes Alembic's
transaction early and prevents the ``alembic_version`` bookkeeping from being
persisted.

Revision ID: 024_interview_status_states
Revises: 023_interview_calibration
"""

from alembic import op
import sqlalchemy as sa


revision = "024_interview_status_states"
down_revision = "023_interview_calibration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TYPE interview_status_new AS ENUM (
            'IN_PROGRESS', 'PROCESSING', 'COMPLETED', 'INTERRUPTED'
        )
    """)
    op.execute("ALTER TABLE medical_interviews ALTER COLUMN status DROP DEFAULT")
    # Remap the existing labels while casting to the new type.
    op.execute("""
        ALTER TABLE medical_interviews
        ALTER COLUMN status TYPE interview_status_new
        USING (
            CASE status::text
                WHEN 'ACTIVE' THEN 'IN_PROGRESS'
                WHEN 'ABANDONED' THEN 'INTERRUPTED'
                ELSE status::text
            END
        )::interview_status_new
    """)
    op.execute("""
        ALTER TABLE medical_interviews
        ALTER COLUMN status SET DEFAULT 'IN_PROGRESS'::interview_status_new
    """)
    op.execute("DROP TYPE interview_status")
    op.execute("ALTER TYPE interview_status_new RENAME TO interview_status")


def downgrade() -> None:
    op.execute("""
        CREATE TYPE interview_status_old AS ENUM (
            'ACTIVE', 'COMPLETED', 'ABANDONED'
        )
    """)
    op.execute("ALTER TABLE medical_interviews ALTER COLUMN status DROP DEFAULT")
    # The two labels introduced by this revision collapse back onto the closest
    # previous label: IN_PROGRESS -> ACTIVE, and both PROCESSING and INTERRUPTED
    # -> ABANDONED.
    op.execute("""
        ALTER TABLE medical_interviews
        ALTER COLUMN status TYPE interview_status_old
        USING (
            CASE status::text
                WHEN 'IN_PROGRESS' THEN 'ACTIVE'
                WHEN 'PROCESSING' THEN 'ABANDONED'
                WHEN 'INTERRUPTED' THEN 'ABANDONED'
                ELSE status::text
            END
        )::interview_status_old
    """)
    op.execute("""
        ALTER TABLE medical_interviews
        ALTER COLUMN status SET DEFAULT 'ACTIVE'::interview_status_old
    """)
    op.execute("DROP TYPE interview_status")
    op.execute("ALTER TYPE interview_status_old RENAME TO interview_status")
