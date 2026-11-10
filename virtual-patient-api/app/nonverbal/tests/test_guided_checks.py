import pytest
from pydantic import ValidationError
from app.models.calibration import GuidedCheckInterval
from app.nonverbal.guided_checks import analyze_guided_checks
from app.nonverbal.gaze import GazeObservation
from app.nonverbal.shared_observations import SharedFrameObservation
from app.nonverbal.smile import extract_smile
from app.nonverbal.video_observations import EnrichedFrameObservation


def observations(left=.1, right=.1, face=True):
    result = []
    for time in range(0, 2000, 100):
        shared = SharedFrameObservation(time, None, face,
            blendshapes={"mouthSmileLeft": left, "mouthSmileRight": right})
        result.append(EnrichedFrameObservation(shared, extract_smile(shared),
            GazeObservation(time, face, "identity_calibration", .5, .5)))
    return result


def interval(kind="smile_speech"):
    return GuidedCheckInterval(kind=kind, start_ms=0, observation_start_ms=250, end_ms=2000)


def test_speech_activity_is_reported_without_changing_the_smile_classifier():
    result = analyze_guided_checks(observations(.6, .1), [interval()], None)
    assert result["diagnostic_only"] is True
    assert result["prompt_labels_verified"] is False
    phase = result["phases"][0]
    assert phase["smile_activity_ratio"] == 1
    assert phase["mean_smile_activation"] == pytest.approx(.35)
    assert phase["samples"][0]["mouth_smile_left"] == .6
    assert phase["gaze_error_median"] is None


def test_missing_face_is_unavailable_not_a_negative_smile():
    result = analyze_guided_checks(observations(face=False), [interval()], None)
    phase = result["phases"][0]
    assert phase["smile_activity_ratio"] is None
    assert phase["status"] == "insufficient_signal"


def test_guided_gaze_without_calibration_is_unavailable():
    result = analyze_guided_checks(observations(), [interval("gaze_still")], None)
    phase = result["phases"][0]
    assert phase["gaze_error_median"] is None
    assert phase["gaze_valid_ratio"] is None
    assert phase["samples"][0]["timestamp_ms"] == 300


@pytest.mark.parametrize("changes", [{"end_ms": 100}, {"observation_start_ms": 2000}, {"kind": "unknown"}])
def test_guided_intervals_reject_invalid_windows_and_unknown_prompts(changes):
    with pytest.raises(ValidationError):
        GuidedCheckInterval.model_validate({**interval().model_dump(), **changes})


def guided_metadata():
    import json
    from app.models.calibration import GUIDED_CHECK_KINDS
    from app.multimodal.tests.test_calibration import _valid_metadata_json
    payload = json.loads(_valid_metadata_json())
    payload["guided_environment"] = {"device_type": "laptop", "camera_position": "top"}
    start = payload["camera_reference_end_ms"]
    payload["guided_checks"] = [dict(kind=kind, start_ms=start+i*2000,
        observation_start_ms=start+i*2000+250, end_ms=start+(i+1)*2000)
        for i,kind in enumerate(GUIDED_CHECK_KINDS)]
    return payload


def test_guided_protocol_requires_complete_ordered_nonoverlapping_conditions():
    from app.models.calibration import UnifiedCalibrationMetadata
    payload = guided_metadata()
    assert len(UnifiedCalibrationMetadata.model_validate(payload).guided_checks) == 12
    payload["guided_checks"][1]["start_ms"] -= 1000
    with pytest.raises(ValidationError):
        UnifiedCalibrationMetadata.model_validate(payload)
    payload = guided_metadata()
    payload["guided_checks"].reverse()
    with pytest.raises(ValidationError):
        UnifiedCalibrationMetadata.model_validate(payload)


def test_diagnostic_error_does_not_modify_the_accepted_profile():
    profile = {"affine_matrix": [[1,0,0],[0,1,0]], "gaze_source": "mediapipe_five_point_v1"}
    phase = analyze_guided_checks(observations(), [interval("gaze_turn")], profile)["phases"][0]
    assert phase["gaze_error_median"] is None
    assert phase["gaze_valid_ratio"] is None
    assert profile == {"affine_matrix": [[1,0,0],[0,1,0]], "gaze_source": "mediapipe_five_point_v1"}


