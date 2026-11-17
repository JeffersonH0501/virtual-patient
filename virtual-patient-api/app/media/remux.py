"""Lossless container rewrite so browser originals are seekable on replay.

MediaRecorder writes WebM without duration or cues. Rewriting the container
with stream copy adds both without touching a single encoded packet. Timestamps
are copied verbatim (``-copyts``; otherwise Opus pre-skip shifts the timeline),
the result is verified packet by packet, and it is reproducible (bitexact), so
the same upload always yields the same bytes.
"""
import json
import os
import subprocess
from pathlib import Path

REMUX_VERSION = "remuxed_copy_v1"
_MUXER_FLAGS = {".webm": ["-cues_to_front", "1"], ".mp4": ["-movflags", "+faststart"]}


def _packets(path: Path) -> dict[int, list[tuple]]:
    """Packet (timestamp, size) sequence per stream; the muxer may interleave equal timestamps differently."""
    result = subprocess.run([
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-show_packets",
        "-show_entries", "packet=stream_index,pts_time,size", "-of", "json", str(path),
    ], check=True, capture_output=True, text=True, timeout=60)
    streams: dict[int, list[tuple]] = {}
    for item in json.loads(result.stdout).get("packets", []):
        streams.setdefault(item.get("stream_index"), []).append((item.get("pts_time"), item.get("size")))
    return streams


def _ffmpeg_version() -> str:
    result = subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, text=True, timeout=10)
    return result.stdout.split("\n", 1)[0]


def remux_for_replay(path: Path) -> dict:
    """Rewrite ``path`` in place when the copy is packet-identical; otherwise keep it as recorded."""
    flags = _MUXER_FLAGS.get(path.suffix.lower())
    if flags is None:
        return {"container": "as_recorded", "reason": "unsupported_container"}
    temporary = path.with_name(f".{path.name}.remux{path.suffix}")
    try:
        before = _packets(path)
        subprocess.run([
            "ffmpeg", "-v", "error", "-y", "-copyts", "-i", str(path), "-map", "0", "-c", "copy",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact", *flags, str(temporary),
        ], check=True, capture_output=True, timeout=120)
        if not before or _packets(temporary) != before:
            return {"container": "as_recorded", "reason": "packet_mismatch"}
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        temporary.replace(path)
        return {"container": REMUX_VERSION, "ffmpeg": _ffmpeg_version(),
                "verified_packets": sum(len(packets) for packets in before.values())}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"container": "as_recorded", "reason": "remux_failed"}
    finally:
        temporary.unlink(missing_ok=True)
