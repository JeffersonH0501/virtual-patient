"""Exercise setup in rollback-only PostgreSQL schemas."""

from contextlib import contextmanager
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.database import engine
from scripts import setup_db
from scripts.adopt_release_baseline import BASELINE, PREVIOUS_HEAD

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_MIGRATION_TEST") != "1",
    reason="Requires explicitly enabled existing Docker PostgreSQL",
)


@pytest.fixture
def connection(monkeypatch):
    with engine.connect() as db, db.begin() as transaction:
        schema = f"test_release_{uuid4().hex}"
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
        db.execute(text(f'SET LOCAL search_path TO "{schema}"'))

        @contextmanager
        def begin():
            with db.begin_nested():
                yield db

        monkeypatch.setattr(setup_db, "engine", SimpleNamespace(begin=begin))
        yield db
        transaction.rollback()


def seed_interview(connection):
    statements = (
        "INSERT INTO organizations (id, name) VALUES (1, 'Synthetic')",
        "INSERT INTO users (id, email, name, role, organization_id) "
        "VALUES (1, 'example@example.invalid', 'Synthetic', 'student', 1)",
        "INSERT INTO clinical_cases (id, title, description, case_type) "
        "VALUES (1, 'Synthetic', 'Fixture', 'default')",
        "INSERT INTO medical_interviews (id, public_id, user_id, clinical_case_id, status) "
        "VALUES (1, 'synthetic01', 1, 1, 'COMPLETED')",
        "INSERT INTO interview_evaluations (medical_interview_id, evaluation_results) VALUES (1, '[]')",
        "INSERT INTO interview_evaluation_runs (id, medical_interview_id, evaluation_condition, snapshot) "
        "VALUES ('run-1', 1, 'TEXT_ONLY', '{}')",
    )
    for statement in statements:
        connection.execute(text(statement))


def test_setup_bootstraps_postgresql_schema_and_preserves_database_guards(connection):
    setup_db.ensure_schema()
    setup_db.ensure_schema()
    assert MigrationContext.configure(connection).get_current_heads() == ("002_canonical_feature_families",)
    seed_interview(connection)
    assert connection.scalar(text("SELECT created_at FROM users WHERE id = 1")).tzinfo is not None
    assert connection.scalar(text("SELECT evaluation_condition FROM interview_evaluations")) == "TEXT_ONLY"
    connection.execute(text(
        "INSERT INTO interview_evaluations (medical_interview_id, evaluation_condition, evaluation_results) "
        "VALUES (1, 'TEXT_PLUS_MULTIMODAL', '[]')"
    ))
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(text(
            "INSERT INTO interview_evaluations (medical_interview_id, evaluation_results) VALUES (1, '[]')"
        ))
    with pytest.raises(DBAPIError, match="Evaluation run snapshots cannot be updated"), connection.begin_nested():
        connection.execute(text("UPDATE interview_evaluation_runs SET snapshot = '{}'"))
    insert_job = text(
        "INSERT INTO interview_processing_jobs (id, medical_interview_id, kind, payload) "
        "VALUES (:job_id, 1, 'test', '{}') RETURNING status, attempts"
    )
    assert connection.execute(insert_job, {"job_id": "job-1"}).one() == ("queued", 0)
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(insert_job, {"job_id": "job-2"})


@pytest.mark.parametrize("bootstrap_omissions", [False, True])
def test_setup_adopts_verified_previous_head_without_rewriting_data(connection, bootstrap_omissions):
    setup_db.ensure_schema()
    seed_interview(connection)
    connection.execute(text("UPDATE alembic_version SET version_num = :revision"), {"revision": PREVIOUS_HEAD})
    if bootstrap_omissions:
        connection.execute(text("DROP TABLE interview_processing_jobs"))
        connection.execute(text("DROP TRIGGER evaluation_runs_append_only ON interview_evaluation_runs"))
        connection.execute(text("DROP FUNCTION reject_evaluation_run_update()"))

    setup_db.ensure_schema()

    assert MigrationContext.configure(connection).get_current_heads() == ("002_canonical_feature_families",)
    assert connection.scalar(text("SELECT snapshot FROM interview_evaluation_runs WHERE id = 'run-1'")) == {}
    assert inspect(connection).has_table("interview_processing_jobs")
    with pytest.raises(DBAPIError, match="Evaluation run snapshots cannot be updated"), connection.begin_nested():
        connection.execute(text("UPDATE interview_evaluation_runs SET snapshot = '{}'"))


