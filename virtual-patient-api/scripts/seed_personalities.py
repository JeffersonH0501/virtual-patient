#!/usr/bin/env python3
"""Insert the bundled personalities into an empty catalog."""

from pathlib import Path
import sys

from sqlalchemy import select, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.core.functional_config import read_config_json
from app.models.personality import PersonalityCreate, PersonalityDB


def load_personality_seeds() -> list[PersonalityCreate]:
    source = read_config_json("personalities/seed.json")
    if not isinstance(source, list) or not source:
        raise ValueError("Expected a nonempty personality seed list")

    seeds = []
    keys = set()
    for entry in source:
        if not isinstance(entry, dict) or entry.keys() != {"key", "name_en", "name_es", "description"}:
            raise ValueError("Invalid personality seed fields")
        if not all(isinstance(value, str) and value.strip() for value in entry.values()):
            raise ValueError("Invalid personality seed values")
        if entry["key"] in keys:
            raise ValueError(f"Duplicate personality seed: {entry['key']}")
        keys.add(entry["key"])
        seeds.append(PersonalityCreate(
            name=entry["name_en"], namespace_key=entry["key"],
            description=entry["description"], name_translations={"es": entry["name_es"]},
        ))
    return seeds


def main() -> int:
    try:
        seeds = load_personality_seeds()
        with SessionLocal.begin() as session:
            session.execute(text("LOCK TABLE personalities IN SHARE ROW EXCLUSIVE MODE"))
            if session.scalar(select(PersonalityDB.id).limit(1)) is not None:
                print("Keeping existing personalities")
                return 0
            session.add_all(PersonalityDB(**entry.model_dump()) for entry in seeds)
    except Exception as exc:
        print(f"Personality seeding failed: {exc}", file=sys.stderr)
        return 1

    print(f"Inserted {len(seeds)} personalities")
    return 0


if __name__ == "__main__":
    sys.exit(main())
