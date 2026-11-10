"""Replace historical wall-clock durations with confirmed interview activity."""

from alembic import op
import sqlalchemy as sa

revision = "008_recorded_interview_durations"
down_revision = "007_recording_segments"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().execute(sa.text("""
        UPDATE medical_interviews AS interview
        SET total_duration = (
            SELECT round(coalesce(
                (SELECT recording.duration_ms FROM interview_recordings AS recording
                 WHERE recording.medical_interview_id = interview.id
                   AND recording.status IN ('ready', 'partial')
                   AND recording.ended_at IS NOT NULL),
                (SELECT max(turn.end_ms) FROM interview_turns AS turn
                 WHERE turn.medical_interview_id = interview.id)
            ) / 1000.0)::integer
        )
        WHERE interview.status::text IN ('COMPLETED', 'INTERRUPTED', 'PROCESSING')
    """))


def downgrade():
    # Recorded activity is authoritative; wall-clock estimates cannot be reconstructed safely.
    pass
