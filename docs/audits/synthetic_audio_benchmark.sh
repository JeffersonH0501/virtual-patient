#!/usr/bin/env bash
# Non-human sine/silence fixtures; measures execution cost, never speech accuracy.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
docker compose -f docker-compose.local.yml run --rm --no-deps -T api python - <<'PY'
import json
import math
import struct
import tempfile
import time
import wave
from pathlib import Path
from app.paraverbal.opensmile_extractor import StudentTurnAudio, analyze_student_turns
from app.utils.runtime_metrics import current_rss_mb
with tempfile.TemporaryDirectory(prefix='readiness-audio-') as directory:
    for seconds in (2, 10):
        path = Path(directory) / f'synthetic-{seconds}.wav'
        rate = 16000
        samples = [int(6000 * math.sin(2 * math.pi * 160 * i / rate)) if i % rate < 12000 else 0 for i in range(seconds * rate)]
        with wave.open(str(path), 'wb') as output:
            output.setnchannels(1); output.setsampwidth(2); output.setframerate(rate)
            output.writeframes(struct.pack(f'<{len(samples)}h', *samples))
        started = time.perf_counter()
        raw = analyze_student_turns(path, [StudentTurnAudio('synthetic', 0, seconds * 1000, 'Synthetic audio fixture')]).get('synthetic')
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(json.dumps({'fixture': 'synthetic 160Hz sine/silence, not human speech', 'durationSeconds': seconds,
                         'executionMs': round(elapsed_ms, 2), 'rssMbAfter': current_rss_mb(),
                         'hasRawFeatures': raw is not None, 'featureFrames': len(raw.loudness_samples) if raw else 0}))
PY
