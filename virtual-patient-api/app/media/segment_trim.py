"""Retain only the confirmed timeline from a browser recording source."""

import hashlib
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from app.media.probe import probe_media_timing
from app.media.storage import StoredMedia, check_upload_size


_ENCODERS = {
    "audio/mp4": ["-c:a", "aac"],
    "audio/ogg": ["-c:a", "libopus"],
    "audio/webm": ["-c:a", "libopus"],
    "video/mp4": ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"],
    "video/webm": ["-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "5"],
}


def trim_segment_source(path: Path, stored: StoredMedia, content_type: str,
                        duration_ms: int, tolerance_ms: int, size_limit: int):
    stream = "a:0" if content_type.startswith("audio/") else "v:0"
    encoded = probe_media_timing(path, stream)
    if abs(encoded["start_pts_ms"]) > tolerance_ms or encoded.get("max_gap_ms", 0) > tolerance_ms:
        raise ValueError("Encoded source has a delayed origin or a discontinuous timeline")
    if encoded["duration_ms"] <= 0 or encoded["duration_ms"] < duration_ms - tolerance_ms:
        raise ValueError("Source ends before the confirmed segment boundary")
    with TemporaryDirectory(dir=path.parent) as temporary:
        output = Path(temporary) / path.name
        subprocess.run([
            "ffmpeg", "-v", "error", "-nostdin", "-protocol_whitelist", "file,pipe",
            "-i", str(path), "-map", f"0:{stream}", "-map_metadata", "-1",
            "-t", f"{duration_ms / 1000:.3f}", *_ENCODERS[content_type], str(output),
        ], check=True, capture_output=True, timeout=300)
        encoded = probe_media_timing(output, stream)
        if abs(encoded["duration_ms"] - duration_ms) > tolerance_ms:
            raise ValueError("Trimmed media does not cover the confirmed segment")
        size = output.stat().st_size
        check_upload_size(size, size_limit)
        with output.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        output.replace(path)
    return StoredMedia(stored.storage_key, size, digest), encoded
