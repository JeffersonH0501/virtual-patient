"""Unit tests for Azure AI Speech Avatar SSML and Pilot Service."""

import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("dotenv", MagicMock())
sys.modules.setdefault("requests", MagicMock())
sys.modules.setdefault("openai", MagicMock())
sys.modules.setdefault("langchain_openai", MagicMock())
sys.modules.setdefault("langchain", MagicMock())
sys.modules.setdefault("langgraph", MagicMock())
sys.modules.setdefault("sqlalchemy", MagicMock())
sys.modules.setdefault("fastapi", MagicMock())

from app.speech.avatar_ssml import (
    render_avatar_ssml,
    select_avatar_character,
    select_avatar_voice,
)
from app.speech.azure_avatar_pilot_service import AzureAvatarPilotService
from app.speech.contracts import (
    DeliveryTone,
    HesitationFrequency,
    IntonationVariation,
    PauseFrequency,
    SpeakingRate,
    VocalEnergy,
    VocalStyle,
)


class AvatarSSMLTests(unittest.TestCase):
    def test_voice_selection_by_gender(self):
        self.assertEqual(select_avatar_voice("female"), "es-CO-SalomeNeural")
        self.assertEqual(select_avatar_voice("mujer"), "es-CO-SalomeNeural")
        self.assertEqual(select_avatar_voice("male"), "es-CO-GonzaloNeural")
        self.assertEqual(select_avatar_voice("hombre"), "es-CO-GonzaloNeural")
        self.assertEqual(select_avatar_voice(None), "es-CO-GonzaloNeural")

    def test_character_selection_by_gender(self):
        self.assertEqual(select_avatar_character("female"), "lisa")
        self.assertEqual(select_avatar_character("male"), "max")

    def test_render_avatar_ssml_basic(self):
        ssml = render_avatar_ssml("Tengo dolor de cabeza.", gender="female")
        self.assertIn('<speak version="1.0"', ssml)
        self.assertIn('xml:lang="es-CO"', ssml)
        self.assertIn('voice name="es-CO-SalomeNeural"', ssml)
        self.assertIn("Tengo dolor de cabeza.", ssml)

    def test_render_avatar_ssml_escapes_xml(self):
        ssml = render_avatar_ssml("Dolor & mareo <urgente>", gender="male")
        self.assertIn("Dolor &amp; mareo &lt;urgente&gt;", ssml)
        self.assertNotIn("<urgente>", ssml)

    def test_render_avatar_ssml_applies_vocal_style(self):
        style = VocalStyle(
            profile_key="test_brisk_reassuring",
            policy_version="2",
            speaking_rate=SpeakingRate.BRISK,
            pause_frequency=PauseFrequency.NATURAL,
            energy=VocalEnergy.HIGH,
            intonation_variation=IntonationVariation.EXPRESSIVE,
            hesitation_frequency=HesitationFrequency.NONE,
            delivery_tone=DeliveryTone.REASSURING,
        )
        ssml = render_avatar_ssml("Todo estará bien.", vocal_style=style, gender="female")
        self.assertIn('rate="+10%"', ssml)
        self.assertIn('volume="loud"', ssml)
        self.assertIn('mstts:express-as style="friendly"', ssml)


class AzureAvatarPilotServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("app.speech.azure_avatar_pilot_service.requests.get")
    @patch("app.speech.azure_avatar_pilot_service.requests.post")
    @patch("app.speech.azure_avatar_pilot_service.settings")
    def test_get_client_configuration_returns_temporary_credentials(
        self,
        mock_settings,
        mock_post,
        mock_get,
    ):
        mock_settings.avatar_pilot_enabled = True
        mock_settings.azure_speech_key = "test-key"
        mock_settings.azure_speech_region = "eastus2"
        mock_settings.avatar_pilot_telemetry_dir = self.temp_dir
        mock_settings.azure_speech_avatar_character_female = "lisa"
        mock_settings.azure_speech_avatar_character_male = "jeff"
        mock_post.return_value.text = "speech-token"
        mock_get.return_value.json.return_value = {
            "urls": ["turn:relay.example.test:3478"],
            "username": "relay-user",
            "password": "relay-password",
        }

        service = AzureAvatarPilotService()
        result = service.get_client_configuration(gender="female")

        self.assertEqual(result["speech_token"], "speech-token")
        self.assertEqual(result["ice_servers"][0]["username"], "relay-user")
        self.assertEqual(result["character"], "lisa")
        self.assertEqual(result["region"], "eastus2")
        mock_post.return_value.raise_for_status.assert_called_once()
        mock_get.return_value.raise_for_status.assert_called_once()

    @patch("app.speech.azure_avatar_pilot_service.settings")
    def test_get_client_configuration_requires_enabled_config(self, mock_settings):
        mock_settings.avatar_pilot_enabled = False
        mock_settings.azure_speech_key = "test-key"
        mock_settings.azure_speech_region = "eastus2"
        mock_settings.avatar_pilot_telemetry_dir = self.temp_dir

        service = AzureAvatarPilotService()

        with self.assertRaisesRegex(RuntimeError, "disabled"):
            service.get_client_configuration()

    @patch("app.speech.azure_avatar_pilot_service.settings")
    def test_save_and_summarize_telemetry(self, mock_settings):
        mock_settings.avatar_pilot_enabled = False
        mock_settings.azure_speech_key = None
        mock_settings.azure_speech_region = "eastus2"
        mock_settings.avatar_pilot_telemetry_dir = self.temp_dir
        mock_settings.azure_speech_avatar_idle_optimization = True

        service = AzureAvatarPilotService()

        # Save 2 simulated turns
        service.save_turn_telemetry(
            interview_id=101,
            turn_data={
                "ttff_ms": 1100.0,
                "rtt_ms": 180.0,
                "jitter_ms": 12.0,
                "packet_loss_pct": 0.2,
                "active_duration_seconds": 6.0,
            },
        )
        service.save_turn_telemetry(
            interview_id=101,
            turn_data={
                "ttff_ms": 1250.0,
                "rtt_ms": 195.0,
                "jitter_ms": 14.0,
                "packet_loss_pct": 0.1,
                "active_duration_seconds": 8.0,
            },
        )

        summary = service.get_telemetry_summary(interview_id=101)

        self.assertEqual(summary["total_turns"], 2)
        self.assertAlmostEqual(summary["latency_metrics"]["mean_ttff_ms"], 1175.0, delta=1.0)
        self.assertAlmostEqual(summary["latency_metrics"]["mean_rtt_ms"], 187.5, delta=1.0)
        self.assertEqual(summary["cost_metrics"]["total_active_streaming_seconds"], 14.0)
        self.assertTrue(summary["protocol_compliance"]["step_1_webrtc_latency"]["passed"])
        self.assertTrue(summary["protocol_compliance"]["step_2_ttff"]["passed"])


if __name__ == "__main__":
    unittest.main()
