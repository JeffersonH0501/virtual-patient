"""Application speech orchestration without provider-specific dependencies."""

from app.speech.contracts import (
    SpeechSynthesisRequest,
    SpeechToTextProvider,
    SpeechTranscriptionRequest,
    SynthesizedAudio,
    TextToSpeechProvider,
    TranscriptionResult,
)
from app.speech.factory import create_stt_provider, create_tts_provider
from app.speech.voice_policy import select_patient_voice
from app.speech.vocal_style_policy import select_patient_vocal_style


def create_patient_synthesis_request(
    text: str,
    personality_namespace_key: str | None = None,
    gender: str | None = None,
) -> SpeechSynthesisRequest:
    """Build one provider-neutral patient speech request."""
    return SpeechSynthesisRequest(
        text=text,
        voice=select_patient_voice(personality_namespace_key, gender),
        vocal_style=select_patient_vocal_style(personality_namespace_key),
    )


class SpeechService:
    """Coordinate speech requests through replaceable providers."""

    def __init__(
        self,
        tts_provider: TextToSpeechProvider | None = None,
        stt_provider: SpeechToTextProvider | None = None,
    ):
        self._tts_provider = tts_provider
        self._stt_provider = stt_provider

    def synthesize_patient_message(
        self,
        text: str,
        personality_namespace_key: str | None = None,
        gender: str | None = None,
    ) -> SynthesizedAudio:
        """Generate patient speech using neutral voice-selection policy."""
        provider = self._tts_provider or create_tts_provider()
        return provider.synthesize(
            create_patient_synthesis_request(
                text,
                personality_namespace_key,
                gender,
            )
        )

    def synthesize(self, text: str, voice: str) -> SynthesizedAudio:
        """Generate speech with an explicitly selected neutral voice name."""
        provider = self._tts_provider or create_tts_provider()
        return provider.synthesize(SpeechSynthesisRequest(text=text, voice=voice))

    def transcribe(
        self,
        request: SpeechTranscriptionRequest,
    ) -> TranscriptionResult:
        """Transcribe an audio request with the configured server provider."""
        provider = self._stt_provider or create_stt_provider()
        return provider.transcribe(request)
