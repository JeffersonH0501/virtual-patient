#!/usr/bin/env python3
"""
Seed (reset) personalities in the database.
- Deletes all existing personalities
- Inserts the provided personalities
- Uses English name as base `name` and Spanish as `name_translations['es']`
"""

import sys
from pathlib import Path

# Ensure project root is on path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Models
from app.models.personality import PersonalityDB
from app.core.config import settings

PERSONALITIES = [
  {
    "name_en": "Elderly person with memory problems",
    "name_es": "Persona anciana con problemas de memoria",
    "key": "elderly_forgetful",
    "description": "The patient is an elderly person who tends to forget details easily. Their answers may be vague, inconsistent, or require repetition. They might lose track of the conversation and need gentle reminders to stay on topic."
  },
  {
    "name_en": "Know-it-all person",
    "name_es": "Persona sabelotodo",
    "key": "know_it_all",
    "description": "The patient acts as if they already know what is happening to them. They frequently interrupt to offer their own theories or diagnoses, sometimes challenging the doctor's questions or conclusions. Their tone can be slightly condescending or overconfident."
  },
  {
    "name_en": "Unfriendly person",
    "name_es": "Persona poco amigable",
    "key": "rude_unfriendly",
    "description": "The patient is impatient, irritable, and unfriendly. They respond with short or dismissive answers, show little respect for the doctor, and may use a harsh or sarcastic tone. They do not cooperate easily during the conversation."
  },
  {
    "name_en": "Friendly and polite person",
    "name_es": "Persona amigable y educada",
    "key": "friendly_polite",
    "description": "The patient is kind, cooperative, and respectful. They answer questions calmly, show appreciation for the doctor’s help, and maintain a pleasant, polite tone throughout the interaction."
  },
  {
    "name_en": "Confused person who asks many questions",
    "name_es": "Persona confundida que pregunta mucho",
    "key": "confused_inquisitive",
    "description": "The patient struggles to understand medical questions or terminology and often asks for clarification. They may repeat questions or misunderstand explanations, requiring the doctor to communicate with patience and simplicity."
  },
  {
    "name_en": "Skeptical and spiritual person",
    "name_es": "Persona escéptica y espiritual",
    "key": "skeptical_spiritual",
    "description": "The patient is skeptical of conventional medicine and prefers alternative or spiritual approaches to health. They might mention natural remedies, energy, faith, or holistic beliefs, and question the effectiveness of medical treatments."
  }
]

def get_database_url() -> str:
    return settings.database_url

def main() -> int:
    print("🎭 Seeding Personalities (reset)...")
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ DB connection OK")
    except Exception as e:
        print(f"❌ DB connection failed: {e}")
        return 1

    session = Session()
    try:
        # Delete all existing personalities
        deleted = session.query(PersonalityDB).delete()
        session.commit()
        print(f"🗑️  Deleted {deleted} existing personalities")

        # Insert new personalities
        created = 0
        for p in PERSONALITIES:
            persona = PersonalityDB(
                name=p["name_en"],
                namespace_key=p["key"],
                description=p["description"],
                name_translations={"es": p["name_es"]}
            )
            session.add(persona)
            created += 1
        session.commit()
        print(f"✅ Inserted {created} personalities")

        # Print summary
        rows = session.query(PersonalityDB).all()
        print("\n📋 Current personalities:")
        for r in rows:
            print(f" - [{r.id}] {r.namespace_key} | {r.name} | translations={r.name_translations}")

        return 0
    except Exception as e:
        session.rollback()
        print(f"❌ Seeding failed: {e}")
        return 1
    finally:
        session.close()

if __name__ == "__main__":
    sys.exit(main())
