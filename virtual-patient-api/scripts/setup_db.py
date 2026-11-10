#!/usr/bin/env python3
"""Prepare the current database schema without deleting existing data."""

import argparse
from pathlib import Path
import sys

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.langgraph_schema import ensure_langgraph_schema  # noqa: E402
from app.core.superuser import synchronize_superuser  # noqa: E402
from app.models.clinical_case import CaseType, ClinicalCaseDB  # noqa: E402
from app.models.organization import OrganizationDB  # noqa: E402
from app.models.personality import PersonalityDB  # noqa: E402
from scripts.adopt_release_baseline import PREVIOUS_HEAD, adopt_release_baseline  # noqa: E402
from scripts.seed_clinical_cases import seed_clinical_cases  # noqa: E402
from scripts.seed_personalities import main as seed_personalities  # noqa: E402


def alembic_config() -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return config


def ensure_schema() -> str:
    """Upgrade a fresh or known database without rewriting existing rows."""
    config = alembic_config()
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(145129873, 1)"))
        config.attributes["connection"] = connection
        schema = connection.scalar(text("SELECT current_schema()"))
        tables = set(inspect(connection).get_table_names(schema=schema))
        heads = MigrationContext.configure(connection).get_current_heads()
        if not heads and tables - {"alembic_version"}:
            raise RuntimeError(
                "Existing tables have no Alembic revision. Back up the database and "
                "verify its schema and revision using the previous deployment."
            )
        if heads == (PREVIOUS_HEAD,):
            adopt_release_baseline(connection, config)
        else:
            known_revisions = {revision.revision for revision in ScriptDirectory.from_config(config).walk_revisions()}
            if set(heads) - known_revisions:
                raise RuntimeError(
                    f"Unsupported database revision: {', '.join(heads)}. Back up the database "
                    f"and upgrade it to {PREVIOUS_HEAD} using the previous deployment before retrying."
                )
        command.upgrade(config, "head")
    return "Prepared the application schema at the current Alembic revision"


def count_rows(model: type) -> int:
    with SessionLocal() as session:
        return len(session.scalars(select(model.id)).all())


def ensure_default_organization() -> None:
    """Ensure user creation always has an active organization on blank schemas."""
    with SessionLocal() as session:
        organization = session.scalars(
            select(OrganizationDB)
            .where(OrganizationDB.active.is_(True))
            .order_by(OrganizationDB.id)
        ).first()
        if organization is not None:
            print(f"Keeping active organization {organization.id}: {organization.name}")
            return
        session.add(
            OrganizationDB(
                name="Default Medical Organization",
                description="Default organization for local and initial deployments",
                active=True,
            )
        )
        session.commit()
        print("Created the default active organization")


def ensure_single_superuser() -> None:
    """Provision the sole superuser from deployment configuration."""
    with SessionLocal() as session:
        print(synchronize_superuser(session))


def seed_empty_reference_tables() -> None:
    with SessionLocal() as session:
        default_case_count = len(
            session.scalars(
                select(ClinicalCaseDB.id).where(
                    ClinicalCaseDB.case_type == CaseType.DEFAULT
                )
            ).all()
        )
        personality_count = len(session.scalars(select(PersonalityDB.id)).all())

    if default_case_count == 0:
        if not seed_clinical_cases():
            raise RuntimeError("Clinical-case seed failed")
    else:
        print(f"Keeping {default_case_count} existing default clinical cases")

    if personality_count == 0:
        if seed_personalities() != 0:
            raise RuntimeError("Personality seed failed")
    else:
        print(f"Keeping {personality_count} existing personalities")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Prepare the schema without inserting reference cases or personalities",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(ensure_schema())
    print(ensure_langgraph_schema())
    ensure_default_organization()
    ensure_single_superuser()
    if not args.skip_seed:
        seed_empty_reference_tables()
    print(f"Clinical cases: {count_rows(ClinicalCaseDB)}")
    print(f"Personalities: {count_rows(PersonalityDB)}")
    print("Database setup completed without deleting existing data")


if __name__ == "__main__":
    main()
