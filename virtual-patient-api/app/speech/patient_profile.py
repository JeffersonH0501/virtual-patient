"""Shared patient speech profile for synthesis and avatar rendering."""

from dataclasses import dataclass

from app.speech.contracts import VocalStyle
from app.speech.voice_policy import select_patient_voice
from app.speech.vocal_style_policy import select_patient_vocal_style


@dataclass(frozen=True)
class PatientSpeechProfile:
    language: str
    personality_key: str
    gender: str | None
    voice: str
    vocal_style: VocalStyle

    @property
    def vocal_style_key(self) -> str:
        return self.vocal_style.profile_key

    def as_metadata(self) -> dict[str, str | None]:
        return {
            "language": self.language,
            "personality_key": self.personality_key,
            "gender": self.gender,
            "voice": self.voice,
            "vocal_style_key": self.vocal_style_key,
        }


def build_patient_speech_profile(
    language: str | None,
    personality_namespace_key: str | None,
    gender: str | None,
) -> PatientSpeechProfile:
    """Resolve the stable identity and delivery profile used for one patient."""
    requested_language = (language or "en").strip().lower()
    normalized_language = {
        "english": "en",
        "spanish": "es",
    }.get(requested_language, requested_language)
    if normalized_language not in {"en", "es"}:
        normalized_language = "en"

    normalized_gender = gender.strip().lower() if gender else None
    if normalized_gender not in {"male", "female"}:
        normalized_gender = None

    personality_key = personality_namespace_key or "default"
    style = select_patient_vocal_style(personality_namespace_key)
    return PatientSpeechProfile(
        language=normalized_language,
        personality_key=personality_key,
        gender=normalized_gender,
        voice=select_patient_voice(personality_namespace_key, normalized_gender),
        vocal_style=style,
    )
