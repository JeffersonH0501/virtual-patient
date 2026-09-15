import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

if "fastapi" not in sys.modules:
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = ""):
            self.status_code = status_code
            self.detail = detail

    class MockAPIRouter:
        def __init__(self, *args, **kwargs):
            pass
        def post(self, *args, **kwargs):
            return lambda f: f
        def delete(self, *args, **kwargs):
            return lambda f: f
        def get(self, *args, **kwargs):
            return lambda f: f

    fastapi_mock = MagicMock()
    fastapi_mock.HTTPException = HTTPException
    fastapi_mock.APIRouter = MockAPIRouter
    fastapi_mock.Depends = lambda x: x
    fastapi_mock.status = SimpleNamespace(
        HTTP_403_FORBIDDEN=403,
        HTTP_404_NOT_FOUND=404,
        HTTP_502_BAD_GATEWAY=502,
    )
    sys.modules["fastapi"] = fastapi_mock

if "pydantic" not in sys.modules:
    class MockBaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        def model_dump(self):
            return self.__dict__
        @classmethod
        def model_rebuild(cls, **kwargs):
            pass

    pydantic_mock = MagicMock()
    pydantic_mock.BaseModel = MockBaseModel
    pydantic_mock.Field = lambda *args, **kwargs: kwargs.get("default_factory", lambda: [])() if "default_factory" in kwargs else kwargs.get("default", None)
    sys.modules["pydantic"] = pydantic_mock

sys.modules.setdefault("dotenv", MagicMock())
sys.modules.setdefault("requests", MagicMock())
sys.modules["sqlalchemy"] = MagicMock()
sys.modules["sqlalchemy.orm"] = MagicMock()
sys.modules.setdefault("openai", MagicMock())
sys.modules.setdefault("langchain_openai", MagicMock())
sys.modules.setdefault("langchain", MagicMock())
sys.modules.setdefault("langgraph", MagicMock())
sys.modules["app.controllers.medical_interview_controller"] = MagicMock()
sys.modules["app.models.medical_interview.medical_interview"] = MagicMock()
sys.modules["app.models.user"] = MagicMock()
sys.modules["app.core.auth"] = MagicMock()
sys.modules["app.core.database"] = MagicMock()

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "avatar_pilot",
    Path(__file__).resolve().parents[2] / "routers" / "avatar_pilot.py",
)
avatar_router = importlib.util.module_from_spec(spec)
sys.modules["app.routers.avatar_pilot"] = avatar_router
spec.loader.exec_module(avatar_router)


class AvatarPilotRouterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = MagicMock()
        self.user = SimpleNamespace(id=99)

    @patch.object(avatar_router, "MedicalInterviewController")
    async def test_session_requires_interview_access(self, mock_controller):
        mock_controller.return_value.validate_interview_access.return_value = False

        with self.assertRaises(HTTPException) as ctx:
            await avatar_router.start_avatar_session(
                interview_id=12,
                request=avatar_router.StartSessionRequest(sdp_offer="mockOffer"),
                db=self.db,
                current_user=self.user,
            )

        self.assertEqual(ctx.exception.status_code, 403)

    @patch.object(avatar_router, "AzureAvatarPilotService")
    @patch.object(avatar_router, "MedicalInterviewController")
    async def test_session_returns_sdp_answer(self, mock_controller, mock_service):
        mock_controller.return_value.validate_interview_access.return_value = True
        self.db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            id=12,
            patient_gender="female",
            personality=None,
        )

        mock_service.return_value.get_client_configuration.return_value = {
            "speech_token": "temporary-token",
            "ice_servers": [{"urls": "turn:test.org", "username": "user", "credential": "secret"}],
            "character": "lisa",
            "voice": "es-CO-SalomeNeural",
            "style": "casual-sitting",
            "region": "eastus",
        }

        response = await avatar_router.start_avatar_session(
            interview_id=12,
            request=avatar_router.StartSessionRequest(),
            db=self.db,
            current_user=self.user,
        )

        self.assertEqual(response.speech_token, "temporary-token")
        self.assertEqual(response.character, "lisa")

    @patch.object(avatar_router, "AzureAvatarPilotService")
    @patch.object(avatar_router, "MedicalInterviewController")
    async def test_telemetry_recording(self, mock_controller, mock_service):
        mock_controller.return_value.validate_interview_access.return_value = True
        self.db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            id=12,
            patient_gender="female",
            personality=None,
        )

        telemetry_payload = avatar_router.TurnTelemetryRequest(
            ttff_ms=950.0,
            rtt_ms=160.0,
            jitter_ms=10.0,
            packet_loss_pct=0.0,
            active_duration_seconds=5.5,
        )

        response = await avatar_router.record_telemetry_turn(
            interview_id=12,
            telemetry=telemetry_payload,
            db=self.db,
            current_user=self.user,
        )

        self.assertEqual(response["status"], "recorded")
        mock_service.return_value.save_turn_telemetry.assert_called_once()


if __name__ == "__main__":
    unittest.main()
