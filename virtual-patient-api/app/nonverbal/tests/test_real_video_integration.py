from pathlib import Path
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from app.multimodal.schemas import UnavailableReason
from app.multimodal import pipeline as pipeline_module
from app.models.medical_interview import MediaAssetKind
from app.multimodal.tests.test_pipeline import (
    _FakeSession,
    _make_asset,
    _make_interview,
    _make_recording,
    _make_turn,
)
from app.nonverbal.gaze import create_tracker
from app.nonverbal.ccdbhg import analyze_nods
from app.nonverbal.mediapipe_extractor import create_face_landmarker
from app.nonverbal.preprocessing import preprocess_nonverbal_turn
from app.nonverbal.video_observations import (
    TurnWindow,
    build_turn_raw_features,
    extract_nonverbal_video_observations,
    segment_nonverbal_observations_by_turn,
)


FIXTURE = Path(__file__).with_name("fixtures") / "face.jpg"


def write_fixture_video(path: Path, *, frame_count: int = 3, fps: float = 5.0) -> None:
    frame = cv2.imread(str(FIXTURE))
    assert frame is not None
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps,
        (frame.shape[1], frame.shape[0]),
    )
    for _ in range(frame_count):
        writer.write(frame)
    writer.release()


class CountingLandmarker:
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = 0

    def detect_for_video(self, image, timestamp_ms):
        self.calls += 1
        return self.delegate.detect_for_video(image, timestamp_ms)


def test_real_video_single_pass_mediapipe_to_blazegaze_and_turn_features(tmp_path):
    video_path = tmp_path / "face.mp4"
    write_fixture_video(video_path, frame_count=35, fps=30.0)

    delegate = create_face_landmarker()
    landmarker = CountingLandmarker(delegate)
    tracker = create_tracker()
    assert not hasattr(tracker, "face_landmarker")
    try:
        observations = extract_nonverbal_video_observations(
            video_path, sample_fps=30.0, landmarker=landmarker, tracker=tracker
        )
    finally:
        delegate.close()

    assert observations
    assert landmarker.calls == len(observations)
    assert any(item.smile is not None for item in observations)
    valid_gaze = [item.gaze for item in observations if item.gaze.valid]
    assert valid_gaze
    assert all(np.isfinite([item.unclipped_x, item.unclipped_y]).all() for item in valid_gaze)

    nod_analysis = analyze_nods([item.shared for item in observations])
    assert nod_analysis.evaluated

    end_ms = observations[-1].shared.timestamp_ms + 1.0
    window = TurnWindow("turn-1", 0.0, end_ms, "student")
    segmented = segment_nonverbal_observations_by_turn(observations, [window])
    raw = build_turn_raw_features(
        segmented["turn-1"], window, sample_fps=30.0, nod_analysis=nod_analysis
    )
    assert raw.frame_timestamps_ms == [item.shared.timestamp_ms for item in observations]
    processed = preprocess_nonverbal_turn(raw, "speaking", baseline=None)
    assert processed.processed.smile_activity_ratio is not None
    assert processed.processed.nod_count is not None
    assert processed.processed.visual_alignment_ratio is None
    assert processed.reasons["visual_alignment_ratio"] == UnavailableReason.GAZE_CALIBRATION_PENDING


def test_product_pipeline_reads_stored_video_and_persists_nonverbal_features(tmp_path):
    video_path = tmp_path / "stored-student-video.mp4"
    write_fixture_video(video_path)
    recording = _make_recording()
    interview = _make_interview()
    turn = _make_turn("real-turn", "patient", 1, 0, 1000)
    video_asset = _make_asset(MediaAssetKind.STUDENT_VIDEO.value)
    session = _FakeSession(
        recording=recording,
        interview=interview,
        turns=[turn],
        assets=[video_asset],
    )
    storage = SimpleNamespace(resolve=lambda storage_key: video_path)

    with patch.object(pipeline_module, "SessionLocal", return_value=session), \
            patch.object(pipeline_module, "get_media_storage", return_value=storage), \
            patch.object(pipeline_module, "read_personal_baseline", return_value=None):
        asyncio.run(pipeline_module.process_multimodal_interview(interview.id, recording.id))

    persisted = turn.nonverbal_features
    assert persisted["raw"]["extractor"]["name"] == "mediapipe_blazegaze_ccdbhg"
    assert persisted["raw"]["gaze_observations"]
    assert persisted["processed"]["smile_activity_ratio"] is not None
    assert persisted["quality"]["feature_reasons"]["visual_alignment_ratio"] == "gaze_calibration_pending"
    assert persisted["base_labels"]["visual_orientation"]["visual_alignment_ratio"]["reason"] == "gaze_calibration_pending"
