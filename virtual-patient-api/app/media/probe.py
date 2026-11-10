"""Inspect encoded packet timing independently of client-declared duration."""
import json
import math
import subprocess
from pathlib import Path


def probe_media_timing(path: Path, stream: str | None = None) -> dict:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
        *(["-select_streams", stream] if stream else []),
        "-show_packets", "-show_entries", "packet=pts_time,duration_time", "-of", "json", str(path),
    ], check=True, capture_output=True, text=True, timeout=60)
    packets = json.loads(result.stdout).get("packets", [])
    intervals = []
    for packet in packets:
        try:
            start = float(packet["pts_time"])
            duration = float(packet.get("duration_time", 0))
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(start) and math.isfinite(duration) and duration >= 0:
            intervals.append((start, start + duration))
    if not intervals:
        raise ValueError("Encoded media timing is unavailable")
    first = min(start for start, _ in intervals)
    last = max(end for _, end in intervals)
    covered_until = first
    max_gap = 0.0
    for start, end in sorted(intervals):
        max_gap = max(max_gap, start - covered_until)
        covered_until = max(covered_until, end)
    return {"start_pts_ms": round(first * 1000), "end_pts_ms": round(last * 1000),
            "max_gap_ms": round(max_gap * 1000),
            "duration_ms": round((last - first) * 1000), "packet_count": len(intervals),
            "probe": "ffprobe_packets_v1"}
