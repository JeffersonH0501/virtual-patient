"""PostgreSQL checks for promotion of Py-Feat observations."""

import importlib.util
from pathlib import Path
import unittest
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa

from app.core.database import engine


class PyFeatPrimaryMigrationTests(unittest.TestCase):
    def setUp(self):
        if engine.dialect.name != "postgresql":
            self.skipTest("Requires configured PostgreSQL")
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        schema = "pyfeat_test_" + uuid4().hex
        self.connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        self.connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
        self.connection.execute(sa.text("""
            CREATE TABLE interview_turns (
                id INTEGER PRIMARY KEY,
                paraverbal JSON,
                nonverbal_features JSON,
                pyfeat_nonverbal_features JSON
            )
        """))
        self.connection.execute(sa.text("""
            INSERT INTO interview_turns VALUES
                (1,
                 '{"speaking_rate_wpm": 120, "pause_total_ms": 300,
                    "f0_median_hz": 55, "f0_iqr_st": 2.5,
                    "loudness_median_rel": -0.4, "loudness_iqr": 1.2}',
                 '{"extractor": {"name": "openface"}}',
                 '{"visual_alignment_dwell_ms": 500,
                    "smile_intensity_mean": 0.7}'),
                (2, NULL, '{"extractor": {"name": "openface"}}', NULL),
                (3, NULL, NULL, NULL)
        """))
        source = Path(__file__).resolve().parents[3] / "alembic/versions/022_promote_pyfeat_observations.py"
        spec = importlib.util.spec_from_file_location("pyfeat_primary_migration", source)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        self.context = MigrationContext.configure(self.connection)

    def tearDown(self):
        self.transaction.rollback()
        self.connection.close()

    def test_upgrade_promotes_pyfeat_and_discards_openface_only_values(self):
        with Operations.context(self.context):
            self.migration.upgrade()

        rows = self.connection.execute(sa.text(
            "SELECT id, paraverbal, nonverbal_features FROM interview_turns ORDER BY id"
        )).mappings().all()
        self.assertEqual(rows[0]["nonverbal_features"]["median_visual_alignment_dwell_ms"], 500)
        self.assertEqual(rows[0]["nonverbal_features"]["mean_smile_activation"], 0.7)
        self.assertIsNone(rows[1]["nonverbal_features"])
        self.assertIsNone(rows[2]["nonverbal_features"])
        self.assertEqual(rows[0]["paraverbal"]["speech_rate_wpm"], 120)
        self.assertEqual(rows[0]["paraverbal"]["total_pause_duration_ms"], 300)
        self.assertAlmostEqual(rows[0]["paraverbal"]["f0_median_semitones"], 12.0)
        self.assertNotIn("f0_p20_p80_range_semitones", rows[0]["paraverbal"])
        self.assertNotIn("median_loudness", rows[0]["paraverbal"])
        columns = {column["name"] for column in sa.inspect(self.connection).get_columns("interview_turns")}
        self.assertNotIn("pyfeat_nonverbal_features", columns)

        with Operations.context(self.context):
            self.migration.downgrade()
        columns = {column["name"] for column in sa.inspect(self.connection).get_columns("interview_turns")}
        self.assertIn("pyfeat_nonverbal_features", columns)
        self.assertIsNone(self.connection.execute(sa.text(
            "SELECT nonverbal_features FROM interview_turns WHERE id=1"
        )).scalar_one())
