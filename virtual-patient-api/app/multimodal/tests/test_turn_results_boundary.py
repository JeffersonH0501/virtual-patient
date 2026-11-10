"""The shared result policy must remain independently usable and traceable."""
import hashlib
from pathlib import Path
import subprocess
import sys

from app.multimodal.config_loader import load_methodology_config
from app.multimodal.extraction_provenance import build_extraction_manifest


def test_manifest_hashes_the_canonical_result_policy():
    manifest = build_extraction_manifest(load_methodology_config(), mode="stored_visual")
    source = Path(__file__).resolve().parents[1] / "turn_results.py"
    assert manifest["source_hashes"]["multimodal/turn_results.py"] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_saved_result_policy_does_not_load_the_native_orchestrator():
    result = subprocess.run([sys.executable, "-c", """
import sys
from app.multimodal import turn_results
assert callable(turn_results.compute_session_references)
assert 'app.multimodal.pipeline' not in sys.modules
assert 'tensorflow' not in sys.modules
assert 'opensmile' not in sys.modules
"""], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