def test_unified_diagnostics_use_the_accepted_camera_without_mutating_the_profile(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.models.calibration import UnifiedCalibrationMetadata
    from app.nonverbal import calibration_worker, video_observations, mediapipe_extractor, guided_checks
    metadata = UnifiedCalibrationMetadata.model_validate(guided_metadata())
    shared = SimpleNamespace(shared=SimpleNamespace(timestamp_ms=1000))
    extract = Mock(return_value=[shared])
    monkeypatch.setattr(video_observations, 'extract_nonverbal_video_observations', extract)
    monkeypatch.setattr(mediapipe_extractor, 'create_face_landmarker', lambda: SimpleNamespace(close=lambda: None))
    profile = {'affine_matrix': [[1,0,0],[0,1,0]], 'gaze_source': 'mediapipe_five_point_v1'}
    monkeypatch.setattr(calibration_worker, 'process_gaze', lambda *args, **kwargs: {'passed': True, 'profile': profile})
    monkeypatch.setattr(calibration_worker, 'process_camera', lambda *args, **kwargs: {'passed': True, 'camera_reference_center': [.2,.7]})
    analyze = Mock(return_value={'diagnostic_only': True})
    monkeypatch.setattr(guided_checks, 'analyze_guided_checks', analyze)
    result = calibration_worker.process_unified(None, metadata)
    assert result['passed'] is True
    extract.assert_called_once()
    assert analyze.call_args.args[2]['camera_reference_center'] == [.2,.7]
    assert 'camera_reference_center' not in profile


def test_nod_counts_are_compared_with_prompts_without_fabricating_verified_labels(monkeypatch):
    from app.nonverbal import guided_checks
    from app.nonverbal.ccdbhg import NodAnalysis, NodEvent
    events = tuple(NodEvent(time-50,time+50,time,.9) for time in (500,1000,1500))
    analysis = NodAnalysis(events, True, evaluated_timestamps_ms=tuple(range(250,2000,33)))
    monkeypatch.setattr(guided_checks, 'analyze_nods', lambda shared: analysis)
    phase = analyze_guided_checks(observations(), [interval('nod_three')], None)['phases'][0]
    assert phase['nod_count'] == 3 and phase['prompted_nod_count'] == 3
    assert phase['nod_count_difference'] == 0
    monkeypatch.setattr(guided_checks, 'analyze_nods', lambda shared: NodAnalysis((), False, 'insufficient_signal'))
    phase = analyze_guided_checks(observations(), [interval('nod_still')], None)['phases'][0]
    assert phase['nod_count'] is None and phase['prompted_nod_count'] == 0
    assert phase['nod_count_difference'] is None


def test_camera_target_uses_the_recorded_lens_reference_for_any_mount_position():
    profile = {'affine_matrix': [[1,0,0],[0,1,0]], 'camera_reference_center': [.2,.7]}
    phase = analyze_guided_checks(observations(), [interval('gaze_camera')], profile)['phases'][0]
    assert phase['target'] is None
    assert phase['gaze_error_median'] is None


def test_legacy_guided_protocol_remains_readable_and_device_context_is_explicit():
    from app.models.calibration import UnifiedCalibrationMetadata, GUIDED_CHECK_KINDS_V1
    payload = guided_metadata()
    payload['guided_checks'] = [item for item in payload['guided_checks'] if item['kind'] in GUIDED_CHECK_KINDS_V1]
    payload['guided_environment'] = {'device_type': 'tablet', 'camera_position': 'left'}
    with pytest.raises(ValidationError):
        UnifiedCalibrationMetadata.model_validate(payload)
    payload['guided_environment'] = {'device_type': 'laptop', 'camera_position': 'top'}
    with pytest.raises(ValidationError):
        UnifiedCalibrationMetadata.model_validate(payload)


def test_frame_geometry_does_not_overwrite_device_context_or_break_json_serialization(monkeypatch):
    import json
    import numpy as np
    from app.nonverbal import guided_checks
    monkeypatch.setattr(guided_checks, 'iris_geometry', lambda shared: np.asarray([0,0,.5,.5,.1]))
    geometry = {'orientation': 'portrait', 'video_width': 720, 'video_height': 1280}
    result = analyze_guided_checks(observations(), [interval()], None,
        environment={'device_type': 'tablet', 'camera_position': 'left'}, geometry=geometry)
    assert result['geometry'] == geometry
    assert json.loads(json.dumps(result))['environment']['camera_position'] == 'left'


def test_native_guided_diagnostics_have_real_windows_and_json_serializable_samples(tmp_path):
    import json
    from pathlib import Path
    import cv2
    from app.nonverbal.video_observations import extract_nonverbal_video_observations
    frame = cv2.imread(str(Path(__file__).with_name('fixtures') / 'face.jpg'))
    path = tmp_path / 'synthetic-guided.mp4'
    height, width = frame.shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 25, (width,height))
    try:
        for _ in range(76):
            writer.write(frame)
    finally:
        writer.release()
    shared = extract_nonverbal_video_observations(path)
    window = GuidedCheckInterval(kind='nod_still', start_ms=1000, observation_start_ms=1250, end_ms=3000)
    result = analyze_guided_checks(shared, [window], None,
        environment={'device_type': 'laptop', 'camera_position': 'top'},
        geometry={'orientation': 'landscape', 'video_width': width, 'video_height': height})
    phase = result['phases'][0]
    assert phase['nod_evaluable_windows'] > 0
    assert phase['nod_count'] is not None
    assert phase['smile_activity_ratio'] is not None
    assert json.loads(json.dumps(result))['geometry']['video_width'] == width
    assert result['decoded_video_dimensions'] == [{'width': width, 'height': height}]
