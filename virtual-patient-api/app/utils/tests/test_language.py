"""Tests for interview-specific patient response languages."""

import unittest

from pydantic import ValidationError

from app.models.medical_interview import MedicalInterviewCreate
from app.utils.language import (
    resolve_patient_response_language,
    resolve_ui_language,
    with_patient_response_language,
)


class PatientResponseLanguageTests(unittest.TestCase):
    def test_interview_language_overrides_account_language(self) -> None:
        metadata = with_patient_response_language({"source": "ui"}, "es")

        self.assertEqual(
            resolve_patient_response_language(metadata, legacy_language_code="en"),
            "es",
        )
        self.assertEqual(metadata["source"], "ui")

    def test_legacy_interview_uses_account_language(self) -> None:
        self.assertEqual(
            resolve_patient_response_language({}, legacy_language_code="es"),
            "es",
        )

    def test_create_contract_rejects_unsupported_language(self) -> None:
        with self.assertRaises(ValidationError):
            MedicalInterviewCreate(
                clinical_case_id=1,
                patient_response_language="fr",
            )

    def test_ui_language_is_resolved_independently(self) -> None:
        self.assertEqual(resolve_ui_language("es", "en"), "es")
        self.assertEqual(resolve_ui_language(None, "es"), "es")
        self.assertEqual(resolve_ui_language("fr", "fr"), "en")


if __name__ == "__main__":
    unittest.main()
