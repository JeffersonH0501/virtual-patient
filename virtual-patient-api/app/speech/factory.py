"""Azure OpenAI speech provider factories."""

from app.core.config import Settings, settings
from app.speech.azure_openai import (
    AzureOpenAISpeechToTextProvider,
    AzureOpenAITextToSpeechProvider,
)
from app.speech.contracts import (
    SpeechToTextProvider,
    TextToSpeechProvider,
)


def create_tts_provider(
    configuration: Settings = settings,
) -> TextToSpeechProvider:
    """Create the project's fixed Azure OpenAI text-to-speech provider."""
    return AzureOpenAITextToSpeechProvider(configuration=configuration)


def create_stt_provider(
    configuration: Settings = settings,
) -> SpeechToTextProvider:
    """Create the project's fixed Azure OpenAI speech-to-text provider."""
    return AzureOpenAISpeechToTextProvider(configuration=configuration)
