"""Preserve one exact TTS original inside the recording's existing retention boundary."""
import fcntl
import os
from pathlib import Path
from uuid import uuid4

from app.speech.contracts import SpeechProviderError


def preserved_patient_audio(storage, interview_id, recording_id, message_id, generate) -> Path:
    directory = (storage.root / "interviews" / str(interview_id) / recording_id / "patient-speech").resolve()
    storage._assert_within_root(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{message_id}.mp3"
    # A per-message filesystem lock also serializes generators in other API processes.
    with (directory / f"{message_id}.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.is_file() and target.stat().st_size:
            return target
        audio = generate()
        if not audio.content or audio.content_type != "audio/mpeg":
            raise SpeechProviderError("Patient audio must be a nonempty MP3 original")
        storage._ensure_free_space(len(audio.content))
        temporary = directory / f".{message_id}-{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as output:
                output.write(audio.content)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(target)
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)
    return target
