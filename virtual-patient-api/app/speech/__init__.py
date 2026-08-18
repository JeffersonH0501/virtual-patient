"""Provider-neutral speech services."""

from app.speech.contracts import (
    SpeechSynthesisRequest,
    SpeechTranscriptionRequest,
    SynthesizedAudio,
    TranscriptionResult,
    VocalStyle,
)
from app.speech.service import SpeechService

__all__ = [
    "SpeechService",
    "SpeechSynthesisRequest",
    "SpeechTranscriptionRequest",
    "SynthesizedAudio",
    "TranscriptionResult",
    "VocalStyle",
]
