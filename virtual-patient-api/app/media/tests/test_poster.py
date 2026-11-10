"""First-frame previews decode without altering or persisting captured media."""
import subprocess
import pytest
from app.media.poster import first_video_frame


def test_first_frame_is_a_jpeg_without_changing_the_source(tmp_path):
    path = tmp_path / "source.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:size=160x90:duration=1",
        "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", str(path),
    ], check=True, timeout=15)
    original = path.read_bytes()
    image = first_video_frame(path)
    assert image.startswith(b"\xff\xd8") and image.endswith(b"\xff\xd9")
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_invalid_video_does_not_create_or_delete_files(tmp_path):
    path = tmp_path / "invalid.webm"
    path.write_bytes(b"invalid video")
    with pytest.raises(subprocess.CalledProcessError):
        first_video_frame(path)
    assert path.read_bytes() == b"invalid video"
    assert list(tmp_path.iterdir()) == [path]
