"""Historical durations use media/turn evidence and preserve lifecycle dates."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

from alembic.operations import Operations
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
import pytest

from app.core.database import engine


def test_historical_duration_backfill_prefers_confirmed_recording_and_keeps_unknown_null():
    spec = spec_from_file_location("duration_migration", Path("alembic/versions/008_recorded_interview_durations.py"))
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.connect() as db, db.begin() as transaction:
        schema = "test_duration_" + uuid4().hex
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
        db.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        db.execute(text("CREATE TABLE medical_interviews (id int PRIMARY KEY, status text, total_duration int, start_time timestamptz, end_time timestamptz)"))
        db.execute(text("CREATE TABLE interview_recordings (medical_interview_id int, status text, duration_ms bigint, ended_at timestamptz)"))
        db.execute(text("CREATE TABLE interview_turns (medical_interview_id int, end_ms bigint)"))
        db.execute(text("INSERT INTO medical_interviews VALUES (25158,'COMPLETED',1110,'2026-11-01 10:00+00','2026-11-01 10:18:30+00'), (2,'COMPLETED',1110,NULL,NULL), (3,'INTERRUPTED',1110,NULL,NULL), (4,'IN_PROGRESS',NULL,NULL,NULL)"))
        db.execute(text("INSERT INTO interview_turns VALUES (25158,50600), (2,80000), (4,25000)"))
        db.execute(text("INSERT INTO interview_recordings VALUES (2,'partial',60000,now())"))
        original_dates = db.execute(text("SELECT start_time,end_time FROM medical_interviews WHERE id=25158")).one()
        with Operations.context(MigrationContext.configure(db)):
            migration.upgrade()
            migration.upgrade()
        assert db.execute(text("SELECT id,total_duration FROM medical_interviews ORDER BY id")).all() == [(2,60),(3,None),(4,None),(25158,51)]
        assert db.execute(text("SELECT start_time,end_time FROM medical_interviews WHERE id=25158")).one() == original_dates
        transaction.rollback()


def test_segment_migration_preserves_legacy_rows_and_enforces_one_active_segment():
    spec = spec_from_file_location("segment_migration", Path("alembic/versions/007_recording_segments.py"))
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.connect() as db, db.begin() as transaction:
        schema = "test_segment_" + uuid4().hex
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
        db.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        db.execute(text("CREATE TABLE interview_recordings (id varchar(36) PRIMARY KEY)"))
        db.execute(text("CREATE TABLE interview_media_assets (id text PRIMARY KEY, recording_id varchar(36) REFERENCES interview_recordings(id), kind text, CONSTRAINT uq_recording_media_kind UNIQUE(recording_id,kind))"))
        db.execute(text("CREATE TABLE interview_turns (id text PRIMARY KEY, end_ms bigint)"))
        db.execute(text("INSERT INTO interview_recordings VALUES ('recording')"))
        db.execute(text("INSERT INTO interview_media_assets VALUES ('legacy','recording','student_video')"))
        db.execute(text("INSERT INTO interview_turns VALUES ('legacy-turn',50600)"))
        with Operations.context(MigrationContext.configure(db)):
            migration.upgrade()
            assert db.execute(text("SELECT id,segment_id FROM interview_media_assets")).all() == [('legacy',None)]
            assert db.execute(text("SELECT id,end_ms,segment_id FROM interview_turns")).all() == [('legacy-turn',50600,None)]
            insert = text("INSERT INTO interview_recording_segments (id,recording_id,sequence,offset_ms,capture_config,calibration) VALUES (:id,'recording',:sequence,0,'{}','{}')")
            db.execute(insert, {"id": "first", "sequence": 0})
            with pytest.raises(IntegrityError), db.begin_nested():
                db.execute(insert, {"id": "second", "sequence": 1})
            with pytest.raises(RuntimeError, match="Cannot downgrade"):
                migration.downgrade()
            db.execute(text("DELETE FROM interview_recording_segments"))
            migration.downgrade()
            assert db.execute(text("SELECT id,end_ms FROM interview_turns")).all() == [('legacy-turn',50600)]
        transaction.rollback()
