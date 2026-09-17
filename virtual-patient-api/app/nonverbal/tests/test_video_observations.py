from types import SimpleNamespace

import numpy as np

from app.nonverbal.gaze import GazeObservation
from app.nonverbal.shared_observations import SharedFrameObservation
from app.nonverbal.smile import SmileObservation
from app.nonverbal.video_observations import (
    EnrichedFrameObservation,
    TurnWindow,
    build_turn_raw_features,
    extract_nonverbal_video_observations,
    segment_nonverbal_observations_by_turn,
)


def enriched(timestamp, *, face=True, smile=True, gaze=True):
    shared = SharedFrameObservation(timestamp, np.zeros((2, 2, 3)), face)
    smile_value = SmileObservation(timestamp, 0.5, 0.2, 0.35, True) if smile else None
    gaze_value = GazeObservation(timestamp, gaze, "identity_calibration" if gaze else "inference_failed", 0.1 if gaze else None, 0.2 if gaze else None, 0.1 if gaze else None, 0.2 if gaze else None)
    return EnrichedFrameObservation(shared, smile_value, gaze_value)


def test_half_open_segmentation_preserves_absolute_timestamps():
    observations = [enriched(0), enriched(999), enriched(1000), enriched(1999)]
    windows = [TurnWindow("a", 0, 1000, "student"), TurnWindow("b", 1000, 2000, "patient")]
    segmented = segment_nonverbal_observations_by_turn(observations, windows)
    assert [item.shared.timestamp_ms for item in segmented["a"]] == [0, 999]
    assert [item.shared.timestamp_ms for item in segmented["b"]] == [1000, 1999]


def test_partial_feature_availability_is_preserved_per_turn():
    window = TurnWindow("a", 0, 1000, "student")
    raw = build_turn_raw_features(
        [enriched(10, smile=False, gaze=True), enriched(20, smile=True, gaze=False)],
        window,
    )
    assert raw.frame_timestamps_ms == [10, 20]
    assert len(raw.au12_samples) == 1
    assert raw.gaze_observations[0]["valid"] is True
    assert raw.gaze_observations[1]["valid"] is False


def test_full_video_fans_out_each_shared_observation_without_second_detector(monkeypatch):
    shared = [
        SharedFrameObservation(0, np.zeros((2, 2, 3)), False),
        SharedFrameObservation(100, np.zeros((2, 2, 3)), True, [], {}),
    ]
    calls = {"video": 0, "smile": 0, "gaze": 0}

    def fake_video(*args, **kwargs):
        calls["video"] += 1
        yield from shared

    monkeypatch.setattr("app.nonverbal.video_observations.extract_video", fake_video)
    monkeypatch.setattr("app.nonverbal.video_observations.extract_smile", lambda item: calls.__setitem__("smile", calls["smile"] + 1))
    monkeypatch.setattr("app.nonverbal.video_observations.extract_gaze", lambda item, tracker: (calls.__setitem__("gaze", calls["gaze"] + 1) or GazeObservation(item.timestamp_ms, False, "test")))
    result = extract_nonverbal_video_observations(SimpleNamespace(), tracker=object())
    assert len(result) == 2
    assert calls == {"video": 1, "smile": 2, "gaze": 2}
