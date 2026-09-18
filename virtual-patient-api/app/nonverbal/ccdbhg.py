"""Independent CCDb-HG cnn_lmk_hp adapter over shared MediaPipe observations."""

from __future__ import annotations

import hashlib
import pickle
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np
import torch
from scipy.spatial.transform import Rotation
from torch import nn

from app.nonverbal.shared_observations import SharedFrameObservation

BUNDLE = Path(__file__).with_name("models") / "ccdbhg_cnn_lmk_hp"
CHECKPOINT_SHA256 = "7f390f20fe02e1636cc18b7d120ab7f60c99e5c972b5953e6d064c47b495c556"
CONFIG_SHA256 = "50a53c77fb8fdac072bbbc13c876fa7694f3e6dfdf8a03b0f98d8570092bca0b"
TRAIN_STATS_SHA256 = "4495249e3f88f867c3f2f39e00027202abebc10926187f22c3e3efe5a718608e"

LANDMARK_GROUPS = {
    "left_eye": [130,247,30,29,27,28,56,190,243,112,26,22,23,24,110,25],
    "right_eye": [463,414,286,258,257,259,260,467,359,255,339,254,253,252,256,341],
    "nose": [51,5,281,45,4,275,220,134,236,3,195,248,456,363,440],
    "ear_l": [234,93,227,137],
    "ear_r": [454,323,447,366],
}
CHANNELS = ["head_yaw", "head_roll", "head_pitch"] + [
    f"{group}_{axis}" for group in LANDMARK_GROUPS for axis in ("x", "y", "z")
]
CLASS_NAMES = ("background", "Nod", "Shake", "Tilt", "Turn", "Up_down")
TARGET_STEP_MS = 1000.0 / 30.0
WINDOW_SAMPLES = 31
RELATIVE_LAG = 5


@dataclass(frozen=True)
class CCDbHGFrameFeatures:
    timestamp_ms: float
    values: np.ndarray


@dataclass(frozen=True)
class WindowPrediction:
    timestamp_ms: float
    class_id: int
    confidence: float


@dataclass(frozen=True)
class NodEvent:
    start_ms: float
    end_ms: float
    midpoint_ms: float
    confidence: float
    class_name: str = "nod"


@dataclass(frozen=True)
class NodAnalysis:
    events: tuple[NodEvent, ...]
    evaluated: bool
    reason: str | None = None


