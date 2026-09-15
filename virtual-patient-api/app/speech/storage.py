"""Build reproducible patient-speech metadata without durable audio storage."""

from dataclasses import dataclass

from app.speech.service import create_patient_synthesis_request


@dataclass(frozen=True)
class PersistedPatientAudio:
    """Compatibility payload containing reproducible synthesis metadata."""

    audio_url: str | None
    synthesis_metadata: dict[str, object]


def persist_patient_audio(
    interview_id: int,
    text: str,
    personality_namespace_key: str | None,
    gender: str | None,
) -> PersistedPatientAudio:
    """Return synthesis metadata; audio is generated on demand by the API."""
    request = create_patient_synthesis_request(
        text,
        personality_namespace_key,
        gender,
    )
    style = request.vocal_style
    synthesis_metadata: dict[str, object] = {
        "voice": request.voice,
        "style_policy_version": style.policy_version if style else None,
        "vocal_style": (
            {
                "profile_key": style.profile_key,
                "speaking_rate": style.speaking_rate.value,
                "pause_frequency": style.pause_frequency.value,
                "energy": style.energy.value,
                "intonation_variation": style.intonation_variation.value,
                "hesitation_frequency": style.hesitation_frequency.value,
                "delivery_tone": style.delivery_tone.value,
            }
            if style
            else None
        ),
    }
    del interview_id
    return PersistedPatientAudio(None, synthesis_metadata)
