"""PostgreSQL checks for the calibration start-time migration."""

import importlib.util
from pathlib import Path
import unittest
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa

from app.core.database import engine


class InterviewCalibrationMigrationTests(unittest.TestCase):
    def setUp(self):
        if engine.dialect.name != "postgresql":
            self.skipTest("Requires configured PostgreSQL")
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        schema = "calibration_test_" + uuid4().hex
        self.connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        self.connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
        self.connection.execute(sa.text("""
            CREATE TABLE medical_interviews (
                id INTEGER PRIMARY KEY,
                start_time TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        source = Path(__file__).resolve().parents[3] / "alembic/versions/023_add_interview_calibration.py"
        spec = importlib.util.spec_from_file_location("interview_calibration_migration", source)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        self.context = MigrationContext.configure(self.connection)

    def tearDown(self):
        self.transaction.rollback()
        self.connection.close()

    def test_upgrade_allows_draft_and_downgrade_backfills_start_time(self):
        with Operations.context(self.context):
            self.migration.upgrade()
        self.connection.execute(sa.text(
            "INSERT INTO medical_interviews (id, start_time) VALUES (1, NULL)"
        ))

        with Operations.context(self.context):
            self.migration.downgrade()

        start_time = self.connection.execute(sa.text(
            "SELECT start_time FROM medical_interviews WHERE id = 1"
        )).scalar_one()
        self.assertIsNotNone(start_time)
        column = next(
            item for item in sa.inspect(self.connection).get_columns("medical_interviews")
            if item["name"] == "start_time"
        )
        self.assertFalse(column["nullable"])
