"""Speech transports are shared without retaining request data."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.speech import azure_openai as speech
from app.speech.contracts import SpeechSynthesisRequest, SpeechTranscriptionRequest


@pytest.fixture(autouse=True)
def clean_clients():
    speech.close_speech_clients()
    yield
    speech.close_speech_clients()


@pytest.mark.parametrize("kind,factory", [
    ("stt", "create_azure_openai_client"), ("tts", "create_openai_client"),
])
def test_concurrent_first_use_creates_one_transport(kind, factory):
    with patch.object(speech, factory) as create:
        with ThreadPoolExecutor(max_workers=5) as workers:
            clients = list(workers.map(speech._get_speech_client, [kind] * 5))
        create.assert_called_once_with()
        assert all(client is create.return_value for client in clients)


def test_failed_initialization_can_retry_and_shutdown_releases_transports():
    first, second, replacement = MagicMock(), MagicMock(), MagicMock()
    with patch.object(speech, "create_openai_client", side_effect=[
        RuntimeError("unavailable"), first, replacement,
    ]), patch.object(speech, "create_azure_openai_client", return_value=second):
        with pytest.raises(RuntimeError, match="unavailable"):
            speech._get_speech_client("tts")
        assert speech._get_speech_client("tts") is first
        assert speech._get_speech_client("stt") is second
        speech.close_speech_clients()
        first.close.assert_called_once_with()
        second.close.assert_called_once_with()
        assert speech._get_speech_client("tts") is replacement


def test_separate_provider_instances_reuse_transport_and_keep_requests_separate():
    with patch.object(speech, "create_openai_client") as tts_factory, patch.object(
        speech, "create_azure_openai_client",
    ) as stt_factory:
        tts_factory.return_value.audio.speech.create.return_value = SimpleNamespace(
            content=b"synthetic audio",
        )
        stt_factory.return_value.audio.transcriptions.create.side_effect = [
            SimpleNamespace(text="First"), SimpleNamespace(text="Second"),
        ]
        for text in ("First", "Second"):
            speech.AzureOpenAITextToSpeechProvider(deployment_name="tts").synthesize(
                SpeechSynthesisRequest(text=text, voice="alloy"),
            )
            result = speech.AzureOpenAISpeechToTextProvider(
                deployment_name="stt",
            ).transcribe(SpeechTranscriptionRequest(
                content=text.encode(), filename="synthetic.mp3",
                content_type="audio/mpeg", language="en",
            ))
            assert result.text == text
        tts_factory.assert_called_once_with()
        stt_factory.assert_called_once_with()
        calls = tts_factory.return_value.audio.speech.create.call_args_list
        assert [call.kwargs["input"] for call in calls] == ["First", "Second"]
        calls = stt_factory.return_value.audio.transcriptions.create.call_args_list
        assert [call.kwargs["file"][1] for call in calls] == [b"First", b"Second"]
