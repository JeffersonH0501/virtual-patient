"""Extract segment-local media with its own calibration, keeping global turn IDs."""

from types import SimpleNamespace

from app.multimodal import pipeline
from app.multimodal.calibration import read_calibration_profile
from app.nonverbal.ccdbhg import NodAnalysis


def test_missing_previous_media_does_not_shift_new_segment_windows_or_calibration(monkeypatch):
    first = SimpleNamespace(id="first", offset_ms=0, duration_ms=60_000, capture_config={},
                            calibration={"profile": {"affine_matrix": [[1, 0, 0], [0, 1, 0]]}})
    roi = [{"timestampMs": 0, "xNormalized": .1, "yNormalized": .1, "widthNormalized": .5, "heightNormalized": .5}]
    second = SimpleNamespace(id="second", offset_ms=60_000, duration_ms=10_000,
                             capture_config={"patientRoiSnapshots": roi},
                             calibration={"profile": {"gaze_source": "mediapipe_five_point_v1", "affine_matrix": [[2, 0, 0], [0, 2, 0]]}})
    turns = [SimpleNamespace(id="old-turn", segment_id="first", start_ms=0, end_ms=60_000,
                              speaker="student", transcript="Preserved old text"),
             SimpleNamespace(id="new-turn", segment_id="second", start_ms=60_000, end_ms=70_000,
                              speaker="student", transcript="New text")]
    groups = pipeline._turns_by_segment([first, second], turns)
    assert [turn.id for turn in groups["first"]] == ["old-turn"]
    assert [turn.id for turn in groups["second"]] == ["new-turn"]
    recording = SimpleNamespace(id="recording", capture_config={})
    monkeypatch.setattr(pipeline, "_set_stage", lambda *args: None)
    monkeypatch.setattr(pipeline, "get_media_storage", lambda: SimpleNamespace(resolve=lambda key: key))
    monkeypatch.setattr(pipeline, "_ready_asset", lambda db, recording_id, kind, segment_id:
                        SimpleNamespace(storage_key=kind) if segment_id == "second" else None)
    audio_windows, video_windows = [], []
    monkeypatch.setattr(pipeline, "analyze_student_turns", lambda path, windows:
                        audio_windows.extend(windows) or {"new-turn": object()})
    monkeypatch.setattr(pipeline, "extract_nonverbal_video_observations_parallel", lambda *args, **kwargs: [])
    monkeypatch.setattr(pipeline, "analyze_nods", lambda observations: NodAnalysis((), False, "no-events"))
    monkeypatch.setattr(pipeline, "segment_nonverbal_observations_by_turn", lambda observations, windows:
                        video_windows.extend(windows) or {"new-turn": []})
    def build(observations, window, **kwargs):
        assert kwargs["calibration_profile"] == second.calibration["profile"]
        assert kwargs["patient_roi_snapshots"] == roi
        assert kwargs["roi_duration_ms"] == 10_000
        return SimpleNamespace(extractor={})
    monkeypatch.setattr(pipeline, "build_turn_raw_features", build)
    outcome = pipeline._OutcomeTracker()
    audio, video = {}, {}
    for segment in (first, second):
        audio.update(pipeline._extract_paraverbal(db=None, recording=recording, interview_id=1,
                     recording_id=recording.id, student_turns=groups[segment.id], outcome=outcome, segment=segment))
        raw, _ = pipeline._extract_nonverbal(db=None, recording=recording, interview_id=1,
                  recording_id=recording.id, turns=groups[segment.id], outcome=outcome, segment=segment,
                  use_full_video=True, calibration_profile=read_calibration_profile(None, segment=segment))
        video.update(raw)
    assert list(audio) == list(video) == ["new-turn"]
    assert [(window.start_ms, window.end_ms) for window in audio_windows] == [(0, 10_000)]
    assert [(window.start_ms, window.end_ms) for window in video_windows] == [(0, 10_000)]
    assert turns[0].transcript == "Preserved old text"
