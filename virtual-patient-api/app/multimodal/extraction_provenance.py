"""Content-addressed extraction identity in the existing recording JSON."""
import hashlib
import json
import platform
import subprocess
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

from app.multimodal.quality_policy import QUALITY_POLICY_VERSION

APP_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    "multimodal/pipeline.py", "multimodal/turn_results.py", "multimodal/quality_policy.py", "multimodal/threshold_engine.py",
    "multimodal/label_engine.py", "multimodal/evidence_text.py", "multimodal/extraction_provenance.py",
    "nonverbal/mediapipe_extractor.py", "nonverbal/shared_observations.py", "nonverbal/gaze.py",
    "nonverbal/ccdbhg.py", "nonverbal/smile.py", "nonverbal/video_observations.py",
    "nonverbal/preprocessing.py", "paraverbal/opensmile_extractor.py", "paraverbal/preprocessing.py", "paraverbal/silero_vad.py",
    "multimodal/turn_video_queue.py", "multimodal/isolated_worker.py", "multimodal/calibration.py",
    "multimodal/config_loader.py", "multimodal/schemas.py", "multimodal/block_turns.py",
    "media/patient_roi.py", "nonverbal/iris.py", "nonverbal/gaze_calibration.py",
)
MODEL_FILES = (
    "face_landmarker_v2_with_blendshapes.task",
    "ccdbhg_cnn_lmk_hp/ckpt.pth.tar", "ccdbhg_cnn_lmk_hp/config.yaml", "ccdbhg_cnn_lmk_hp/train_stats.pkl",
)
PACKAGES = ("numpy", "pyarrow", "opensmile", "onnxruntime", "mediapipe", "torch", "scipy", "opencv-contrib-python")


def _file_hash(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def build_extraction_manifest(config, *, mode, references=None, calibration=None):
    """Identify actual mounted sources, artifacts and installed native runtime."""
    packages = {}
    for name in PACKAGES:
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "unavailable"
    ffmpeg = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True, timeout=10)
    return {
        "manifest_version": "extraction_v1", "mode": mode,
        "source_hashes": {name: _file_hash(APP_ROOT / name) for name in SOURCE_FILES},
        "model_hashes": {**{name: _file_hash(APP_ROOT / "nonverbal/models" / name) for name in MODEL_FILES},
                         "silero_vad.onnx": _file_hash(Path('/usr/local/share/silero-vad/silero_vad.onnx'))},
        "runtime": {"python": platform.python_version(), "machine": platform.machine(),
                    "ffmpeg": ffmpeg.stdout.splitlines()[0], "packages": packages},
        "methodology": {"versions": config.versions.model_dump(), "config_hash": config.config_hash,
                        "quality_policy": QUALITY_POLICY_VERSION},
        "references": references,
        "calibration_sha256": hashlib.sha256(json.dumps(calibration, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
    }


def record_extraction_manifest(recording, manifest):
    """Append an immutable manifest; multiple results share its hash reference."""
    serialized = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False)
    identifier = hashlib.sha256(serialized.encode()).hexdigest()
    snapshot = json.loads(serialized)
    capture = dict(recording.capture_config or {})
    manifests = dict(capture.get("extraction_manifests", {}))
    if identifier in manifests and manifests[identifier] != snapshot:
        raise ValueError("Extraction manifest identity conflict")
    manifests[identifier] = snapshot
    recording.capture_config = {**capture, "extraction_manifests": manifests}
    return identifier
