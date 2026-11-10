#!/usr/bin/env python3
"""Verify database, native audio, and internal worker without external providers."""

from pathlib import Path
import sys

from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import engine  # noqa: E402


REQUIRED_LANGGRAPH_TABLES = {
    "checkpoint_blobs",
    "checkpoint_migrations",
    "checkpoint_writes",
    "checkpoints",
    "store",
    "store_migrations",
}


def scalar(query: str):
    with engine.connect() as connection:
        return connection.execute(text(query)).scalar_one()


def verify_audio_runtime() -> dict:
    """Extract generated harmonic audio, never participant media."""
    import tempfile
    import wave
    import numpy as np
    import opensmile
    from app.paraverbal.opensmile_extractor import StudentTurnAudio, analyze_student_turns
    from app.paraverbal.silero_vad import MODEL_SHA256

    sample_rate, duration_ms = 16000, 2000
    time = np.arange(sample_rate * 2) / sample_rate
    signal = sum(np.sin(2 * np.pi * 160 * harmonic * time) / harmonic
                 for harmonic in range(1, 9)) * 0.2
    with tempfile.TemporaryDirectory(prefix="deployment-audio-") as directory:
        path = Path(directory) / "synthetic.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes((signal * 32767).astype("<i2").tobytes())
        raw = analyze_student_turns(path, [StudentTurnAudio("synthetic", 0, duration_ms, "Synthetic audio")]).get("synthetic")
        smile = opensmile.Smile(feature_set=opensmile.FeatureSet.eGeMAPSv02,
                                feature_level=opensmile.FeatureLevel.LowLevelDescriptors)
        features = smile.process_file(str(path))
        pitch = next((name for name in features.columns if 'F0semitoneFrom27.5Hz' in name), None)
        loudness = next((name for name in features.columns if 'loudness' in name.lower()), None)
        if raw is None or not raw.vad_probabilities or raw.vad_model.get('sha256') != MODEL_SHA256 or pitch is None or loudness is None:
            raise RuntimeError("OpenSMILE or Silero VAD synthetic extraction failed")
        voiced_frames = sum(float(value) > 0 for value in features[pitch])
        if not voiced_frames:
            raise RuntimeError("OpenSMILE synthetic pitch extraction failed")
        return {"feature_frames": len(features), "voiced_frames": voiced_frames,
                "vad_frames": len(raw.vad_probabilities), "vad_model_sha256": MODEL_SHA256}


def verify_video_worker() -> None:
    import requests
    from app.core.config import settings
    response = requests.get(f"{settings.video_processing_worker_url}/health", timeout=10)
    response.raise_for_status()
    if response.json().get("status") != "healthy":
        raise RuntimeError("Video processing worker is not healthy")


def main() -> None:
    audio = verify_audio_runtime()
    verify_video_worker()
    case_count = scalar("SELECT COUNT(*) FROM clinical_cases")
    personality_count = scalar("SELECT COUNT(*) FROM personalities")
    alembic_revision = scalar("SELECT version_num FROM alembic_version")

    if case_count < 1:
        raise RuntimeError("No clinical cases are available")
    if personality_count < 1:
        raise RuntimeError("No personalities are available")

    available_tables = set(inspect(engine).get_table_names())
    missing_langgraph_tables = REQUIRED_LANGGRAPH_TABLES - available_tables
    if missing_langgraph_tables:
        missing = ", ".join(sorted(missing_langgraph_tables))
        raise RuntimeError(f"Missing LangGraph persistence tables: {missing}")

    print(f"Clinical cases: {case_count}")
    print(f"Personalities: {personality_count}")
    print(f"Alembic revision: {alembic_revision}")
    print("LangGraph persistence tables: ready")
    print(f"Native audio extraction: ready ({audio['feature_frames']} frames)")
    print("Internal video processing worker: ready")


if __name__ == "__main__":
    main()
