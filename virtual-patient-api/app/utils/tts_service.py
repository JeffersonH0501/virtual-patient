"""Backward-compatible facade for the provider-neutral speech service."""

from pathlib import Path
import tempfile
from typing import Optional

from openai import OpenAI

from app.core.config import settings
from app.speech.azure_openai import AzureOpenAITextToSpeechProvider
from app.speech.contracts import SpeechError
from app.speech.service import SpeechService
from app.speech.voice_policy import (
    DEFAULT_VOICES,
    PERSONALITY_VOICES,
    select_patient_voice,
)


class TTSService:
    """Compatibility wrapper retained for existing application consumers."""

    PERSONALITY_VOICES = PERSONALITY_VOICES
    DEFAULT_VOICES = DEFAULT_VOICES

    def __init__(self, client: OpenAI | None = None):
        provider = AzureOpenAITextToSpeechProvider(
            client=client,
            configuration=settings,
        )
        self._speech_service = SpeechService(tts_provider=provider)

    @classmethod
    def get_voice_for_personality(
        cls,
        personality_namespace_key: Optional[str] = None,
        gender: Optional[str] = None,
    ) -> str:
        """Return the voice selected by the neutral patient voice policy."""
        return select_patient_voice(personality_namespace_key, gender)

    def generate_audio(
        self,
        text: str,
        voice: Optional[str] = None,
        personality_namespace_key: Optional[str] = None,
        gender: Optional[str] = None,
        output_file: Optional[str] = None,
    ) -> Optional[bytes]:
        """Generate MP3 audio and optionally write it to a file."""
        try:
            if voice:
                audio = self._speech_service.synthesize(text, voice)
            else:
                audio = self._speech_service.synthesize_patient_message(
                    text,
                    personality_namespace_key,
                    gender,
                )
        except SpeechError:
            return None

        if output_file:
            Path(output_file).write_bytes(audio.content)
        return audio.content

    def generate_audio_to_file(
        self,
        text: str,
        voice: Optional[str] = None,
        personality_namespace_key: Optional[str] = None,
        gender: Optional[str] = None,
    ) -> Optional[str]:
        """Generate audio in a temporary MP3 file and return its path."""
        temporary_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temporary_path = temporary_file.name
        temporary_file.close()
        audio = self.generate_audio(
            text,
            voice=voice,
            personality_namespace_key=personality_namespace_key,
            gender=gender,
            output_file=temporary_path,
        )
        if audio:
            return temporary_path
        Path(temporary_path).unlink(missing_ok=True)
        return None
