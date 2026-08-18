"""Tests for complete progress summary reconstruction."""

from types import SimpleNamespace
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.agents.schemas.progress_summary import ProgressSummarySchema
from app.controllers.progress_summary_controller import ProgressSummaryController


class ProgressSummaryControllerTests(unittest.TestCase):
    def test_to_schema_keeps_every_persisted_summary_field(self) -> None:
        stored_summary = SimpleNamespace(
            age=65,
            weight_in_kg=70.0,
            current_symptoms=[{"symptom": "fatigue"}],
            allergies=["pollen"],
            medications=[{"medication": "aspirin"}],
            diet_information="Low sodium",
            current_illnesses=[{"illness": "COPD"}],
            family_history=[{"relationship": "father", "condition": "diabetes"}],
            habits=[{"habit": "walking"}],
            medical_history=[{
                "type": "hospitalization",
                "description": "Respiratory exacerbation",
                "outcome": "Recovered",
            }],
            work_information="Retired",
            summary_text="Current interview summary",
        )

        result = ProgressSummaryController.to_schema(stored_summary)

        self.assertEqual(result.weight_in_kg, 70.0)
        self.assertEqual(result.habits[0].habit, "walking")
        self.assertEqual(result.medical_history[0].type, "hospitalization")
        self.assertEqual(
            result.medical_history[0].description,
            "Respiratory exacerbation",
        )
        self.assertEqual(result.medical_history[0].outcome, "Recovered")
        self.assertEqual(result.work_information, "Retired")

    def test_canonical_update_invalidates_localized_versions(self) -> None:
        record = SimpleNamespace(
            id=1,
            medical_interview_id=9,
            age=65,
            weight_in_kg=70.0,
            current_symptoms=[],
            allergies=[],
            medications=[],
            diet_information=None,
            current_illnesses=[],
            family_history=[],
            habits=[],
            medical_history=[],
            work_information=None,
            summary_text="Old summary",
            source_language="en",
            localized_versions={"es": {"summary_text": "Resumen anterior"}},
            last_updated_message_id=4,
            update_count=1,
            confidence_score=0.8,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = record
        controller = ProgressSummaryController(db)

        controller.update_progress_summary(
            9,
            ProgressSummarySchema(summary_text="New canonical summary"),
            message_id=5,
        )

        self.assertEqual(record.localized_versions, {})
        self.assertEqual(record.summary_text, "New canonical summary")
        self.assertEqual(record.last_updated_message_id, 5)
