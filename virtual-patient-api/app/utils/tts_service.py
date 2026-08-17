"""Text-to-speech service backed by the Azure OpenAI v1 API."""

from pathlib import Path
import tempfile
from typing import Optional

from openai import OpenAI, OpenAIError

from app.core.azure_openai import create_openai_client
from app.core.config import settings


class TTSService:
    """Generate patient audio with the configured Azure OpenAI deployment."""

    PERSONALITY_VOICES = {
        "elderly_forgetful": {"male": "onyx", "female": "echo"},
        "know_it_all": {"male": "onyx", "female": "nova"},
        "rude_unfriendly": {"male": "onyx", "female": "alloy"},
        "friendly_polite": {"male": "onyx", "female": "nova"},
        "confused_inquisitive": {"male": "onyx", "female": "nova"},
        "skeptical_spiritual": {"male": "echo", "female": "shimmer"},
    }

    DEFAULT_VOICES = {
        "male": "alloy",
        "female": "shimmer",
    }

    def __init__(self, client: OpenAI | None = None):
        self.deployment_name = settings.azure_openai_tts_deployment_name
        self.client = client
        if (
            self.client is None
            and settings.azure_openai_api_key
            and settings.azure_openai_v1_base_url
        ):
            self.client = create_openai_client()

    @classmethod
    def get_voice_for_personality(
        cls,
        personality_namespace_key: Optional[str] = None,
        gender: Optional[str] = None,
    ) -> str:
        """Select a voice from the inherited personality/gender mapping."""
        gender_normalized = gender.lower() if gender else None

        if personality_namespace_key and gender_normalized:
            personality_voices = cls.PERSONALITY_VOICES.get(
                personality_namespace_key
            )
            if personality_voices:
                voice = personality_voices.get(gender_normalized)
                if voice:
                    print(
                        f"Selected voice '{voice}' for personality "
                        f"'{personality_namespace_key}' ({gender_normalized})"
                    )
                    return voice

        if gender_normalized:
            voice = cls.DEFAULT_VOICES.get(gender_normalized, "alloy")
            print(f"Using default voice '{voice}' for gender '{gender_normalized}'")
            return voice

        print("Using default voice 'alloy' (no personality/gender specified)")
        return "alloy"

    def generate_audio(
        self,
        text: str,
        voice: Optional[str] = None,
        personality_namespace_key: Optional[str] = None,
        gender: Optional[str] = None,
        output_file: Optional[str] = None,
    ) -> Optional[bytes]:
        """Generate MP3 audio and optionally persist it to ``output_file``."""
        if voice is None:
            voice = self.get_voice_for_personality(
                personality_namespace_key,
                gender,
            )

        if not self.client or not self.deployment_name:
            print("TTS Service: Azure TTS configuration is incomplete")
            return None

        if not text or not text.strip():
            print("TTS Service: Empty text provided")
            return None

        print(f"Generating TTS audio for text: '{text[:50]}...'")
        try:
            response = self.client.audio.speech.create(
                model=self.deployment_name,
                input=text,
                voice=voice,
                response_format="mp3",
            )
            audio_data = response.content
            if not audio_data:
                print("TTS Service: Azure returned an empty audio response")
                return None

            print(f"TTS audio generated successfully ({len(audio_data):,} bytes)")
            if output_file:
                Path(output_file).write_bytes(audio_data)
                print(f"Audio saved to: {output_file}")
            return audio_data
        except OpenAIError as error:
            print(f"TTS request failed: {error}")
            return None

    def generate_audio_to_file(
        self,
        text: str,
        voice: Optional[str] = None,
        personality_namespace_key: Optional[str] = None,
        gender: Optional[str] = None,
    ) -> Optional[str]:
        """Generate audio in a temporary MP3 file and return its path."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_file_path = temp_file.name
        temp_file.close()

        audio_data = self.generate_audio(
            text,
            voice=voice,
            personality_namespace_key=personality_namespace_key,
            gender=gender,
            output_file=temp_file_path,
        )

        if audio_data:
            return temp_file_path

        try:
            Path(temp_file_path).unlink(missing_ok=True)
        except OSError:
            pass
        return None
