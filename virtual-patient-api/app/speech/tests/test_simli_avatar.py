"""Unit tests for SimliAvatarService."""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from app.core.config import Settings
from app.speech.simli_avatar_service import (
    SimliAvatarService,
    SimliConfigurationError,
    SimliProviderError,
)


class SimliAvatarServiceTests(unittest.TestCase):
    def setUp(self):
        self.mock_requester = MagicMock()

    def test_is_enabled_returns_true_when_configured(self):
        settings = Settings(
            simli_avatar_enabled=True,
            simli_api_key="simli-key-123",
        )
        service = SimliAvatarService(configuration=settings)
        self.assertTrue(service.is_enabled)

    def test_is_enabled_returns_false_when_key_missing(self):
        settings = Settings(
            simli_avatar_enabled=True,
            simli_api_key="",
        )
        service = SimliAvatarService(configuration=settings)
        self.assertFalse(service.is_enabled)

    def test_is_enabled_returns_false_when_disabled(self):
        settings = Settings(
            simli_avatar_enabled=False,
            simli_api_key="simli-key-123",
        )
        service = SimliAvatarService(configuration=settings)
        self.assertFalse(service.is_enabled)

    def test_resolve_face_id_selects_gender_specific_face(self):
        settings = Settings(
            simli_default_face_id_male="face-male-001",
            simli_default_face_id_female="face-female-002",
        )
        service = SimliAvatarService(configuration=settings)

        self.assertEqual(service.resolve_face_id("female"), "face-female-002")
        self.assertEqual(service.resolve_face_id("mujer"), "face-female-002")
        self.assertEqual(service.resolve_face_id("male"), "face-male-001")
        self.assertEqual(service.resolve_face_id("hombre"), "face-male-001")

    def test_resolve_face_id_uses_override(self):
        settings = Settings(
            simli_default_face_id_male="face-male-001",
            simli_default_face_id_female="face-female-002",
        )
        service = SimliAvatarService(configuration=settings)

        self.assertEqual(
            service.resolve_face_id("female", character_override="custom-face"),
            "custom-face",
        )

    def test_get_session_configuration_raises_when_disabled(self):
        settings = Settings(
            simli_avatar_enabled=False,
            simli_api_key="key",
        )
        service = SimliAvatarService(configuration=settings)
        with self.assertRaises(SimliConfigurationError):
            service.get_session_configuration()

    def test_get_session_configuration_raises_when_key_missing(self):
        settings = Settings(
            simli_avatar_enabled=True,
            simli_api_key="",
        )
        service = SimliAvatarService(configuration=settings)
        with self.assertRaises(SimliConfigurationError):
            service.get_session_configuration()

    def test_get_session_configuration_success(self):
        settings = Settings(
            simli_avatar_enabled=True,
            simli_api_key="test-api-key",
            simli_default_face_id_male="face-male-123",
            simli_api_url="https://api.simli.ai",
            simli_max_session_length=1200,
            simli_max_idle_time=240,
        )

        mock_token_resp = MagicMock()
        mock_token_resp.ok = True
        mock_token_resp.json.return_value = {"session_token": "token-xyz-123"}

        mock_ice_resp = MagicMock()
        mock_ice_resp.ok = True
        mock_ice_resp.json.return_value = [{"urls": ["stun:stun.l.google.com:19302"]}]

        self.mock_requester.post.return_value = mock_token_resp
        self.mock_requester.get.return_value = mock_ice_resp

        service = SimliAvatarService(
            configuration=settings,
            session_requester=self.mock_requester,
        )

        config = service.get_session_configuration(gender="male")

        self.assertEqual(config.session_token, "token-xyz-123")
        self.assertEqual(config.face_id, "face-male-123")
        self.assertEqual(config.max_session_length, 1200)
        self.assertEqual(config.max_idle_time, 240)
        self.assertEqual(len(config.ice_servers), 1)

        self.mock_requester.post.assert_called_once_with(
            "https://api.simli.ai/compose/token",
            json={
                "faceId": "face-male-123",
                "handleSilence": True,
                "maxSessionLength": 1200,
                "maxIdleTime": 240,
                "model": "fasttalk",
            },
            headers={
                "Content-Type": "application/json",
                "x-simli-api-key": "test-api-key",
            },
            timeout=10,
        )

    def test_get_session_configuration_handles_provider_error(self):
        settings = Settings(
            simli_avatar_enabled=True,
            simli_api_key="test-api-key",
        )

        mock_token_resp = MagicMock()
        mock_token_resp.ok = False
        mock_token_resp.status_code = 401
        mock_token_resp.text = "Unauthorized"

        self.mock_requester.post.return_value = mock_token_resp

        service = SimliAvatarService(
            configuration=settings,
            session_requester=self.mock_requester,
        )

        with self.assertRaises(SimliProviderError):
            service.get_session_configuration()


if __name__ == "__main__":
    unittest.main()

