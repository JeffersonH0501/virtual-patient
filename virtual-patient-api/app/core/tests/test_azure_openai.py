"""Unit tests for Azure OpenAI v1 client configuration."""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.core import azure_openai
from app.core.config import Settings
from app.utils import tts_service


def configured_settings(**overrides: object) -> Settings:
    """Build isolated Azure settings for unit tests."""
    values: dict[str, object] = {
        "azure_openai_api_key": "test-key",
        "azure_openai_endpoint": "https://example.openai.azure.com/",
        "azure_openai_llm_deployment_name": "llm-normal",
        "azure_openai_llm_mini_deployment_name": "llm-mini",
        "azure_openai_stt_deployment_name": "speech-to-text",
        "azure_openai_tts_deployment_name": "text-to-speech",
        "azure_openai_embedding_deployment_name": "text-embedding",
    }
    values.update(overrides)
    return Settings(**values)


class AzureOpenAIConfigurationTests(unittest.TestCase):
    def test_v1_base_url_normalization(self) -> None:
        cases = [
            (
                "https://example.openai.azure.com/",
                "https://example.openai.azure.com/openai/v1/",
            ),
            (
                "https://example.openai.azure.com/openai/v1",
                "https://example.openai.azure.com/openai/v1/",
            ),
            ("", ""),
        ]
        for endpoint, expected in cases:
            with self.subTest(endpoint=endpoint):
                configured = configured_settings(azure_openai_endpoint=endpoint)
                self.assertEqual(configured.azure_openai_v1_base_url, expected)

    def test_default_chat_model_uses_mini_deployment(self) -> None:
        fake_settings = configured_settings()
        with (
            patch.object(azure_openai, "settings", fake_settings),
            patch.object(azure_openai, "ChatOpenAI") as chat_class,
        ):
            azure_openai.create_chat_model(temperature=0.2)

        self.assertEqual(
            chat_class.call_args.kwargs,
            {
                "model": "llm-mini",
                "api_key": "test-key",
                "base_url": "https://example.openai.azure.com/openai/v1/",
                "temperature": 0.2,
            },
        )

    def test_chat_model_can_explicitly_use_normal_deployment(self) -> None:
        with (
            patch.object(azure_openai, "settings", configured_settings()),
            patch.object(azure_openai, "ChatOpenAI") as chat_class,
        ):
            azure_openai.create_chat_model(variant=azure_openai.LLMVariant.NORMAL)

        self.assertEqual(chat_class.call_args.kwargs["model"], "llm-normal")

    def test_embeddings_use_canonical_deployment_and_dimensions(self) -> None:
        with (
            patch.object(azure_openai, "settings", configured_settings()),
            patch.object(azure_openai, "OpenAIEmbeddings") as embeddings_class,
        ):
            azure_openai.create_embeddings()

        kwargs = embeddings_class.call_args.kwargs
        self.assertEqual(kwargs["model"], "text-embedding")
        self.assertEqual(kwargs["dimensions"], azure_openai.EMBEDDING_DIMENSIONS)
        self.assertEqual(azure_openai.EMBEDDING_DIMENSIONS, 1536)
        self.assertTrue(kwargs["base_url"].endswith("/openai/v1/"))

    def test_standard_client_uses_v1_base_url(self) -> None:
        with (
            patch.object(azure_openai, "settings", configured_settings()),
            patch.object(azure_openai, "OpenAI") as openai_class,
        ):
            azure_openai.create_openai_client()

        self.assertEqual(
            openai_class.call_args.kwargs,
            {
                "api_key": "test-key",
                "base_url": "https://example.openai.azure.com/openai/v1/",
            },
        )

    def test_incomplete_configuration_names_the_missing_variable(self) -> None:
        cases = [
            ({"azure_openai_api_key": None}, "AZURE_OPENAI_API_KEY"),
            ({"azure_openai_endpoint": None}, "AZURE_OPENAI_ENDPOINT"),
            (
                {"azure_openai_llm_mini_deployment_name": None},
                "AZURE_OPENAI_LLM_MINI_DEPLOYMENT_NAME",
            ),
            (
                {"azure_openai_embedding_deployment_name": None},
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME",
            ),
        ]
        for overrides, variable_name in cases:
            with self.subTest(variable_name=variable_name):
                fake_settings = configured_settings(**overrides)
                with patch.object(azure_openai, "settings", fake_settings):
                    with self.assertRaisesRegex(RuntimeError, variable_name):
                        if "EMBEDDING" in variable_name:
                            azure_openai.create_embeddings()
                        else:
                            azure_openai.create_chat_model()

    def test_tts_uses_sdk_audio_endpoint_and_configured_deployment(self) -> None:
        client = MagicMock()
        client.audio.speech.create.return_value = SimpleNamespace(content=b"mp3-data")
        fake_settings = configured_settings()

        with patch.object(tts_service, "settings", fake_settings):
            audio = tts_service.TTSService(client=client).generate_audio(
                "Short test sentence.",
                voice="alloy",
            )

        self.assertEqual(audio, b"mp3-data")
        client.audio.speech.create.assert_called_once_with(
            model="text-to-speech",
            input="Short test sentence.",
            voice="alloy",
            response_format="mp3",
        )

    def test_tts_does_not_call_provider_when_configuration_is_incomplete(self) -> None:
        client = MagicMock()
        fake_settings = configured_settings(azure_openai_tts_deployment_name=None)

        with patch.object(tts_service, "settings", fake_settings):
            audio = tts_service.TTSService(client=client).generate_audio(
                "Short test sentence.",
                voice="alloy",
            )

        self.assertIsNone(audio)
        client.audio.speech.create.assert_not_called()
