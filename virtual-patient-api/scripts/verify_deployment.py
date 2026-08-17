#!/usr/bin/env python3
"""Verify the database baseline without invoking external providers."""

from pathlib import Path
import sys

from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import engine  # noqa: E402


REQUIRED_LANGGRAPH_TABLES = {
    "checkpoint_blobs",
    "checkpoint_migrations",
    "checkpoint_writes",
    "checkpoints",
    "store",
    "store_migrations",
}


def scalar(query: str):
    with engine.connect() as connection:
        return connection.execute(text(query)).scalar_one()


def main() -> None:
    case_count = scalar("SELECT COUNT(*) FROM clinical_cases")
    personality_count = scalar("SELECT COUNT(*) FROM personalities")
    alembic_revision = scalar("SELECT version_num FROM alembic_version")

    if case_count < 1:
        raise RuntimeError("No clinical cases are available")
    if personality_count < 1:
        raise RuntimeError("No personalities are available")

    available_tables = set(inspect(engine).get_table_names())
    missing_langgraph_tables = REQUIRED_LANGGRAPH_TABLES - available_tables
    if missing_langgraph_tables:
        missing = ", ".join(sorted(missing_langgraph_tables))
        raise RuntimeError(f"Missing LangGraph persistence tables: {missing}")

    print(f"Clinical cases: {case_count}")
    print(f"Personalities: {personality_count}")
    print(f"Alembic revision: {alembic_revision}")
    print("LangGraph persistence tables: ready")


if __name__ == "__main__":
    main()
