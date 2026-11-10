"""Preserve incomplete originals without inventing their encoded duration."""
from alembic import op
import sqlalchemy as sa

revision = '011_partial_recording_blocks'
down_revision = '010_recording_blocks'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('ck_recording_block_extent', 'interview_recording_blocks', type_='check')
    op.alter_column('interview_recording_blocks', 'duration_ms', existing_type=sa.BigInteger(), nullable=True)
    op.create_check_constraint('ck_recording_block_extent', 'interview_recording_blocks',
        '"order" >= 0 AND (duration_ms IS NULL OR duration_ms > 0) AND size_bytes > 0')


def downgrade():
    raise RuntimeError('Cannot discard preserved incomplete originals to downgrade recording blocks')
