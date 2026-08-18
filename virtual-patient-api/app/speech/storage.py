"""Optional storage for synthesized patient audio."""

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings
from app.speech.contracts import SynthesizedAudio
from app.speech.service import SpeechService, create_patient_synthesis_request
from app.utils.gcs_service import GCSService


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PersistedPatientAudio:
    """Optional stored audio plus a reproducible synthesis snapshot."""

    audio_url: str | None
    synthesis_metadata: dict[str, object]


class AudioStorage(Protocol):
    """Contract for durable synthesized-audio storage."""

    def store(
        self,
        audio: SynthesizedAudio,
        destination_path: str,
    ) -> str | None:
        """Store audio and return a retrievable URL."""


class GoogleCloudAudioStorage:
    """Store synthesized audio in the existing optional GCS integration."""

    def __init__(self, service: GCSService | None = None):
        self.service = service or GCSService()

    def store(
        self,
        audio: SynthesizedAudio,
        destination_path: str,
    ) -> str | None:
        """Upload audio bytes to Google Cloud Storage."""
        return self.service.upload_audio_bytes(
            audio_data=audio.content,
            destination_path=destination_path,
            content_type=audio.content_type,
            make_public=True,
        )


def create_audio_storage() -> AudioStorage | None:
    """Create durable audio storage only when it is configured."""
    if not settings.gcs_bucket_name:
        return None
    storage = GoogleCloudAudioStorage()
    if not storage.service.bucket:
        return None
    return storage


def persist_patient_audio(
    interview_id: int,
    text: str,
    personality_namespace_key: str | None,
    gender: str | None,
) -> PersistedPatientAudio:
    """Generate and persist patient audio when optional storage is available."""
    started_at = time.perf_counter()
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
    try:
        storage = create_audio_storage()
        if not storage:
            if settings.patient_response_timing_logging:
                logger.info(
                    "patient_response_timing interview_id=%s stage=patient_audio_persistence "
                    "configured=false total_ms=%.1f",
                    interview_id,
                    (time.perf_counter() - started_at) * 1000,
                )
            return PersistedPatientAudio(None, synthesis_metadata)
        synthesis_started_at = time.perf_counter()
        audio = SpeechService().synthesize_patient_message(
            text, personality_namespace_key, gender
        )
        synthesis_elapsed = time.perf_counter() - synthesis_started_at
        synthesis_metadata.update(
            {
                "provider": audio.provider,
                "model": audio.model,
                "instructions": audio.synthesis_instructions,
            }
        )
        style_version = audio.style_policy_version or "unversioned"
        destination_path = (
            f"audio/interview_{interview_id}/"
            f"style_v{style_version}/message_{uuid.uuid4().hex[:16]}.mp3"
        )
        storage_started_at = time.perf_counter()
        audio_url = storage.store(audio, destination_path)
        if settings.patient_response_timing_logging:
            logger.info(
                "patient_response_timing interview_id=%s stage=patient_audio_persistence "
                "configured=true tts_ms=%.1f storage_ms=%.1f total_ms=%.1f",
                interview_id,
                synthesis_elapsed * 1000,
                (time.perf_counter() - storage_started_at) * 1000,
                (time.perf_counter() - started_at) * 1000,
            )
        return PersistedPatientAudio(
            audio_url,
            synthesis_metadata,
        )
    except Exception as error:
        logger.warning(
            "Optional patient audio persistence failed for interview %s: %s",
            interview_id,
            error,
        )
        return PersistedPatientAudio(None, synthesis_metadata)
