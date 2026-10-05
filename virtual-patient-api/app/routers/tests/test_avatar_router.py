"""Unit tests for Simli Avatar endpoints."""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.routers import avatar as avatar_router
from app.speech.simli_avatar_service import (
    SimliConfigurationError,
    SimliProviderError,
    SimliSessionConfig,
)


class AvatarEndpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.db = MagicMock()
        self.user = SimpleNamespace(id=42)

    @patch.object(avatar_router, "MedicalInterviewController")
    async def test_session_requires_interview_access(self, controller_type) -> None:
        controller_type.return_value.validate_interview_access.return_value = False

        with self.assertRaises(HTTPException) as context:
            await avatar_router.start_avatar_session(
                interview_id=10,
                request=avatar_router.StartAvatarSessionRequest(),
                db=self.db,
                current_user=self.user,
            )

        self.assertEqual(context.exception.status_code, 403)

    @patch.object(avatar_router, "SimliAvatarService")
    @patch.object(avatar_router, "MedicalInterviewController")
    async def test_session_returns_503_when_disabled(
        self,
        controller_type,
        service_type,
    ) -> None:
        controller_type.return_value.validate_interview_access.return_value = True
        self.db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            id=10,
            patient_gender="female",
        )
        service_type.return_value.is_enabled = False

        with self.assertRaises(HTTPException) as context:
            await avatar_router.start_avatar_session(
                interview_id=10,
                request=avatar_router.StartAvatarSessionRequest(),
                db=self.db,
                current_user=self.user,
            )

        self.assertEqual(context.exception.status_code, 503)

    @patch.object(avatar_router, "SimliAvatarService")
    @patch.object(avatar_router, "MedicalInterviewController")
    async def test_session_success(
        self,
        controller_type,
        service_type,
    ) -> None:
        controller_type.return_value.validate_interview_access.return_value = True
        self.db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            id=10,
            patient_gender="male",
        )
        service_type.return_value.is_enabled = True
        service_type.return_value.get_session_configuration.return_value = SimliSessionConfig(
            session_token="simli-session-token-abc",
            ice_servers=[{"urls": "stun:stun.l.google.com:19302"}],
            face_id="face-male-001",
            max_session_length=1800,
            max_idle_time=300,
        )

        response = await avatar_router.start_avatar_session(
            interview_id=10,
            request=avatar_router.StartAvatarSessionRequest(),
            db=self.db,
            current_user=self.user,
        )

        self.assertEqual(response.session_token, "simli-session-token-abc")
        self.assertEqual(response.face_id, "face-male-001")
        self.assertEqual(response.max_session_length, 1800)
        self.assertEqual(response.max_idle_time, 300)
        self.assertTrue(response.enabled)

    @patch.object(avatar_router, "SimliAvatarService")
    @patch.object(avatar_router, "MedicalInterviewController")
    async def test_status_endpoint(
        self,
        controller_type,
        service_type,
    ) -> None:
        controller_type.return_value.validate_interview_access.return_value = True
        self.db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            id=10,
        )
        service_type.return_value.is_enabled = True

        status_response = await avatar_router.get_avatar_status(
            interview_id=10,
            db=self.db,
            current_user=self.user,
        )

        self.assertTrue(status_response.enabled)
        self.assertEqual(status_response.provider, "simli")

    @patch.object(avatar_router, "MedicalInterviewController")
    async def test_telemetry_endpoint(self, controller_type) -> None:
        controller_type.return_value.validate_interview_access.return_value = True
        self.db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            id=10,
        )

        telemetry_req = avatar_router.AvatarTelemetryRequest(
            ttff_ms=210.5,
            rtt_ms=45.2,
            jitter_ms=2.1,
            packet_loss_pct=0.0,
            frame_rate=30.0,
            resolution="1280x720",
            active_duration_seconds=12.4,
        )

        result = await avatar_router.record_avatar_telemetry(
            interview_id=10,
            telemetry=telemetry_req,
            db=self.db,
            current_user=self.user,
        )

        self.assertEqual(result, {"status": "recorded"})


if __name__ == "__main__":
    unittest.main()

