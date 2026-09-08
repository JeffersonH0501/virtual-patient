"""PostgreSQL migration checks in an isolated, rolled-back schema."""

import importlib.util
from pathlib import Path
import unittest
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa
from app.core.database import engine


class EmailIdentityMigrationTests(unittest.TestCase):
    def setUp(self):
        if engine.dialect.name != "postgresql":
            self.skipTest("Requires configured PostgreSQL")
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        schema = "identity_test_" + uuid4().hex
        self.connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        self.connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
        self.connection.execute(sa.text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY, username VARCHAR UNIQUE,
                email VARCHAR UNIQUE, full_name VARCHAR
            )
        """))
        self.connection.execute(sa.text("""
            INSERT INTO users VALUES
                (1, 'legacy.one', 'One@example.org', 'Ana Maria De la Cruz'),
                (2, 'legacy.two', 'two@example.org', NULL)
        """))
        source = Path(__file__).resolve().parents[3] / "alembic/versions/021_email_identity.py"
        spec = importlib.util.spec_from_file_location("identity_migration", source)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        self.context = MigrationContext.configure(self.connection)

    def tearDown(self):
        self.transaction.rollback()
        self.connection.close()

    def test_upgrade_preserves_names_and_downgrade_restores_retired_fields(self):
        before = self.connection.execute(sa.text("SELECT * FROM users ORDER BY id")).all()
        with Operations.context(self.context):
            self.migration.upgrade()
        row = self.connection.execute(sa.text("SELECT * FROM users WHERE id=1")).mappings().one()
        self.assertEqual(row["first_name"], "Ana Maria De la Cruz")
        self.assertEqual(row["last_name"], "")
        self.assertEqual(row["email"], "one@example.org")
        self.assertNotIn("username", row)
        self.assertNotIn("full_name", row)
        with self.connection.begin_nested() as savepoint:
            with self.assertRaises(sa.exc.IntegrityError):
                self.connection.execute(sa.text("""
                    INSERT INTO users (id, email, first_name, last_name)
                    VALUES (3, 'ONE@example.org', 'Test', 'User')
                """))
            savepoint.rollback()
        with Operations.context(self.context):
            self.migration.downgrade()
        after = self.connection.execute(sa.text("SELECT id, username, email, full_name FROM users ORDER BY id")).all()
        self.assertEqual(before, after)

    def test_duplicate_email_stops_before_schema_changes(self):
        self.connection.execute(sa.text("UPDATE users SET email='ONE@example.org' WHERE id=2"))
        with Operations.context(self.context), self.assertRaisesRegex(RuntimeError, "duplicate"):
            self.migration.upgrade()
        self.assertIn("username", [column["name"] for column in sa.inspect(self.connection).get_columns("users")])

    def test_missing_email_stops_before_schema_changes(self):
        self.connection.execute(sa.text("UPDATE users SET email=NULL WHERE id=2"))
        with Operations.context(self.context), self.assertRaisesRegex(RuntimeError, "valid email"):
            self.migration.upgrade()
