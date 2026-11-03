"""Tests for the shared patient speech and avatar profile."""

import unittest

from app.speech.patient_profile import build_patient_speech_profile


class PatientSpeechProfileTests(unittest.TestCase):
    def test_profile_normalizes_language_gender_and_personality(self) -> None:
        profile = build_patient_speech_profile(
            "Spanish",
            "elderly_forgetful",
            "Female",
        )

        self.assertEqual(profile.language, "es")
        self.assertEqual(profile.gender, "female")
        self.assertEqual(profile.personality_key, "elderly_forgetful")
        self.assertEqual(profile.voice, "echo")
        self.assertEqual(profile.vocal_style_key, "elderly_forgetful")
        self.assertEqual(
            profile.as_metadata(),
            {
                "language": "es",
                "personality_key": "elderly_forgetful",
                "gender": "female",
                "voice": "echo",
                "vocal_style_key": "elderly_forgetful",
            },
        )

    def test_unknown_profile_values_use_safe_defaults(self) -> None:
        profile = build_patient_speech_profile("fr", "unknown", "other")

        self.assertEqual(profile.language, "en")
        self.assertIsNone(profile.gender)
        self.assertEqual(profile.personality_key, "unknown")
        self.assertEqual(profile.voice, "alloy")
        self.assertEqual(profile.vocal_style_key, "default")