@pytest.mark.parametrize("default", ["queued", "unexpected"])
def test_setup_validates_legacy_incremental_schema(connection, default):
    setup_db.ensure_schema()
    seed_interview(connection)
    connection.execute(text("UPDATE alembic_version SET version_num = :revision"), {"revision": PREVIOUS_HEAD})
    legacy_ddl = (
        "ALTER TABLE interview_recordings ADD UNIQUE (medical_interview_id)",
        "ALTER TABLE medical_interviews ALTER COLUMN status SET DEFAULT 'IN_PROGRESS'",
        "ALTER TABLE progress_summaries ALTER COLUMN localized_versions SET DEFAULT '{}'::jsonb",
        "ALTER TABLE progress_summaries ALTER COLUMN source_language SET DEFAULT 'en'",
        "ALTER TABLE turn_video_analyses ALTER COLUMN roi_snapshots SET DEFAULT '[]'::json",
        "ALTER TABLE turn_video_analyses ALTER COLUMN status SET DEFAULT " + repr(default),
        "ALTER TABLE turn_video_analyses RENAME CONSTRAINT turn_video_analyses_storage_key_key "
        "TO uq_turn_video_analyses_storage_key",
        "ALTER INDEX ix_turn_video_analyses_medical_interview_id RENAME TO ix_turn_video_analyses_interview",
        "ALTER INDEX ix_turn_video_analyses_recording_id RENAME TO ix_turn_video_analyses_recording",
        "ALTER INDEX ix_turn_video_analyses_turn_id RENAME TO uq_turn_video_analyses_turn_id",
        "ALTER TABLE turn_video_analyses ADD UNIQUE USING INDEX uq_turn_video_analyses_turn_id",
        "ALTER TABLE users RENAME CONSTRAINT users_organization_id_fkey TO fk_users_organization_id",
    )
    for statement in legacy_ddl:
        connection.execute(text(statement))

    if default == "queued":
        setup_db.ensure_schema()
        assert MigrationContext.configure(connection).get_current_heads() == ("002_canonical_feature_families",)
    else:
        with pytest.raises(RuntimeError, match="does not match the release schema in: turn_video_analyses"):
            setup_db.ensure_schema()
        assert MigrationContext.configure(connection).get_current_heads() == (PREVIOUS_HEAD,)

    assert connection.scalar(text("SELECT public_id FROM medical_interviews WHERE id = 1")) == "synthetic01"
    assert {"uq_turn_video_analyses_turn_id", "uq_turn_video_analyses_storage_key"} <= {
        item["name"] for item in inspect(connection).get_unique_constraints("turn_video_analyses")
    }


def test_setup_rejects_drift_without_applying_repairs(connection):
    setup_db.ensure_schema()
    connection.execute(text("UPDATE alembic_version SET version_num = :revision"), {"revision": PREVIOUS_HEAD})
    connection.execute(text("DROP INDEX uq_users_email_normalized"))
    connection.execute(text("DROP TABLE interview_processing_jobs"))

    with pytest.raises(RuntimeError, match="does not match the release schema in: users"):
        setup_db.ensure_schema()

    assert MigrationContext.configure(connection).get_current_heads() == (PREVIOUS_HEAD,)
    assert not inspect(connection).has_table("interview_processing_jobs")


def test_setup_refuses_older_revision(connection):
    setup_db.ensure_schema()
    previous = "028_drop_calibration_tables"
    connection.execute(text("UPDATE alembic_version SET version_num = :revision"), {"revision": previous})

    with pytest.raises(RuntimeError, match=f"Unsupported database revision: {previous}"):
        setup_db.ensure_schema()

    assert MigrationContext.configure(connection).get_current_heads() == (previous,)


def test_feature_rename_preserves_measurements_and_snapshots(connection):
    setup_db.ensure_schema()
    seed_interview(connection)
    connection.execute(text("UPDATE alembic_version SET version_num = :revision"), {"revision": BASELINE})
    connection.execute(text("""
        INSERT INTO interview_turns
            (id, medical_interview_id, speaker, sequence, start_ms, end_ms,
             transcript, input_source, timing_source, timing_quality, paraverbal)
        VALUES ('synthetic-turn', 1, 'student', 0, 0, 1000,
                'Synthetic', 'audio', 'recording', 'measured',
                '{"raw":{"speech_rate_wpm": 120},"integrated_labels":
                  {"temporal":{"value":"typical_temporal_pattern","confidence": 1}}}')
    """))
    connection.execute(text("""
        INSERT INTO interview_recordings
            (id, medical_interview_id, status, started_at, capture_config, consent_basis, consent_policy_version)
        VALUES ('synthetic-recording', 1, 'ready', now(),
                '{"learning_moments": {"moments": [
                    {"evidence_used": ["smile_behavior", "head_gestural_feedback"], "observation": "temporal"}
                ]}}', 'test', 'test')
    """))
    setup_db.ensure_schema()
    moment = connection.scalar(text(
        "SELECT capture_config #> '{learning_moments,moments,0}' FROM interview_recordings"
    ))
    assert moment == {"evidence_used": ["smile_activity", "head_nods"], "observation": "temporal"}
    layer = connection.scalar(text("SELECT paraverbal FROM interview_turns WHERE id='synthetic-turn'"))
    assert layer == {
        "raw": {"speech_rate_wpm": 120},
        "integrated_labels": {"speech_timing": {"value": "typical_speech_timing_pattern", "confidence": 1}},
    }
    assert connection.scalar(text("SELECT snapshot FROM interview_evaluation_runs WHERE id='run-1'")) == {}