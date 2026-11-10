"""Decode the first video frame for private replay without persisting another asset."""
from pathlib import Path
import subprocess


def first_video_frame(path: Path) -> bytes:
    result = subprocess.run([
        "ffmpeg", "-v", "error", "-nostdin", "-protocol_whitelist", "file,pipe",
        "-threads", "1", "-i", str(path), "-map", "0:v:0", "-frames:v", "1",
        "-vf", "scale='min(640,iw)':-2", "-an", "-threads", "1",
        "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1",
    ], check=True, capture_output=True, timeout=15)
    if not result.stdout.startswith(b"\xff\xd8"):
        raise ValueError("Video has no decodable first frame")
    return result.stdout
