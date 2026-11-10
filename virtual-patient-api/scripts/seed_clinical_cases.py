#!/usr/bin/env python3
"""Insert the bundled cases into an empty default catalog."""

from pathlib import Path
import sys

from sqlalchemy import select, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.core.functional_config import CONFIG_ROOT, read_config_json
from app.models.clinical_case import CaseType, ClinicalCaseDB

TRANSLATABLE_FIELDS = (
    "title", "description", "physical_requirements", "socioeconomic_status",
    "female_name", "male_name", "patient_context", "chief_complaint",
    "present_illness", "personal_medical_history", "surgical_history",
    "family_history", "medications", "habits", "allergies", "concerns",
)
REQUIRED_FIELDS = {*TRANSLATABLE_FIELDS, "key", "icon", "age", "weight_in_kg", "female_photo", "male_photo"}


def load_case_seeds() -> list[dict]:
    paths = sorted((CONFIG_ROOT / "clinical_cases").glob("*.json"))
    if not paths:
        raise ValueError("No clinical case files found")

    seeds = []
    for path in paths:
        data = read_config_json(f"clinical_cases/{path.name}")
        if not isinstance(data, dict) or data.keys() != {"en", "es"}:
            raise ValueError(f"{path}: expected English and Spanish cases")
        for locale, case in data.items():
            if not isinstance(case, dict) or not REQUIRED_FIELDS <= case.keys() or (
                case.keys() - REQUIRED_FIELDS - {"gender_restriction"}
            ):
                raise ValueError(f"{path}: invalid {locale} case fields")
            if (
                case["key"] != path.stem
                or any(not isinstance(case[field], str) for field in REQUIRED_FIELDS - {"age", "weight_in_kg"})
                or not case["title"].strip()
                or not case["description"].strip()
                or type(case["age"]) is not int
                or type(case["weight_in_kg"]) not in (int, float)
                or case.get("gender_restriction") not in (None, "female", "male")
            ):
                raise ValueError(f"{path}: invalid {locale} case values")

        english, spanish = data["en"], data["es"]
        fields = {field: value for field, value in english.items() if field != "key"}
        translations = {
            f"{field}_translations": {"es": spanish[field]} if english[field] and spanish[field] else {}
            for field in TRANSLATABLE_FIELDS
        }
        seeds.append({
            **fields, **translations, "case_key": english["key"],
            "case_type": CaseType.DEFAULT, "active": True,
        })
    return seeds


def seed_clinical_cases() -> bool:
    try:
        seeds = load_case_seeds()
        with SessionLocal.begin() as session:
            session.execute(text("LOCK TABLE clinical_cases IN SHARE ROW EXCLUSIVE MODE"))
            present = session.scalar(select(ClinicalCaseDB.id).where(
                ClinicalCaseDB.case_type == CaseType.DEFAULT,
            ).limit(1))
            if present is not None:
                print("Keeping existing default clinical cases")
                return True
            session.add_all(ClinicalCaseDB(**fields) for fields in seeds)
    except Exception as exc:
        print(f"Clinical case seeding failed: {exc}", file=sys.stderr)
        return False

    print(f"Inserted {len(seeds)} default clinical cases")
    return True


if __name__ == "__main__":
    sys.exit(0 if seed_clinical_cases() else 1)
