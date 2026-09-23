"""Small, dependency-free runtime measurements for structured diagnostics."""

from __future__ import annotations

import os
from pathlib import Path


def current_rss_mb() -> float | None:
    """Return current resident memory on Linux without logging process details."""
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        return None
    return None


def process_id() -> int:
    """Expose the PID so concurrent isolated workers can be correlated."""
    return os.getpid()
