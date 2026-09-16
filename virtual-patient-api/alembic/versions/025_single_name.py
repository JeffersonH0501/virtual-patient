"""Collapse the user given/family names into a single ``name`` column.

Migration 021 stored each account's historical display name in ``first_name``
and left ``last_name`` empty. This migration finishes that consolidation by
replacing the two columns with one ``name`` column.

Upgrade backfills ``name`` from ``trim(concat_ws(' ', first_name, last_name))``
so accounts that still carry a separate family name keep the same rendered
value they had before (a single space between the parts, no trailing space when
``last_name`` is empty). The column is added nullable, backfilled, then made
NOT NULL before the old columns are dropped.

Downgrade restores the previous shape: the whole ``name`` goes back into
``first_name`` and ``last_name`` starts empty, mirroring the state migration 021
left behind.

Alembic manages the surrounding transaction (see ``env.py``), so this migration
must not call ``commit``/``rollback`` itself.

Revision ID: 025_single_name
Revises: 024_interview_status_states
"""

from alembic import op
import sqlalchemy as sa


revision = "025_single_name"
down_revision = "024_interview_status_states"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("name", sa.String(), nullable=True))
    op.execute(sa.text("""
        UPDATE users
        SET name = trim(concat_ws(' ', first_name, last_name))
    """))
    op.alter_column("users", "name", nullable=False)
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")


def downgrade():
    op.add_column("users", sa.Column("first_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(), nullable=True))
    op.execute(sa.text("""
        UPDATE users
        SET first_name = COALESCE(name, ''),
            last_name = ''
    """))
    op.alter_column("users", "first_name", nullable=False)
    op.alter_column("users", "last_name", nullable=False)
    op.drop_column("users", "name")
