"""Verify the pinned BlazeGaze artifact in the API runtime."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import tensorflow as tf


ARTIFACT = Path(__file__).resolve().parents[1] / "app" / "nonverbal" / "models" / "blazegaze_mpiifacegaze.keras"
EXPECTED_SHA256 = "5b011cfe82466896e27b1ac3e18130117cafbc02dbc964a1ad7315f62005cc05"


def main() -> None:
    digest = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"Unexpected BlazeGaze artifact SHA-256: {digest}")

    model = tf.keras.models.load_model(ARTIFACT, compile=False)
    output = model(
        {
            "image": np.zeros((1, 128, 512, 3), dtype=np.float32),
            "head_vector": np.array([[0.0, 0.0, 1.0]], dtype=np.float32),
            "face_origin_3d": np.zeros((1, 3), dtype=np.float32),
        },
        training=False,
    )
    if tuple(output.shape) != (1, 2):
        raise RuntimeError(f"Unexpected BlazeGaze output shape: {tuple(output.shape)}")
    if not np.isfinite(output.numpy()).all():
        raise RuntimeError("BlazeGaze returned non-finite output")
    print(
        "BlazeGaze compatibility gate passed: "
        f"tensorflow={tf.__version__} keras={tf.keras.__version__} "
        f"shape={tuple(output.shape)} sha256={digest}"
    )


if __name__ == "__main__":
    main()
