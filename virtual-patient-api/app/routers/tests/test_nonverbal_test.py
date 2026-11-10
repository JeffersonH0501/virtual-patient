"""The temporary nonverbal test must not create interview records."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.models.user import UserRole
from app.routers import calibration
from app.multimodal.tests.test_calibration import _valid_metadata_json


def client(role):
    app = FastAPI()
    app.include_router(calibration.router)
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id=7, role=role)
    return TestClient(app)


def upload(api, metadata):
    return api.post('/calibration/nonverbal-test', data={
        'stage': 'unified', 'attempt_id': '12345678-1234-1234-1234-123456789012',
        'duration_ms': str(metadata['camera_reference_end_ms']), 'metadata_json': json.dumps(metadata),
    }, files={'media': ('capture.webm', b'video', 'video/webm')})


def test_test_requires_superuser():
    response = upload(client(UserRole.STUDENT), json.loads(_valid_metadata_json()))
    assert response.status_code == 403


def test_test_uses_temporary_file_and_signed_checkpoints(monkeypatch):
    metadata = json.loads(_valid_metadata_json())
    matrix = [[1, 0, 0], [0, 1, 0]]
    from app.models.calibration import CalibrationGeometry
    geometry = CalibrationGeometry.model_validate(metadata['geometry']).model_dump(mode='json')
    gaze = {'passed': True, 'profile': {'affine_matrix': matrix,
        'gaze_source': 'mediapipe_five_point_v1', 'calibration_target_count': 5}}
    camera = {'passed': True, 'camera_reference_center': [.5, .1],
        'camera_eye_reference': {'center': [0, 0], 'radius': .01},
        'neutral_head': {'neutral_head_yaw': 0, 'neutral_head_pitch': 0, 'neutral_head_roll': 0}}
    seen = []
    async def worker(path, parsed, stage):
        seen.append(path)
        assert path.read_bytes() == b'video'
        assert not parsed.experimental_quality_bypass
        return {'passed': True, 'failed_stage': None, 'gaze': gaze, 'camera': camera,
            'camera_metadata': {'affine_matrix': matrix, 'geometry': geometry,
                'geometry_stable': True, 'gaze_source': 'mediapipe_five_point_v1'}}, .1
    monkeypatch.setattr(calibration, '_run_timed_worker', AsyncMock(side_effect=worker))
    response = upload(client(UserRole.SUPERUSER), metadata)
    assert response.status_code == 200
    assert response.json()['result']['checkpoints']['camera']['attestation']
    assert not seen[0].exists()


def test_guided_capture_requires_checkpoints_for_the_same_attempt(monkeypatch):
    from app.multimodal.calibration_attestation import sign_checkpoint
    from app.nonverbal.tests.test_guided_checks import guided_metadata
    from app.models.calibration import CalibrationGeometry

    metadata = guided_metadata()
    matrix = [[1, 0, 0], [0, 1, 0]]
    geometry = CalibrationGeometry.model_validate(metadata['geometry']).model_dump(mode='json')
    attempt = '12345678-1234-1234-1234-123456789012'
    gaze = {'passed': True, 'profile': {'affine_matrix': matrix,
        'gaze_source': 'mediapipe_five_point_v1', 'calibration_target_count': 5}}
    camera = {'passed': True, 'camera_reference_center': [.5, .1],
        'camera_eye_reference': {'center': [0, 0], 'radius': .01},
        'neutral_head': {'neutral_head_yaw': 0, 'neutral_head_pitch': 0, 'neutral_head_roll': 0}}
    gaze_metadata = {'geometry': geometry, 'gaze_source': 'mediapipe_five_point_v1'}
    camera_metadata = {**gaze_metadata, 'geometry_stable': True, 'affine_matrix': matrix}
    guided = {'geometry': geometry, 'geometry_stable': True,
        'guided_checks': metadata['guided_checks'], 'guided_environment': metadata['guided_environment'],
        'attestations': {'gaze': sign_checkpoint(7, 0, 'gaze', gaze, gaze_metadata, attempt),
                         'camera': sign_checkpoint(7, 0, 'camera', camera, camera_metadata, attempt)}}
    worker = AsyncMock(return_value=({'passed': True, 'guided_checks': {'phases': []}}, .1))
    monkeypatch.setattr(calibration, '_run_timed_worker', worker)
    def request(attempt_id):
        return client(UserRole.SUPERUSER).post('/calibration/nonverbal-test', data={
            'stage': 'guided', 'attempt_id': attempt_id,
            'duration_ms': str(guided['guided_checks'][-1]['end_ms']),
            'metadata_json': json.dumps(guided),
        }, files={'media': ('guided.webm', b'video', 'video/webm')})
    assert request('99999999-1234-1234-1234-123456789012').status_code == 422
    response = request(attempt)
    assert response.status_code == 200
    assert response.json()['result']['guided_checks']['processing_time_seconds'] == .1
    assert worker.call_args.args[1].profile['gaze_source'] == 'mediapipe_five_point_v1'
    assert not worker.call_args.args[0].exists()


def test_nod_and_smile_test_does_not_require_gaze_calibration(monkeypatch):
    from app.nonverbal.tests.test_guided_checks import guided_metadata
    metadata = guided_metadata()
    guided = {'geometry': metadata['geometry'], 'geometry_stable': True,
        'guided_checks': metadata['guided_checks'][5:], 'guided_environment': metadata['guided_environment'],
        'attestations': {}, 'profile': {'untrusted': True}}
    worker = AsyncMock(return_value=({'passed': True, 'guided_checks': {'phases': []}}, .1))
    monkeypatch.setattr(calibration, '_run_timed_worker', worker)
    response = client(UserRole.SUPERUSER).post('/calibration/nonverbal-test', data={
        'stage': 'guided', 'attempt_id': '12345678-1234-1234-1234-123456789012',
        'duration_ms': str(guided['guided_checks'][-1]['end_ms']), 'metadata_json': json.dumps(guided),
    }, files={'media': ('guided.webm', b'video', 'video/webm')})
    assert response.status_code == 200
    assert worker.call_args.args[1].profile == {}


def test_live_gaze_requires_matching_signed_calibration_and_discards_frame(monkeypatch):
    from app.multimodal.calibration_attestation import sign_checkpoint
    from app.models.calibration import CalibrationGeometry
    metadata = json.loads(_valid_metadata_json())
    geometry = CalibrationGeometry.model_validate(metadata['geometry']).model_dump(mode='json')
    matrix = [[1, 0, 0], [0, 1, 0]]
    attempt = '12345678-1234-1234-1234-123456789012'
    gaze = {'passed': True, 'profile': {'affine_matrix': matrix, 'gaze_source': 'mediapipe_five_point_v1', 'calibration_target_count': 5}}
    camera = {'passed': True, 'camera_reference_center': [.5, .1], 'camera_eye_reference': {'center': [0, 0], 'radius': .01},
        'neutral_head': {'neutral_head_yaw': 0, 'neutral_head_pitch': 0, 'neutral_head_roll': 0}}
    gaze_metadata = {'geometry': geometry, 'gaze_source': 'mediapipe_five_point_v1'}
    camera_metadata = {**gaze_metadata, 'geometry_stable': True, 'affine_matrix': matrix}
    tokens = {'gaze': sign_checkpoint(7, 0, 'gaze', gaze, gaze_metadata, attempt),
              'camera': sign_checkpoint(7, 0, 'camera', camera, camera_metadata, attempt)}
    paths = []
    async def process(path, parsed, stage):
        paths.append(path)
        assert path.read_bytes() == b'frame'
        assert parsed.profile['capture_geometry'] == geometry
        assert stage == 'live-gaze'
        return {'state': 'inside'}
    monkeypatch.setattr(calibration, 'process_calibration_video', process)
    def request(role, current_geometry, current_attempt=attempt):
        return client(role).post('/calibration/gaze-test/frame', data={'attempt_id': current_attempt,
            'attestations_json': json.dumps(tokens), 'geometry_json': json.dumps(current_geometry)},
            files={'media': ('frame.jpg', b'frame', 'image/jpeg')})
    assert request(UserRole.STUDENT, geometry).status_code == 403
    assert request(UserRole.SUPERUSER, {**geometry, 'viewport_width': 1}).status_code == 409
    assert request(UserRole.SUPERUSER, geometry, '99999999-1234-1234-1234-123456789012').status_code == 422
    response = request(UserRole.SUPERUSER, geometry)
    assert response.status_code == 200 and response.json() == {'state': 'inside'}
    assert not paths[0].exists()