class CNNLmkHp(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        in_channels = 18
        for out_channels, kernel, dropout in zip((128,128,128), (8,5,3), (0.1,0.1,0.0)):
            layers.extend((nn.Conv1d(in_channels, out_channels, kernel, padding=kernel//2, bias=False), nn.ReLU(), nn.Dropout(dropout)))
            in_channels = out_channels
        self.model = nn.Sequential(*layers)
        self.head = nn.Linear(128, 6)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        encoded = self.model(inputs).mean(dim=2)
        return self.head(encoded)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_bundle(bundle: Path = BUNDLE) -> tuple[dict, np.ndarray, CNNLmkHp]:
    import yaml

    paths = {"config": bundle/"config.yaml", "stats": bundle/"train_stats.pkl", "checkpoint": bundle/"ckpt.pth.tar"}
    expected = {"config": CONFIG_SHA256, "stats": TRAIN_STATS_SHA256, "checkpoint": CHECKPOINT_SHA256}
    for key, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"Missing CCDb-HG {key}: {path}")
        if path.read_bytes().startswith(b"version https://git-lfs.github.com/spec"):
            raise ValueError(f"CCDb-HG {key} is a Git LFS pointer")
        if _sha256(path) != expected[key]:
            raise ValueError(f"CCDb-HG {key} SHA-256 mismatch")
    config = yaml.safe_load(paths["config"].read_text(encoding="utf-8"))
    required = {"in_ch":18, "max_len":31, "num_classes":6, "input_domain":["head_pose","landmarks"], "normalize_type":"head_size", "relative_method":"with_head_center", "transform_relative":5}
    for key, value in required.items():
        if config.get(key) != value:
            raise ValueError(f"Unsupported CCDb-HG config {key}={config.get(key)!r}")
    with paths["stats"].open("rb") as handle:
        stats = pickle.load(handle)
    std = np.asarray(stats.get("std"), dtype=np.float64)
    if stats.get("mean") is not None or std.shape != (1,1,18) or not np.isfinite(std).all() or np.any(std <= 0):
        raise ValueError("Invalid CCDb-HG training statistics")
    checkpoint = torch.load(paths["checkpoint"], map_location="cpu", weights_only=False)
    state = checkpoint.get("model")
    if not isinstance(state, dict):
        raise ValueError("Invalid CCDb-HG checkpoint state")
    model = CNNLmkHp()
    model.load_state_dict(state, strict=True)
    model.eval()
    return config, std, model


@lru_cache(maxsize=1)
def load_default_bundle() -> tuple[dict, np.ndarray, CNNLmkHp]:
    """Load and verify the pinned CPU bundle once per API process."""
    return load_bundle(BUNDLE)


def landmark_features(observation: SharedFrameObservation) -> np.ndarray:
    if observation.frame_width is not None and observation.frame_height is not None:
        width, height = observation.frame_width, observation.frame_height
    elif observation.frame is not None:
        height, width = observation.frame.shape[:2]
    else:
        raise ValueError("Frame geometry is unavailable for CCDb-HG landmarks")
    points = np.asarray([[p.x*width, p.y*height, p.z*width] for p in observation.landmarks], dtype=np.float64)
    return np.concatenate([points[indexes].mean(axis=0) for indexes in LANDMARK_GROUPS.values()])


def head_pose_features(matrix: np.ndarray) -> np.ndarray:
    transformed = np.asarray(matrix, dtype=np.float64).reshape(4,4).copy()
    transformed[1:3, :] *= -1
    rotation_x_pi = np.diag([1.0, -1.0, -1.0])
    pitch, yaw, roll = Rotation.from_matrix(transformed[:3,:3] @ rotation_x_pi).as_euler("xyz", degrees=False)
    return np.asarray([yaw, roll, pitch])


def frame_features(observations: Sequence[SharedFrameObservation]) -> list[CCDbHGFrameFeatures]:
    return [CCDbHGFrameFeatures(item.timestamp_ms, np.concatenate((head_pose_features(item.facial_transformation_matrix), landmark_features(item)))) for item in observations if item.face_valid and item.landmarks is not None and item.facial_transformation_matrix is not None]


def resample_windows(features: Sequence[CCDbHGFrameFeatures], *, max_gap_ms: float = 100.0) -> list[tuple[float, np.ndarray]]:
    if len(features) < 2:
        return []
    times = np.asarray([item.timestamp_ms for item in features], dtype=float)
    values = np.asarray([item.values for item in features], dtype=float)
    windows = []
    end = times[0] + TARGET_STEP_MS * (WINDOW_SAMPLES - 1)
    while end <= times[-1] + 1e-6:
        targets = end - TARGET_STEP_MS * np.arange(WINDOW_SAMPLES - 1, -1, -1)
        indexes = np.searchsorted(times, targets)
        valid = True
        for target, index in zip(targets, indexes):
            left = max(index - 1, 0); right = min(index, len(times)-1)
            if min(abs(target-times[left]), abs(times[right]-target)) > max_gap_ms:
                valid = False; break
        if valid:
            windows.append((float(end), np.column_stack([np.interp(targets, times, values[:,channel]) for channel in range(18)])))
        end += TARGET_STEP_MS
    return windows


def _rotation_matrices(head_pose: np.ndarray) -> np.ndarray:
    return Rotation.from_euler("xyz", head_pose[:, [2,0,1]], degrees=False).as_matrix()


def preprocess_window(window: np.ndarray, std: np.ndarray) -> np.ndarray:
    head = window[:, :3]
    landmarks = window[:, 3:].reshape(WINDOW_SAMPLES, 5, 3)
    head_size = np.linalg.norm(landmarks[:,3]-landmarks[:,4], axis=1).mean()/100.0
    if not np.isfinite(head_size) or head_size <= 0:
        raise ValueError("Invalid head size")
    landmarks = landmarks / head_size
    rotations = _rotation_matrices(head)
    prepend = np.repeat(rotations[:1], RELATIVE_LAG, axis=0)
    relative_rot = np.transpose(np.concatenate((prepend, rotations)), (0,2,1))[RELATIVE_LAG:] @ np.concatenate((prepend, rotations))[:-RELATIVE_LAG]
    relative_head_xyz = Rotation.from_matrix(relative_rot).as_euler("xyz", degrees=False)
    relative_head = relative_head_xyz[:, [1,2,0]]
    average_rotation = Rotation.from_euler("xyz", head.mean(axis=0)[[2,0,1]], degrees=False).as_matrix()
    center = landmarks.mean(axis=1, keepdims=True)
    invariant = ((average_rotation.T @ (landmarks-center).transpose(0,2,1)).transpose(0,2,1) + center).reshape(WINDOW_SAMPLES,15)
    prepend_landmarks = np.repeat(invariant[:1], RELATIVE_LAG, axis=0)
    relative_landmarks = np.concatenate((prepend_landmarks,invariant))[RELATIVE_LAG:] - np.concatenate((prepend_landmarks,invariant))[:-RELATIVE_LAG]
    model_input = np.concatenate((relative_head, relative_landmarks), axis=1) / std.reshape(1,18)
    if model_input.shape != (31,18) or not np.isfinite(model_input).all():
        raise ValueError("Invalid CCDb-HG model input")
    return model_input


def infer(features: Sequence[CCDbHGFrameFeatures], std: np.ndarray, model: CNNLmkHp) -> list[WindowPrediction]:
    output = []
    for timestamp, window in resample_windows(features):
        tensor = torch.from_numpy(preprocess_window(window,std).T[None]).float()
        with torch.no_grad():
            probabilities = torch.softmax(model(tensor), dim=1)[0]
        class_id = int(torch.argmax(probabilities))
        output.append(WindowPrediction(timestamp, class_id, float(probabilities[class_id])))
    return output


def analyze_nods(observations: Sequence[SharedFrameObservation]) -> NodAnalysis:
    """Run CCDb-HG over already-decoded shared observations."""
    features = frame_features(observations)
    if not resample_windows(features):
        return NodAnalysis((), False, "insufficient_signal")
    _, std, model = load_default_bundle()
    predictions = infer(features, std, model)
    if not predictions:
        return NodAnalysis((), False, "insufficient_signal")
    return NodAnalysis(tuple(nod_events(predictions)), True)


def _smooth(labels: list[int], margin: int = 3) -> list[int]:
    if len(labels) <= margin*2:
        return labels
    padded = [0]*margin + labels + [0]*margin
    return [max(set(padded[i-margin:i+margin+1]), key=padded[i-margin:i+margin+1].count) for i in range(margin, len(padded)-margin)]


def nod_events(predictions: Sequence[WindowPrediction], *, short_event_margin: int = 6) -> list[NodEvent]:
    labels = _smooth([item.class_id for item in predictions])
    events: list[NodEvent] = []
    start = None
    for index in range(len(labels)+1):
        label = labels[index] if index < len(labels) else 0
        if label == 1 and start is None:
            start = index
        elif label != 1 and start is not None:
            end = index-1
            if end-start+1 > short_event_margin:
                subset = predictions[start:end+1]
                start_ms, end_ms = subset[0].timestamp_ms, subset[-1].timestamp_ms
                events.append(NodEvent(start_ms,end_ms,(start_ms+end_ms)/2,float(np.mean([item.confidence for item in subset]))))
            start = None
    return events


def assign_nods_to_turns(events: Sequence[NodEvent], windows: Sequence[object]) -> dict[str, tuple[int,float]]:
    result = {}
    for window in windows:
        count = sum(window.start_ms <= event.midpoint_ms < window.end_ms for event in events)
        duration_minutes = (window.end_ms-window.start_ms)/60000.0
        result[window.turn_id] = (count, count/duration_minutes if duration_minutes > 0 else 0.0)
    return result
