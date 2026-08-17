"""Unit tests for Azure OpenAI v1 client configuration."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core import azure_openai
from app.core.config import Settings
from app.utils import tts_service


def configured_settings(**overrides: object) -> Settings:
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


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        (
            "https://example.openai.azure.com/",
            "https://example.openai.azure.com/openai/v1/",
        ),
        (
            "https://example.openai.azure.com/openai/v1",
            "https://example.openai.azure.com/openai/v1/",
        ),
        ("", ""),
    ],
)
def test_v1_base_url_normalization(endpoint: str, expected: str) -> None:
    configured = configured_settings(azure_openai_endpoint=endpoint)
    assert configured.azure_openai_v1_base_url == expected


def test_default_chat_model_uses_mini_deployment() -> None:
    fake_settings = configured_settings()
    with (
        patch.object(azure_openai, "settings", fake_settings),
        patch.object(azure_openai, "ChatOpenAI") as chat_class,
    ):
        azure_openai.create_chat_model(temperature=0.2)

    kwargs = chat_class.call_args.kwargs
    assert kwargs == {
        "model": "llm-mini",
        "api_key": "test-key",
        "base_url": "https://example.openai.azure.com/openai/v1/",
        "temperature": 0.2,
    }


def test_chat_model_can_explicitly_use_normal_deployment() -> None:
    with (
        patch.object(azure_openai, "settings", configured_settings()),
        patch.object(azure_openai, "ChatOpenAI") as chat_class,
    ):
        azure_openai.create_chat_model(variant=azure_openai.LLMVariant.NORMAL)

    assert chat_class.call_args.kwargs["model"] == "llm-normal"


def test_embeddings_use_canonical_deployment_and_dimensions() -> None:
    with (
        patch.object(azure_openai, "settings", configured_settings()),
        patch.object(azure_openai, "OpenAIEmbeddings") as embeddings_class,
    ):
        azure_openai.create_embeddings()

    kwargs = embeddings_class.call_args.kwargs
    assert kwargs["model"] == "text-embedding"
    assert kwargs["dimensions"] == azure_openai.EMBEDDING_DIMENSIONS == 1536
    assert kwargs["base_url"].endswith("/openai/v1/")


def test_standard_client_uses_v1_base_url() -> None:
    with (
        patch.object(azure_openai, "settings", configured_settings()),
        patch.object(azure_openai, "OpenAI") as openai_class,
    ):
        azure_openai.create_openai_client()

    assert openai_class.call_args.kwargs == {
        "api_key": "test-key",
        "base_url": "https://example.openai.azure.com/openai/v1/",
    }


@pytest.mark.parametrize(
    ("overrides", "variable_name"),
    [
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
    ],
)
def test_incomplete_configuration_fails_with_variable_name(
    overrides: dict[str, object],
    variable_name: str,
) -> None:
    fake_settings = configured_settings(**overrides)
    with patch.object(azure_openai, "settings", fake_settings):
        with pytest.raises(RuntimeError, match=variable_name):
            if "EMBEDDING" in variable_name:
                azure_openai.create_embeddings()
            else:
                azure_openai.create_chat_model()


def test_tts_uses_sdk_audio_endpoint_and_configured_deployment() -> None:
    client = MagicMock()
    client.audio.speech.create.return_value = SimpleNamespace(content=b"mp3-data")
    fake_settings = configured_settings()

    with patch.object(tts_service, "settings", fake_settings):
        audio = tts_service.TTSService(client=client).generate_audio(
            "Short test sentence.",
            voice="alloy",
        )

    assert audio == b"mp3-data"
    client.audio.speech.create.assert_called_once_with(
        model="text-to-speech",
        input="Short test sentence.",
        voice="alloy",
        response_format="mp3",
    )


def test_tts_does_not_call_provider_when_configuration_is_incomplete() -> None:
    client = MagicMock()
    fake_settings = configured_settings(azure_openai_tts_deployment_name=None)

    with patch.object(tts_service, "settings", fake_settings):
        audio = tts_service.TTSService(client=client).generate_audio(
            "Short test sentence.",
            voice="alloy",
        )

    assert audio is None
    client.audio.speech.create.assert_not_called()
