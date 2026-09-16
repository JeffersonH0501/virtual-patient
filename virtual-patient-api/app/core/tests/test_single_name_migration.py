"""PostgreSQL migration checks for the single ``name`` column consolidation."""

import importlib.util
from pathlib import Path
import unittest
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa
from app.core.database import engine


class SingleNameMigrationTests(unittest.TestCase):
    def setUp(self):
        if engine.dialect.name != "postgresql":
            self.skipTest("Requires configured PostgreSQL")
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        schema = "single_name_test_" + uuid4().hex
        self.connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        self.connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
        # Post-021 shape: separate first_name/last_name, both NOT NULL.
        self.connection.execute(sa.text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                email VARCHAR NOT NULL,
                first_name VARCHAR NOT NULL,
                last_name VARCHAR NOT NULL
            )
        """))
        self.connection.execute(sa.text("""
            INSERT INTO users VALUES
                (1, 'one@example.org', 'Ana Maria De la Cruz', ''),
                (2, 'two@example.org', 'John', 'Doe')
        """))
        source = Path(__file__).resolve().parents[3] / "alembic/versions/025_single_name.py"
        spec = importlib.util.spec_from_file_location("single_name_migration", source)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        self.context = MigrationContext.configure(self.connection)

    def tearDown(self):
        self.transaction.rollback()
        self.connection.close()

    def test_upgrade_backfills_name_and_downgrade_restores_split(self):
        with Operations.context(self.context):
            self.migration.upgrade()

        rows = self.connection.execute(
            sa.text("SELECT id, name FROM users ORDER BY id")
        ).mappings().all()
        # Empty last_name yields no trailing space; a real last_name joins with one space.
        self.assertEqual(rows[0]["name"], "Ana Maria De la Cruz")
        self.assertEqual(rows[1]["name"], "John Doe")

        columns = [c["name"] for c in sa.inspect(self.connection).get_columns("users")]
        self.assertNotIn("first_name", columns)
        self.assertNotIn("last_name", columns)
        self.assertIn("name", columns)

        with Operations.context(self.context):
            self.migration.downgrade()

        restored = self.connection.execute(
            sa.text("SELECT id, first_name, last_name FROM users ORDER BY id")
        ).mappings().all()
        # Downgrade puts the whole name back into first_name and leaves last_name empty.
        self.assertEqual(restored[0]["first_name"], "Ana Maria De la Cruz")
        self.assertEqual(restored[0]["last_name"], "")
        self.assertEqual(restored[1]["first_name"], "John Doe")
        self.assertEqual(restored[1]["last_name"], "")

        columns_after = [c["name"] for c in sa.inspect(self.connection).get_columns("users")]
        self.assertNotIn("name", columns_after)

    def test_name_is_not_null_after_upgrade(self):
        with Operations.context(self.context):
            self.migration.upgrade()
        with self.connection.begin_nested() as savepoint:
            with self.assertRaises(sa.exc.IntegrityError):
                self.connection.execute(sa.text("""
                    INSERT INTO users (id, email, name) VALUES (3, 'three@example.org', NULL)
                """))
            savepoint.rollback()
