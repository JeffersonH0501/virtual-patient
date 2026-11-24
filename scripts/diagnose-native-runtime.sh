#!/usr/bin/env bash
set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
case "${1:-full}" in
  local) compose_file="$root/docker-compose.local.yml"; env_file="$root/.env.local" ;;
  full) compose_file="$root/docker-compose.full.yml"; env_file="$root/.env.full" ;;
  *) echo "Usage: bash scripts/diagnose-native-runtime.sh [local|full]" >&2; exit 2 ;;
esac
if [[ ! -r "$env_file" ]]; then echo "Missing environment file: $env_file" >&2; exit 2; fi
compose=(docker compose --env-file "$env_file" -f "$compose_file")
failed=0

check() {
  local name="$1" service="$2" code="$3" status
  printf '\n--- %s (%s) ---\n' "$name" "$service"
  "${compose[@]}" exec -T "$service" timeout 120s python -c "$code"
  status=$?
  if [[ $status -eq 0 ]]; then
    echo "PASS: $name"
  else
    echo "FAIL: $name (exit $status)"
    failed=$((failed + 1))
  fi
}

echo 'Native runtime diagnostic: synthetic inputs only; no participant media or external AI calls.'
"${compose[@]}" ps

check 'CPU features and runtime versions' media-processing-worker '
import importlib.metadata as md, platform
print("Architecture:", platform.machine())
flags = set()
with open("/proc/cpuinfo", encoding="utf-8") as f:
    for line in f:
        if line.startswith("flags"):
            flags = set(line.split(":", 1)[1].split()); break
for flag in ("sse4_1", "sse4_2", "avx", "avx2", "fma"):
    print(flag + ": " + ("YES" if flag in flags else "NO"))
for name in ("numpy", "scipy", "opencv-contrib-python", "mediapipe", "torch", "onnxruntime", "opensmile", "pyarrow"):
    try: print(f"{name}: {md.version(name)}")
    except md.PackageNotFoundError: print(f"{name}: NOT INSTALLED")
'

check 'NumPy and SciPy operations' media-processing-worker '
import numpy as np
from scipy.spatial.transform import Rotation
assert np.isfinite(np.linalg.svd(np.eye(8))[1]).all()
assert np.isfinite(Rotation.from_euler("xyz", [0.1, 0.2, 0.3]).as_matrix()).all()
'

check 'OpenCV image operations' media-processing-worker '
import cv2
import numpy as np
frame = np.zeros((240, 320, 3), dtype=np.uint8)
assert cv2.resize(frame, (160, 120)).shape == (120, 160, 3)
assert cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).shape == frame.shape
'

check 'MediaPipe face model and inference' media-processing-worker '
import mediapipe as mp
import numpy as np
from app.nonverbal.mediapipe_extractor import create_face_landmarker
detector = create_face_landmarker(image_mode=True)
try:
    detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((240, 320, 3), dtype=np.uint8)))
finally:
    detector.close()
'

check 'CCDb-HG model and PyTorch inference' media-processing-worker '
import torch
from app.nonverbal.ccdbhg import load_default_bundle
_, _, model = load_default_bundle()
with torch.no_grad(): result = model(torch.zeros((1, 18, 31)))
assert result.shape == (1, 6) and torch.isfinite(result).all()
'

check 'FFmpeg synthetic video encode and decode' media-processing-worker '
import subprocess, tempfile
from pathlib import Path
with tempfile.TemporaryDirectory(prefix="native-diagnostic-") as directory:
    path = str(Path(directory) / "synthetic.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-t", "1", "-c:v", "mpeg4", path], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-"], check=True)
'

check 'OpenSMILE and Silero synthetic audio extraction' api '
from scripts.deployment.verify_deployment import verify_audio_runtime
result = verify_audio_runtime()
print("Feature frames:", result["feature_frames"], "VAD frames:", result["vad_frames"])
'

check 'Python dependency consistency' api '
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "check"], check=True)
'

printf '\nDiagnostic complete: %s failed check(s).\n' "$failed"
echo 'Passing synthetic checks does not establish real-interview, calibration, concurrency, or external-service compatibility.'
[[ $failed -eq 0 ]]
