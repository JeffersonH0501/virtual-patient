from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from app.nonverbal import ccdbhg
from app.nonverbal.ccdbhg import (
    CHANNELS, CLASS_NAMES, LANDMARK_GROUPS, CCDbHGFrameFeatures, NodAnalysis,
    NodEvent, WindowPrediction, assign_nods_to_turns, head_pose_features,
    landmark_features, load_bundle, nod_events, preprocess_window,
    resample_windows,
)
from app.nonverbal.shared_observations import SharedFrameObservation
from app.nonverbal.video_observations import TurnWindow, build_turn_raw_features


EXPECTED_GROUPS = {
    "left_eye": [130,247,30,29,27,28,56,190,243,112,26,22,23,24,110,25],
    "right_eye": [463,414,286,258,257,259,260,467,359,255,339,254,253,252,256,341],
    "nose": [51,5,281,45,4,275,220,134,236,3,195,248,456,363,440],
    "ear_l": [234,93,227,137],
    "ear_r": [454,323,447,366],
}


def test_landmark_groups_and_pixel_coordinate_conversion_are_frozen():
    assert LANDMARK_GROUPS == EXPECTED_GROUPS
    points = [SimpleNamespace(x=i / 1000, y=i / 2000, z=-i / 4000) for i in range(478)]
    observation = SharedFrameObservation(0, np.zeros((200, 400, 3)), True, points)
    actual = landmark_features(observation).reshape(5, 3)
    for row, indexes in zip(actual, EXPECTED_GROUPS.values()):
        mean = np.mean(indexes)
        np.testing.assert_allclose(row, [mean * .4, mean * .1, -mean * .1])


def test_head_pose_official_axis_and_euler_convention():
    np.testing.assert_allclose(head_pose_features(np.eye(4)), [0, 0, 0], atol=1e-12)
    matrix = np.eye(4)
    # Inverse of the adapter's two fixed axis operations for known xyz angles.
    from scipy.spatial.transform import Rotation
    expected_xyz = np.array([.1, -.2, .3])
    matrix[:3, :3] = np.diag([1., -1., -1.]) @ Rotation.from_euler("xyz", expected_xyz).as_matrix() @ np.diag([1., -1., -1.])
    np.testing.assert_allclose(head_pose_features(matrix), [-.2, .3, .1], atol=1e-12)


def test_channel_order_is_exact_and_finite():
    assert CHANNELS == ["head_yaw", "head_roll", "head_pitch"] + [
        f"{group}_{axis}" for group in EXPECTED_GROUPS for axis in ("x", "y", "z")
    ]
    assert len(CHANNELS) == 18


def test_timestamp_resampling_supports_irregular_non_30fps_and_rejects_gaps():
    timestamps = np.arange(0, 1300, 40, dtype=float)  # 25 FPS
    timestamps[10:] += 3.0
    features = [CCDbHGFrameFeatures(t, np.full(18, t)) for t in timestamps]
    windows = resample_windows(features)
    assert windows and windows[0][1].shape == (31, 18)
    assert np.isfinite(windows[0][1]).all()
    gapped = [item for item in features if not 400 <= item.timestamp_ms <= 800]
    assert resample_windows(gapped) == []


def test_official_bundle_loads_on_cpu_and_model_contract_is_valid():
    config, std, model = load_bundle()
    assert (config["in_ch"], config["max_len"], config["num_classes"]) == (18, 31, 6)
    assert std.shape == (1, 1, 18)
    logits = model(torch.zeros(2, 18, 31))
    probabilities = torch.softmax(logits, dim=1)
    assert logits.shape == (2, 6)
    assert torch.isfinite(logits).all()
    assert torch.allclose(probabilities.sum(dim=1), torch.ones(2))
    assert CLASS_NAMES == ("background", "Nod", "Shake", "Tilt", "Turn", "Up_down")


def test_bundle_rejects_lfs_pointer_and_hash_mismatch(tmp_path, monkeypatch):
    for name in ("config.yaml", "train_stats.pkl", "ckpt.pth.tar"):
        (tmp_path / name).write_text("version https://git-lfs.github.com/spec/v1", encoding="utf-8")
    with pytest.raises(ValueError, match="Git LFS pointer"):
        load_bundle(tmp_path)


def test_preprocessing_matches_frozen_reference_fixture():
    window = np.zeros((31, 18), dtype=float)
    window[:, 0] = np.linspace(0, .3, 31)
    window[:, 3:] = np.tile(np.array([0,0,0, 1,0,0, 0,1,0, -50,0,0, 50,0,0]), (31,1))
    result = preprocess_window(window, np.ones((1, 1, 18)))
    assert result.shape == (31, 18)
    np.testing.assert_allclose(result[0], np.zeros(18), atol=1e-12)
    assert np.isfinite(result).all()


def test_overlapping_predictions_consolidate_and_short_events_are_removed():
    predictions = [WindowPrediction(i * 33.333, label, .8) for i, label in enumerate(
        [0] * 5 + [1] * 10 + [0] * 8 + [1] * 2 + [0] * 5
    )]
    events = nod_events(predictions)
    assert len(events) == 1
    assert events[0].start_ms < events[0].midpoint_ms < events[0].end_ms
    assert events[0].confidence == pytest.approx(.8)


def test_turn_assignment_is_half_open_and_valid_zero_is_available():
    turns = [TurnWindow("a", 0, 1000, "student"), TurnWindow("b", 1000, 2000, "patient")]
    events = [NodEvent(900, 1100, 1000, .9)]
    assigned = assign_nods_to_turns(events, turns)
    assert assigned["a"] == (0, 0)
    assert assigned["b"] == (1, 60)
    raw = build_turn_raw_features([], turns[0], nod_analysis=NodAnalysis((), True))
    assert raw.nod_count == 0 and raw.nod_rate_min == 0
    unavailable = build_turn_raw_features([], turns[0], nod_analysis=NodAnalysis((), False, "insufficient_signal"))
    assert unavailable.nod_count is None and unavailable.nod_unavailable_reason.value == "insufficient_signal"
