"""Create the first release application schema."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_release_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'organizations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_organizations_id'), 'organizations', ['id'], unique=False)
    op.create_table(
        'personalities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('namespace_key', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('name_translations', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_personalities_id'), 'personalities', ['id'], unique=False)
    op.create_index(op.f('ix_personalities_namespace_key'), 'personalities', ['namespace_key'], unique=True)
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('hashed_password', sa.String(), nullable=True),
        sa.Column('disabled', sa.Boolean(), nullable=True),
        sa.Column('preferred_language', sa.String(), nullable=True),
        sa.Column('role', sa.Enum('teacher', 'student', 'superuser', name='user_role'), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_organization_id'), 'users', ['organization_id'], unique=False)
    op.create_index('uq_users_email_normalized', 'users', [sa.text('lower(email)')], unique=True)
    op.create_table(
        'clinical_cases',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('case_key', sa.String(), nullable=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('case_type', sa.Enum('default', 'custom', name='case_type'), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('icon', sa.String(), nullable=True),
        sa.Column('age', sa.Integer(), nullable=True),
        sa.Column('weight_in_kg', sa.Float(), nullable=True),
        sa.Column('physical_requirements', sa.String(), nullable=True),
        sa.Column('socioeconomic_status', sa.String(), nullable=True),
        sa.Column('female_photo', sa.String(), nullable=True),
        sa.Column('male_photo', sa.String(), nullable=True),
        sa.Column('female_name', sa.String(), nullable=True),
        sa.Column('male_name', sa.String(), nullable=True),
        sa.Column('gender_restriction', sa.String(), nullable=True),
        sa.Column('patient_context', sa.String(), nullable=True),
        sa.Column('chief_complaint', sa.String(), nullable=True),
        sa.Column('present_illness', sa.String(), nullable=True),
        sa.Column('personal_medical_history', sa.String(), nullable=True),
        sa.Column('surgical_history', sa.String(), nullable=True),
        sa.Column('family_history', sa.String(), nullable=True),
        sa.Column('medications', sa.String(), nullable=True),
        sa.Column('habits', sa.String(), nullable=True),
        sa.Column('allergies', sa.String(), nullable=True),
        sa.Column('concerns', sa.String(), nullable=True),
        sa.Column('title_translations', sa.JSON(), nullable=True),
        sa.Column('description_translations', sa.JSON(), nullable=True),
        sa.Column('chief_complaint_translations', sa.JSON(), nullable=True),
        sa.Column('present_illness_translations', sa.JSON(), nullable=True),
        sa.Column('personal_medical_history_translations', sa.JSON(), nullable=True),
        sa.Column('surgical_history_translations', sa.JSON(), nullable=True),
        sa.Column('family_history_translations', sa.JSON(), nullable=True),
        sa.Column('medications_translations', sa.JSON(), nullable=True),
        sa.Column('habits_translations', sa.JSON(), nullable=True),
        sa.Column('allergies_translations', sa.JSON(), nullable=True),
        sa.Column('concerns_translations', sa.JSON(), nullable=True),
        sa.Column('physical_requirements_translations', sa.JSON(), nullable=True),
        sa.Column('socioeconomic_status_translations', sa.JSON(), nullable=True),
        sa.Column('patient_context_translations', sa.JSON(), nullable=True),
        sa.Column('female_name_translations', sa.JSON(), nullable=True),
        sa.Column('male_name_translations', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_clinical_cases_id'), 'clinical_cases', ['id'], unique=False)
    op.create_table(
        'medical_interviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('public_id', sa.String(length=11), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('clinical_case_id', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.Enum('IN_PROGRESS', 'PROCESSING', 'COMPLETED', 'INTERRUPTED', name='interview_status'), nullable=False),
        sa.Column('interview_metadata', sa.JSON(), nullable=True),
        sa.Column('total_duration', sa.Integer(), nullable=True),
        sa.Column('patient_name', sa.String(), nullable=True),
        sa.Column('patient_photo', sa.String(), nullable=True),
        sa.Column('patient_gender', sa.String(), nullable=True),
        sa.Column('personality_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['clinical_case_id'], ['clinical_cases.id']),
        sa.ForeignKeyConstraint(['personality_id'], ['personalities.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_medical_interviews_clinical_case_id'), 'medical_interviews', ['clinical_case_id'], unique=False)
    op.create_index(op.f('ix_medical_interviews_id'), 'medical_interviews', ['id'], unique=False)
    op.create_index(op.f('ix_medical_interviews_public_id'), 'medical_interviews', ['public_id'], unique=True)
    op.create_index(op.f('ix_medical_interviews_user_id'), 'medical_interviews', ['user_id'], unique=False)
    op.create_table(
        'interview_evaluation_runs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('medical_interview_id', sa.Integer(), nullable=False),
        sa.Column('evaluation_condition', sa.String(length=32), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['medical_interview_id'], ['medical_interviews.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_interview_evaluation_runs_medical_interview_id'), 'interview_evaluation_runs', ['medical_interview_id'], unique=False)
    op.create_table(
        'interview_evaluations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('medical_interview_id', sa.Integer(), nullable=False),
        sa.Column('evaluation_condition', sa.String(length=32), server_default='TEXT_ONLY', nullable=False),
        sa.Column('evaluation_results', sa.JSON(), nullable=False),
        sa.Column('overall_score', sa.Float(), nullable=True),
        sa.Column('completion_timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("evaluation_condition IN ('TEXT_ONLY', 'TEXT_PLUS_MULTIMODAL')", name='ck_interview_evaluation_condition'),
        sa.ForeignKeyConstraint(['medical_interview_id'], ['medical_interviews.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('medical_interview_id', 'evaluation_condition', name='uq_interview_evaluation_condition'),
    )
    op.create_index(op.f('ix_interview_evaluations_id'), 'interview_evaluations', ['id'], unique=False)
    op.create_index(op.f('ix_interview_evaluations_medical_interview_id'), 'interview_evaluations', ['medical_interview_id'], unique=False)
    op.create_table(
        'interview_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('interview_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('sender_type', sa.String(length=20), nullable=False),
        sa.Column('message_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('audio_url', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['interview_id'], ['medical_interviews.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_interview_messages_id'), 'interview_messages', ['id'], unique=False)
    op.create_index(op.f('ix_interview_messages_interview_id'), 'interview_messages', ['interview_id'], unique=False)
    create_processing_jobs(op)
    op.create_table(
        'interview_recordings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('medical_interview_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.BigInteger(), nullable=True),
        sa.Column('capture_config', sa.JSON(), nullable=False),
        sa.Column('consent_basis', sa.String(length=30), nullable=False),
        sa.Column('consent_policy_version', sa.String(length=80), nullable=False),
        sa.Column('retention_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_code', sa.String(length=80), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('duration_ms IS NULL OR duration_ms >= 0', name='ck_recording_duration'),
        sa.ForeignKeyConstraint(['medical_interview_id'], ['medical_interviews.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_interview_recordings_medical_interview_id'), 'interview_recordings', ['medical_interview_id'], unique=True)
    op.create_table(
        'session_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('interview_id', sa.Integer(), nullable=False),
        sa.Column('notes_content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['interview_id'], ['medical_interviews.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_session_notes_id'), 'session_notes', ['id'], unique=False)
    op.create_index(op.f('ix_session_notes_interview_id'), 'session_notes', ['interview_id'], unique=False)
    op.create_table(
        'teacher_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('interview_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('assigned_by_id', sa.Integer(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assigned_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['interview_id'], ['medical_interviews.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['teacher_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('interview_id', 'teacher_id', name='uq_teacher_assignment'),
    )
    op.create_index(op.f('ix_teacher_assignments_interview_id'), 'teacher_assignments', ['interview_id'], unique=False)
    op.create_index(op.f('ix_teacher_assignments_teacher_id'), 'teacher_assignments', ['teacher_id'], unique=False)
    op.create_table(
        'teacher_feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('feedback', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('medical_interview_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['medical_interview_id'], ['medical_interviews.id']),
        sa.ForeignKeyConstraint(['teacher_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_teacher_feedback_id'), 'teacher_feedback', ['id'], unique=False)
    op.create_table(
        'user_hypotheses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('interview_id', sa.Integer(), nullable=False),
        sa.Column('hypothesis_text', sa.Text(), nullable=False),
        sa.Column('hypothesis_order', sa.Integer(), nullable=False),
        sa.CheckConstraint('hypothesis_order >= 1 AND hypothesis_order <= 3', name='chk_hypothesis_order'),
        sa.ForeignKeyConstraint(['interview_id'], ['medical_interviews.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('interview_id', 'hypothesis_order', name='uq_interview_hypothesis_order'),
    )
    op.create_index(op.f('ix_user_hypotheses_id'), 'user_hypotheses', ['id'], unique=False)
    op.create_index(op.f('ix_user_hypotheses_interview_id'), 'user_hypotheses', ['interview_id'], unique=False)
    op.create_table(
        'interview_media_assets',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('recording_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('storage_key', sa.String(length=500), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('duration_ms', sa.BigInteger(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('duration_ms >= 0', name='ck_media_asset_duration'),
        sa.CheckConstraint('size_bytes >= 0', name='ck_media_asset_size'),
        sa.ForeignKeyConstraint(['recording_id'], ['interview_recordings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('recording_id', 'kind', name='uq_recording_media_kind'),
        sa.UniqueConstraint('storage_key'),
    )
    op.create_index(op.f('ix_interview_media_assets_recording_id'), 'interview_media_assets', ['recording_id'], unique=False)
    op.create_table(
        'interview_turns',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('medical_interview_id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('speaker', sa.String(length=20), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('start_ms', sa.BigInteger(), nullable=False),
        sa.Column('end_ms', sa.BigInteger(), nullable=False),
        sa.Column('transcript', sa.Text(), nullable=False),
        sa.Column('input_source', sa.String(length=40), nullable=False),
        sa.Column('timing_source', sa.String(length=40), nullable=False),
        sa.Column('timing_quality', sa.String(length=30), nullable=False),
        sa.Column('paraverbal', sa.JSON(), nullable=True),
        sa.Column('nonverbal_features', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('end_ms >= start_ms', name='ck_interview_turn_end'),
        sa.CheckConstraint('start_ms >= 0', name='ck_interview_turn_start'),
        sa.ForeignKeyConstraint(['medical_interview_id'], ['medical_interviews.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['message_id'], ['interview_messages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('medical_interview_id', 'message_id', name='uq_interview_turn_message'),
        sa.UniqueConstraint('medical_interview_id', 'sequence', name='uq_interview_turn_sequence'),
    )
    op.create_index(op.f('ix_interview_turns_medical_interview_id'), 'interview_turns', ['medical_interview_id'], unique=False)
    op.create_index(op.f('ix_interview_turns_message_id'), 'interview_turns', ['message_id'], unique=False)
    op.create_table(
        'progress_summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('medical_interview_id', sa.Integer(), nullable=False),
        sa.Column('age', sa.Integer(), nullable=True),
        sa.Column('weight_in_kg', sa.Float(), nullable=True),
        sa.Column('current_symptoms', sa.JSON(), nullable=True),
        sa.Column('allergies', sa.JSON(), nullable=True),
        sa.Column('medications', sa.JSON(), nullable=True),
        sa.Column('diet_information', sa.Text(), nullable=True),
        sa.Column('current_illnesses', sa.JSON(), nullable=True),
        sa.Column('family_history', sa.JSON(), nullable=True),
        sa.Column('habits', sa.JSON(), nullable=True),
        sa.Column('medical_history', sa.JSON(), nullable=True),
        sa.Column('work_information', sa.Text(), nullable=True),
        sa.Column('summary_text', sa.Text(), nullable=True),
        sa.Column('source_language', sa.String(length=8), nullable=False),
        sa.Column('localized_versions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('last_updated_message_id', sa.Integer(), nullable=True),
        sa.Column('update_count', sa.Integer(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['last_updated_message_id'], ['interview_messages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['medical_interview_id'], ['medical_interviews.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_progress_summaries_id'), 'progress_summaries', ['id'], unique=False)
    op.create_index('ix_progress_summaries_localized_versions', 'progress_summaries', ['localized_versions'], unique=False, postgresql_using='gin')
    op.create_index(op.f('ix_progress_summaries_medical_interview_id'), 'progress_summaries', ['medical_interview_id'], unique=True)
    op.create_table(
        'teacher_ratings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('assignment_id', sa.Integer(), nullable=False),
        sa.Column('rubric_version', sa.String(length=80), nullable=False),
        sa.Column('rubric_snapshot', sa.JSON(), nullable=False),
        sa.Column('results', sa.JSON(), nullable=False),
        sa.Column('overall_score', sa.Float(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['assignment_id'], ['teacher_assignments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assignment_id'),
    )
    op.create_table(
        'turn_video_analyses',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('medical_interview_id', sa.Integer(), nullable=False),
        sa.Column('recording_id', sa.String(length=36), nullable=False),
        sa.Column('turn_id', sa.String(length=36), nullable=False),
        sa.Column('speaker', sa.String(length=20), nullable=False),
        sa.Column('start_ms', sa.BigInteger(), nullable=False),
        sa.Column('end_ms', sa.BigInteger(), nullable=False),
        sa.Column('storage_key', sa.String(length=500), nullable=True),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('roi_snapshots', sa.JSON(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('queued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('end_ms >= start_ms', name='ck_turn_video_analysis_window'),
        sa.CheckConstraint('size_bytes >= 0', name='ck_turn_video_analysis_size'),
        sa.ForeignKeyConstraint(['medical_interview_id'], ['medical_interviews.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recording_id'], ['interview_recordings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['turn_id'], ['interview_turns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('recording_id', 'turn_id', name='uq_turn_video_analysis_recording_turn'),
        sa.UniqueConstraint('storage_key'),
    )
    op.create_index(op.f('ix_turn_video_analyses_medical_interview_id'), 'turn_video_analyses', ['medical_interview_id'], unique=False)
    op.create_index(op.f('ix_turn_video_analyses_recording_id'), 'turn_video_analyses', ['recording_id'], unique=False)
    op.create_index(op.f('ix_turn_video_analyses_status'), 'turn_video_analyses', ['status'], unique=False)
    op.create_index(op.f('ix_turn_video_analyses_turn_id'), 'turn_video_analyses', ['turn_id'], unique=True)
    install_evaluation_run_trigger(op)


def create_processing_jobs(operations) -> None:
    operations.create_table(
        'interview_processing_jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('medical_interview_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='queued', nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error_code', sa.String(length=80), nullable=True),
        sa.Column('queued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['medical_interview_id'], ['medical_interviews.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    operations.create_index(
        'uq_active_interview_processing_job',
        'interview_processing_jobs',
        ['medical_interview_id', 'kind'],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'processing')"),
    )


def install_evaluation_run_trigger(operations) -> None:
    operations.execute("""CREATE FUNCTION reject_evaluation_run_update() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Evaluation run snapshots cannot be updated'; END; $$""")
    operations.execute("""CREATE TRIGGER evaluation_runs_append_only BEFORE UPDATE ON interview_evaluation_runs
        FOR EACH ROW EXECUTE FUNCTION reject_evaluation_run_update()""")


def downgrade() -> None:
    raise RuntimeError("Downgrading the release baseline would erase application data. Restore a backup instead.")
