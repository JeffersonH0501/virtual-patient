"""A patient message uses the first complete original on every playback."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest

from app.speech.contracts import SynthesizedAudio


def test_concurrent_replay_reuses_exact_original_and_failed_generation_is_not_published(tmp_path):
    from app.speech.preserved_audio import preserved_patient_audio
    from app.media.storage import LocalMediaStorage
    storage = LocalMediaStorage(tmp_path)
    generate = Mock(return_value=SynthesizedAudio(b"exact-mp3", "audio/mpeg", "synthetic", "test"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: preserved_patient_audio(storage, 11, "recording", 9, generate), range(4)))
    assert all(path.read_bytes() == b"exact-mp3" for path in results)
    assert generate.call_count == 1
    failed = Mock(side_effect=RuntimeError("Synthetic synthesis failure"))
    with pytest.raises(RuntimeError):
        preserved_patient_audio(storage, 11, "recording", 10, failed)
    assert not (results[0].parent / "10.mp3").exists()
    assert preserved_patient_audio(storage, 11, "recording", 10, generate).read_bytes() == b"exact-mp3"
    storage.delete_recording(11, "recording")
    assert not results[0].exists()
