#!/usr/bin/env python3
"""Prepare the current database schema without deleting existing data."""

import argparse
from pathlib import Path
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.langgraph_schema import ensure_langgraph_schema  # noqa: E402
import app.models  # noqa: E402,F401 - register all model metadata
from app.models.clinical_case import CaseType, ClinicalCaseDB  # noqa: E402
from app.models.organization import OrganizationDB  # noqa: E402
from app.models.personality import PersonalityDB  # noqa: E402
from scripts.seed_clinical_cases import seed_clinical_cases  # noqa: E402
from scripts.seed_personalities import main as seed_personalities  # noqa: E402


def alembic_config() -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return config


def ensure_schema() -> str:
    """Create a blank schema or migrate a schema already tracked by Alembic."""
    initial_tables = set(inspect(engine).get_table_names())
    application_tables = initial_tables - {"alembic_version"}

    if application_tables and "alembic_version" not in initial_tables:
        names = ", ".join(sorted(application_tables))
        raise RuntimeError(
            "Existing application tables have no Alembic version. Refusing to "
            "guess their schema or overwrite data. Back up and migrate this "
            f"database explicitly. Tables found: {names}"
        )

    config = alembic_config()
    if application_tables:
        command.upgrade(config, "head")
        Base.metadata.create_all(bind=engine)
        return "Migrated the existing database to the current revision"

    # The inherited migration history is incremental and cannot construct the
    # original schema from zero. Current models are therefore authoritative for
    # a blank database; stamping records the matching migration baseline.
    Base.metadata.create_all(bind=engine)
    command.stamp(config, "head")
    return "Created a new database from the current models and stamped it at head"


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
    if not args.skip_seed:
        seed_empty_reference_tables()
    print(f"Clinical cases: {count_rows(ClinicalCaseDB)}")
    print(f"Personalities: {count_rows(PersonalityDB)}")
    print("Database setup completed without deleting existing data")


if __name__ == "__main__":
    main()
