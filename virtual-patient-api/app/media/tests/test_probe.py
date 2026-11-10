"""Encoded timing is measured independently of session declarations."""
import subprocess
import pytest
from app.media.probe import probe_media_timing


def test_probe_measures_synthetic_encoded_audio(tmp_path):
    path = tmp_path / "tone.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(path)], check=True, timeout=15)
    timing = probe_media_timing(path)
    assert timing["duration_ms"] == pytest.approx(1000, abs=25)
    assert timing["packet_count"] > 0


def test_probe_rejects_invalid_media(tmp_path):
    path = tmp_path / "invalid.webm"
    path.write_bytes(b"invalid media")
    with pytest.raises(subprocess.CalledProcessError):
        probe_media_timing(path)
