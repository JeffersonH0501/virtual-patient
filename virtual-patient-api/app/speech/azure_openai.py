"""Azure OpenAI v1 implementations of the neutral speech contracts."""

from openai import OpenAI, OpenAIError

from app.core.azure_openai import create_azure_openai_client, create_openai_client
from app.core.config import Settings, settings
from app.speech.contracts import (
    DeliveryTone,
    HesitationFrequency,
    IntonationVariation,
    PauseFrequency,
    SpeechConfigurationError,
    SpeechProviderError,
    SpeechSynthesisRequest,
    SpeechTranscriptionRequest,
    SpeakingRate,
    SynthesizedAudio,
    TranscriptionResult,
    VocalEnergy,
    VocalStyle,
)


def render_vocal_instructions(style: VocalStyle) -> str:
    """Translate a neutral vocal style into Azure OpenAI TTS instructions."""
    speaking_rate = {
        SpeakingRate.MODERATELY_SLOW: "a moderately slow",
        SpeakingRate.MODERATE: "a moderate",
        SpeakingRate.BRISK: "a brisk",
    }[style.speaking_rate]
    pauses = {
        PauseFrequency.SPARSE: "Use few pauses and keep the delivery concise.",
        PauseFrequency.NATURAL: "Use natural conversational pauses.",
        PauseFrequency.OCCASIONAL: "Use occasional short pauses.",
        PauseFrequency.FREQUENT: "Use frequent short pauses without becoming unnatural.",
    }[style.pause_frequency]
    energy = {
        VocalEnergy.LOW: "Keep vocal energy low but audible.",
        VocalEnergy.MODERATE: "Keep vocal energy moderate.",
        VocalEnergy.HIGH: "Use high vocal energy without shouting.",
    }[style.energy]
    intonation = {
        IntonationVariation.RESTRAINED: "Keep intonation variation restrained.",
        IntonationVariation.NATURAL: "Use natural intonation variation.",
        IntonationVariation.EXPRESSIVE: "Use expressive but realistic intonation variation.",
    }[style.intonation_variation]
    hesitation = {
        HesitationFrequency.NONE: "Avoid vocal hesitation.",
        HesitationFrequency.LIGHT: (
            "Use light vocal hesitation without adding filler words."
        ),
        HesitationFrequency.OCCASIONAL: (
            "Use occasional vocal hesitation without adding filler words."
        ),
    }[style.hesitation_frequency]
    delivery = {
        DeliveryTone.NEUTRAL: "Use a neutral conversational delivery.",
        DeliveryTone.REASSURING: "Use a reassuring conversational delivery.",
        DeliveryTone.SELF_ASSURED: "Use a self-assured conversational delivery.",
        DeliveryTone.IMPATIENT: "Use a mildly impatient, clipped delivery.",
        DeliveryTone.UNCERTAIN: "Use an uncertain but intelligible delivery.",
        DeliveryTone.REFLECTIVE: "Use a reflective conversational delivery.",
    }[style.delivery_tone]
    return " ".join(
        (
            f"Speak at {speaking_rate} pace.",
            pauses,
            energy,
            intonation,
            hesitation,
            delivery,
            (
                "Preserve the supplied text exactly. Do not add, remove, "
                "paraphrase, or reorder words."
            ),
        )
    )


class AzureOpenAITextToSpeechProvider:
    """Generate speech through an Azure OpenAI v1 deployment."""

    provider_name = "azure_openai"

    def __init__(
        self,
        client: OpenAI | None = None,
        deployment_name: str | None = None,
        configuration: Settings = settings,
    ):
        self.client = client
        self.deployment_name = (
            deployment_name or configuration.azure_openai_tts_deployment_name
        )

    def synthesize(self, request: SpeechSynthesisRequest) -> SynthesizedAudio:
        """Generate audio with the configured Azure deployment."""
        if not request.text.strip():
            raise SpeechProviderError("Speech synthesis text cannot be empty")
        if not self.deployment_name:
            raise SpeechConfigurationError(
                "AZURE_OPENAI_TTS_DEPLOYMENT_NAME is required"
            )

        client = self.client or create_openai_client()
        arguments = {
            "model": self.deployment_name,
            "input": request.text,
            "voice": request.voice,
            "response_format": request.response_format,
        }
        instructions = None
        if request.vocal_style:
            instructions = render_vocal_instructions(request.vocal_style)
            arguments["instructions"] = instructions
        try:
            response = client.audio.speech.create(**arguments)
        except (OpenAIError, RuntimeError) as error:
            raise SpeechProviderError(f"Text-to-speech request failed: {error}") from error

        if not response.content:
            raise SpeechProviderError("Text-to-speech provider returned empty audio")
        return SynthesizedAudio(
            content=response.content,
            content_type="audio/mpeg",
            provider=self.provider_name,
            model=self.deployment_name,
            voice=request.voice,
            style_policy_version=(
                request.vocal_style.policy_version if request.vocal_style else None
            ),
            synthesis_instructions=instructions,
        )


class AzureOpenAISpeechToTextProvider:
    """Transcribe audio through an Azure OpenAI v1 deployment."""

    provider_name = "azure_openai"

    def __init__(
        self,
        client: OpenAI | None = None,
        deployment_name: str | None = None,
        configuration: Settings = settings,
    ):
        self.client = client
        self.deployment_name = (
            deployment_name or configuration.azure_openai_stt_deployment_name
        )

    def transcribe(self, request: SpeechTranscriptionRequest) -> TranscriptionResult:
        """Transcribe audio without persisting the uploaded media."""
        if not request.content:
            raise SpeechProviderError("Audio content cannot be empty")
        if not self.deployment_name:
            raise SpeechConfigurationError(
                "AZURE_OPENAI_STT_DEPLOYMENT_NAME is required"
            )

        client = self.client or create_azure_openai_client()
        arguments = {
            "model": self.deployment_name,
            "file": (
                request.filename,
                request.content,
                request.content_type,
            ),
        }
        if request.language:
            arguments["language"] = request.language
        try:
            response = client.audio.transcriptions.create(**arguments)
        except (OpenAIError, RuntimeError) as error:
            raise SpeechProviderError(f"Speech-to-text request failed: {error}") from error

        text = getattr(response, "text", "").strip()
        if not text:
            raise SpeechProviderError("Speech-to-text provider returned empty text")
        return TranscriptionResult(
            text=text,
            language=request.language,
            provider=self.provider_name,
            model=self.deployment_name,
        )
