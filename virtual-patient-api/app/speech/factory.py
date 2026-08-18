"""Speech provider factories selected through application configuration."""

from app.core.config import Settings, settings
from app.speech.azure_openai import (
    AzureOpenAISpeechToTextProvider,
    AzureOpenAITextToSpeechProvider,
)
from app.speech.contracts import (
    SpeechConfigurationError,
    SpeechToTextProvider,
    TextToSpeechProvider,
)


def create_tts_provider(
    configuration: Settings = settings,
) -> TextToSpeechProvider:
    """Create the configured text-to-speech provider."""
    if configuration.speech_tts_provider == "azure_openai":
        return AzureOpenAITextToSpeechProvider(configuration=configuration)
    if configuration.speech_tts_provider == "disabled":
        raise SpeechConfigurationError("Text-to-speech is disabled")
    raise SpeechConfigurationError(
        f"Unsupported text-to-speech provider: {configuration.speech_tts_provider}"
    )


def create_stt_provider(
    configuration: Settings = settings,
) -> SpeechToTextProvider:
    """Create the configured speech-to-text provider."""
    if configuration.speech_stt_provider == "azure_openai":
        return AzureOpenAISpeechToTextProvider(configuration=configuration)
    if configuration.speech_stt_provider == "disabled":
        raise SpeechConfigurationError("Server speech-to-text is disabled")
    raise SpeechConfigurationError(
        f"Unsupported speech-to-text provider: {configuration.speech_stt_provider}"
    )
