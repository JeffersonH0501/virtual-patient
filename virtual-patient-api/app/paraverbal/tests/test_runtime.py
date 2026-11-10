"""Native runtime checks, using generated audio and no participant recordings."""
import builtins
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from app.paraverbal.opensmile_extractor import StudentTurnAudio, analyze_student_turns
from scripts import verify_deployment


def test_missing_audio_dependency_is_a_technical_failure(monkeypatch):
    original_import = builtins.__import__

    def import_without_opensmile(name, *args, **kwargs):
        if name == "opensmile":
            raise ImportError("Synthetic native dependency failure")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_opensmile)
    with pytest.raises(RuntimeError, match="OpenSMILE runtime"):
        analyze_student_turns(Path("unused.wav"), [StudentTurnAudio("synthetic", 0, 2000, "Test")])


def test_native_audio_extraction_without_legacy_voice_calibration():
    # Match the existing fresh-process pipeline boundary, outside visual ML tests.
    completed = subprocess.run(
        [sys.executable, "-c",
         "import json; import app.multimodal.pipeline; "
         "from scripts.verify_deployment import verify_audio_runtime; "
         "print(json.dumps(verify_audio_runtime()))"],
        capture_output=True, text=True, timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["feature_frames"] > 0
    assert result["voiced_frames"] > 0
    assert result["vad_frames"] > 0
    assert len(result["vad_model_sha256"]) == 64
    assert "voice_baseline" not in result


@pytest.mark.parametrize("status", ["healthy", "unhealthy"])
def test_deployment_checks_internal_visual_worker(monkeypatch, status):
    response = Mock()
    response.json.return_value = {"status": status}
    get = Mock(return_value=response)
    monkeypatch.setattr("requests.get", get)
    if status == "healthy":
        verify_deployment.verify_video_worker()
    else:
        with pytest.raises(RuntimeError, match="Video processing worker"):
            verify_deployment.verify_video_worker()
    assert get.call_args.args[0].endswith(":8010/health")
    response.raise_for_status.assert_called_once()
