"""Unit tests for provider-neutral speech endpoints."""

from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.models.medical_interview.enums import SenderType
from app.routers import speech as speech_router
from app.speech.contracts import SynthesizedAudio, TranscriptionResult
from app.speech.vocal_style_policy import VOCAL_STYLE_POLICY_VERSION


class SpeechEndpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.db = MagicMock()
        self.user = SimpleNamespace(id=7)

    @patch.object(speech_router, "MedicalInterviewController")
    async def test_patient_speech_requires_interview_access(self, controller_type) -> None:
        controller_type.return_value.validate_interview_access.return_value = False

        with self.assertRaises(HTTPException) as context:
            await speech_router.synthesize_patient_message(
                interview_id=11,
                message_id=12,
                db=self.db,
                current_user=self.user,
            )

        self.assertEqual(context.exception.status_code, 403)

    @patch.object(speech_router, "MessageController")
    @patch.object(speech_router, "MedicalInterviewController")
    async def test_patient_speech_rejects_student_messages(
        self,
        controller_type,
        message_controller_type,
    ) -> None:
        controller_type.return_value.validate_interview_access.return_value = True
        message_controller_type.return_value.get_message.return_value = SimpleNamespace(
            interview_id=11,
            sender_type=SenderType.USER.value,
            content="Hello",
        )

        with self.assertRaises(HTTPException) as context:
            await speech_router.synthesize_patient_message(
                interview_id=11,
                message_id=12,
                db=self.db,
                current_user=self.user,
            )

        self.assertEqual(context.exception.status_code, 400)

    @patch.object(speech_router, "SpeechService")
    @patch.object(speech_router, "MessageController")
    @patch.object(speech_router, "MedicalInterviewController")
    async def test_patient_speech_returns_non_empty_audio(
        self,
        controller_type,
        message_controller_type,
        speech_service_type,
    ) -> None:
        controller_type.return_value.validate_interview_access.return_value = True
        message_controller_type.return_value.get_message.return_value = SimpleNamespace(
            interview_id=11,
            sender_type=SenderType.PATIENT.value,
            content="I feel tired.",
        )
        self.db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            patient_gender="female",
            personality=SimpleNamespace(namespace_key="reserved"),
        )
        speech_service_type.return_value.synthesize_patient_message.return_value = (
            SynthesizedAudio(
                content=b"audio-bytes",
                content_type="audio/mpeg",
                provider="mock",
                model="mock-tts",
            )
        )

        response = await speech_router.synthesize_patient_message(
            interview_id=11,
            message_id=12,
            db=self.db,
            current_user=self.user,
        )

        self.assertEqual(response.body, b"audio-bytes")
        self.assertEqual(response.media_type, "audio/mpeg")
        speech_service_type.return_value.synthesize_patient_message.assert_called_once_with(
            "I feel tired.",
            "reserved",
            "female",
        )

    @patch.object(speech_router, "MessageController")
    @patch.object(speech_router, "MedicalInterviewController")
    async def test_patient_speech_reuses_current_version_stored_audio(
        self,
        controller_type,
        message_controller_type,
    ) -> None:
        controller_type.return_value.validate_interview_access.return_value = True
        message_controller_type.return_value.get_message.return_value = SimpleNamespace(
            interview_id=11,
            sender_type=SenderType.PATIENT.value,
            content="I feel tired.",
            audio_url="https://storage.example/patient.mp3",
            message_metadata={
                "speech_synthesis": {
                    "style_policy_version": VOCAL_STYLE_POLICY_VERSION,
                }
            },
        )
        self.db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            patient_gender="female",
            personality=SimpleNamespace(namespace_key="friendly_polite"),
        )

        response = await speech_router.synthesize_patient_message(
            interview_id=11,
            message_id=12,
            db=self.db,
            current_user=self.user,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "https://storage.example/patient.mp3")

    @patch.object(speech_router, "SpeechService")
    async def test_transcription_forwards_audio_and_language(
        self,
        speech_service_type,
    ) -> None:
        speech_service_type.return_value.transcribe.return_value = TranscriptionResult(
            text="Tengo dolor.",
            language="es",
            provider="mock",
            model="mock-stt",
        )
        upload = UploadFile(
            file=BytesIO(b"audio-bytes"),
            filename="sample.webm",
            headers=Headers({"content-type": "audio/webm"}),
        )

        result = await speech_router.transcribe_audio(
            audio=upload,
            language="es",
            current_user=self.user,
        )

        self.assertEqual(result.text, "Tengo dolor.")
        request = speech_service_type.return_value.transcribe.call_args.args[0]
        self.assertEqual(request.content, b"audio-bytes")
        self.assertEqual(request.language, "es")
        self.assertEqual(request.content_type, "audio/webm")
