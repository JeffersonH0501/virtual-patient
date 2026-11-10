"""A pending provider must not stall unrelated requests on the API event loop."""
import asyncio
from io import BytesIO
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, UploadFile

from app.routers import speech
from app.speech.contracts import SynthesizedAudio, TranscriptionResult


@pytest.mark.parametrize("operation", ["transcription", "synthesis"])
def test_pending_speech_provider_keeps_the_event_loop_available(monkeypatch, operation):
    entered, release = Event(), Event()
    service = MagicMock()
    user = SimpleNamespace(id=1)

    def provider(*args):
        entered.set()
        if not release.wait(2):
            raise TimeoutError("Synthetic provider was blocked by its event loop")
        if operation == "transcription":
            return TranscriptionResult("Synthetic input", "en", "synthetic", "synthetic")
        return SynthesizedAudio(b"synthetic audio", "audio/mpeg", "synthetic", "synthetic")

    monkeypatch.setattr(speech, "SpeechService", lambda: service)
    if operation == "transcription":
        service.transcribe.side_effect = provider
        request = lambda: speech.transcribe_audio(
            audio=UploadFile(BytesIO(b"synthetic"), filename="synthetic.wav"), language="en", current_user=user,
        )
    else:
        service.synthesize_patient_message.side_effect = provider
        access = MagicMock()
        access.validate_interview_access.return_value = True
        monkeypatch.setattr(speech, "MedicalInterviewController", lambda db: access)
        messages = MagicMock()
        messages.get_message.return_value = SimpleNamespace(interview_id=7, sender_type="patient", content="Synthetic input")
        monkeypatch.setattr(speech, "MessageController", lambda db: messages)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        request = lambda: speech.synthesize_patient_message(7, 9, db=db, current_user=user)

    async def scenario():
        pending = asyncio.create_task(request())
        try:
            assert await asyncio.wait_for(asyncio.to_thread(entered.wait, 3), timeout=4)
            assert not pending.done(), "The provider prevented the event loop from making progress"
            await asyncio.sleep(0)
        finally:
            release.set()
            result = await pending
        if operation == "transcription":
            assert result.text == "Synthetic input"
        else:
            assert result.body == b"synthetic audio"

    asyncio.run(scenario())


@pytest.mark.parametrize("disconnect", [False, True])
def test_patient_mp3_sends_first_chunk_before_reading_next(monkeypatch, disconnect):
    closed = Event()
    first_sent = Event()

    def chunks(_request):
        try:
            yield b"first"
            assert first_sent.is_set()
            yield b"second"
        finally:
            closed.set()

    monkeypatch.setattr(speech, "_patient_speech_inputs", lambda *_: ("Synthetic input", None, None))
    monkeypatch.setattr(speech, "AzureOpenAITextToSpeechProvider", lambda: SimpleNamespace(stream=chunks))

    async def scenario():
        response = await speech.stream_patient_message(7, 9, db=None, current_user=SimpleNamespace(id=1))
        assert response.media_type == "audio/mpeg"
        bodies = []

        async def send(message):
            if message["type"] == "http.response.body":
                bodies.append(message["body"])
                first_sent.set()
                if disconnect:
                    raise OSError("Client disconnected")

        if disconnect:
            with pytest.raises(OSError):
                await response.stream_response(send)
            assert bodies == [b"first"]
        else:
            await response.stream_response(send)
            assert bodies == [b"first", b"second", b""]
        assert closed.is_set()

    asyncio.run(scenario())


def test_patient_stream_checks_interview_access_before_opening_provider(monkeypatch):
    access = SimpleNamespace(validate_interview_access=lambda *_: False)
    provider = MagicMock()
    monkeypatch.setattr(speech, "MedicalInterviewController", lambda _: access)
    monkeypatch.setattr(speech, "AzureOpenAITextToSpeechProvider", provider)

    with pytest.raises(HTTPException) as error:
        asyncio.run(speech.stream_patient_message(7, 9, db=None, current_user=SimpleNamespace(id=2)))
    assert error.value.status_code == 403
    provider.assert_not_called()
