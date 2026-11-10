"""Pinned Silero ONNX speech intervals on the original 16 kHz turn clock."""
from functools import lru_cache
import hashlib
from math import isfinite
from pathlib import Path

import numpy as np

MODEL_PATH = Path('/usr/local/share/silero-vad/silero_vad.onnx')
MODEL_SHA256 = '1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3'
MODEL_VERSION = 'silero_vad_60b7ffa_onnx'
SAMPLE_RATE = 16000
FRAME_SAMPLES = 512
FRAME_MS = 32
THRESHOLD = .5
MIN_GAP_MS = 100


def speech_intervals(probabilities, *, duration_ms):
    """Merge detected frames separated by less than 100 ms without edge padding."""
    intervals = []
    start = None
    for index, probability in enumerate(probabilities):
        if not isfinite(float(probability)) or not 0 <= probability <= 1:
            raise ValueError('VAD probabilities must be finite and within [0, 1]')
        at = min(index * FRAME_MS, duration_ms)
        if probability >= THRESHOLD and at < duration_ms:
            if start is None:
                start = at
        elif start is not None:
            intervals.append((start, at))
            start = None
    if start is not None:
        intervals.append((start, min(len(probabilities) * FRAME_MS, duration_ms)))
    merged = []
    for start, end in intervals:
        if merged and start - merged[-1][1] < MIN_GAP_MS:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


@lru_cache(maxsize=1)
def _session():
    import onnxruntime as ort
    if hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError('Silero VAD model hash mismatch')
    options = ort.SessionOptions()
    options.inter_op_num_threads = 1
    options.intra_op_num_threads = 1
    return ort.InferenceSession(str(MODEL_PATH), sess_options=options, providers=['CPUExecutionProvider'])


def detect_speech(samples):
    """Return intervals and per-frame model probabilities for mono 16 kHz PCM."""
    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim != 1 or not np.isfinite(audio).all():
        raise ValueError('VAD audio must be finite mono PCM')
    if not len(audio):
        return [], []
    session = _session()
    state = np.zeros((2, 1, 128), dtype=np.float32)
    context = np.zeros((1, 64), dtype=np.float32)
    probabilities = []
    for start in range(0, len(audio), FRAME_SAMPLES):
        frame = np.zeros((1, FRAME_SAMPLES), dtype=np.float32)
        chunk = audio[start:start + FRAME_SAMPLES]
        frame[0, :len(chunk)] = chunk
        model_input = np.concatenate((context, frame), axis=1)
        result, state = session.run(None, {'input': model_input, 'state': state, 'sr': np.asarray(SAMPLE_RATE, dtype=np.int64)})
        probabilities.append(float(result[0][0]))
        context = model_input[:, -64:]
    duration_ms = len(audio) * 1000 / SAMPLE_RATE
    return speech_intervals(probabilities, duration_ms=duration_ms), probabilities
