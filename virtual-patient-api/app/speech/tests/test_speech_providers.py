"""Unit tests for provider-neutral speech behavior."""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.core.config import Settings
from app.speech.azure_openai import (
    AzureOpenAISpeechToTextProvider,
    AzureOpenAITextToSpeechProvider,
)
from app.speech.contracts import (
    DeliveryTone,
    HesitationFrequency,
    IntonationVariation,
    PauseFrequency,
    SpeechSynthesisRequest,
    SpeechTranscriptionRequest,
    SpeakingRate,
    VocalEnergy,
    VocalStyle,
)
from app.speech.factory import create_stt_provider, create_tts_provider
from app.speech.service import SpeechService
from app.speech.storage import persist_patient_audio
from app.speech.voice_policy import select_patient_voice
from app.speech.vocal_style_policy import (
    VOCAL_STYLE_POLICY_VERSION,
    select_patient_vocal_style,
)


class SpeechProviderTests(unittest.TestCase):
    def test_azure_tts_uses_configured_deployment(self) -> None:
        client = MagicMock()
        client.audio.speech.create.return_value = SimpleNamespace(content=b"audio")
        provider = AzureOpenAITextToSpeechProvider(
            client=client,
            deployment_name="tts-deployment",
        )

        result = provider.synthesize(
            SpeechSynthesisRequest(text="Hello", voice="alloy")
        )

        self.assertEqual(result.content, b"audio")
        self.assertEqual(result.provider, "azure_openai")
        client.audio.speech.create.assert_called_once_with(
            model="tts-deployment",
            input="Hello",
            voice="alloy",
            response_format="mp3",
        )

    def test_azure_stt_uses_configured_deployment_and_language(self) -> None:
        client = MagicMock()
        client.audio.transcriptions.create.return_value = SimpleNamespace(text="Hola")
        provider = AzureOpenAISpeechToTextProvider(
            client=client,
            deployment_name="stt-deployment",
        )

        result = provider.transcribe(
            SpeechTranscriptionRequest(
                content=b"audio",
                filename="sample.webm",
                content_type="audio/webm",
                language="es",
            )
        )

        self.assertEqual(result.text, "Hola")
        client.audio.transcriptions.create.assert_called_once_with(
            model="stt-deployment",
            file=("sample.webm", b"audio", "audio/webm"),
            language="es",
        )

    def test_patient_voice_selection_is_provider_independent(self) -> None:
        provider = MagicMock()
        provider.synthesize.return_value = SimpleNamespace(content=b"audio")
        service = SpeechService(tts_provider=provider)

        service.synthesize_patient_message("Hello", "rude_unfriendly", "female")

        request = provider.synthesize.call_args.args[0]
        self.assertEqual(request.voice, "alloy")
        self.assertEqual(request.vocal_style.profile_key, "rude_unfriendly")
        self.assertEqual(
            request.vocal_style.policy_version,
            VOCAL_STYLE_POLICY_VERSION,
        )
        self.assertEqual(select_patient_voice(None, "female"), "shimmer")

    def test_patient_vocal_style_is_provider_independent(self) -> None:
        style = select_patient_vocal_style("elderly_forgetful")

        self.assertEqual(style.speaking_rate, SpeakingRate.MODERATELY_SLOW)
        self.assertEqual(style.pause_frequency, PauseFrequency.OCCASIONAL)
        self.assertEqual(style.energy, VocalEnergy.LOW)
        self.assertEqual(style.intonation_variation, IntonationVariation.RESTRAINED)
        self.assertEqual(style.hesitation_frequency, HesitationFrequency.LIGHT)
        self.assertEqual(style.delivery_tone, DeliveryTone.REFLECTIVE)

    def test_azure_tts_translates_vocal_style_to_instructions(self) -> None:
        client = MagicMock()
        client.audio.speech.create.return_value = SimpleNamespace(content=b"audio")
        provider = AzureOpenAITextToSpeechProvider(
            client=client,
            deployment_name="tts-deployment",
        )
        style = VocalStyle(
            profile_key="test",
            policy_version="test-version",
            speaking_rate=SpeakingRate.MODERATELY_SLOW,
            pause_frequency=PauseFrequency.OCCASIONAL,
            energy=VocalEnergy.LOW,
            intonation_variation=IntonationVariation.RESTRAINED,
            hesitation_frequency=HesitationFrequency.LIGHT,
            delivery_tone=DeliveryTone.REFLECTIVE,
        )

        result = provider.synthesize(
            SpeechSynthesisRequest(
                text="I need a moment.",
                voice="echo",
                vocal_style=style,
            )
        )

        arguments = client.audio.speech.create.call_args.kwargs
        self.assertEqual(arguments["input"], "I need a moment.")
        self.assertIn("moderately slow pace", arguments["instructions"])
        self.assertIn("without adding filler words", arguments["instructions"])
        self.assertIn("Preserve the supplied text exactly", arguments["instructions"])
        self.assertEqual(result.style_policy_version, "test-version")
        self.assertEqual(result.synthesis_instructions, arguments["instructions"])

    def test_synthesis_metadata_is_recorded_without_durable_storage(
        self,
    ) -> None:
        persisted = persist_patient_audio(
            interview_id=11,
            text="I need a moment.",
            personality_namespace_key="elderly_forgetful",
            gender="female",
        )

        self.assertIsNone(persisted.audio_url)
        self.assertEqual(persisted.synthesis_metadata["voice"], "echo")
        self.assertEqual(
            persisted.synthesis_metadata["style_policy_version"],
            VOCAL_STYLE_POLICY_VERSION,
        )
        self.assertEqual(
            persisted.synthesis_metadata["vocal_style"]["speaking_rate"],
            "moderately_slow",
        )

    def test_factories_always_create_azure_openai_providers(self) -> None:
        configuration = Settings()

        self.assertIsInstance(
            create_tts_provider(configuration),
            AzureOpenAITextToSpeechProvider,
        )
        self.assertIsInstance(
            create_stt_provider(configuration),
            AzureOpenAISpeechToTextProvider,
        )
