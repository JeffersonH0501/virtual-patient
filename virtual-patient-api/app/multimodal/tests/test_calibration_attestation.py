"""Unsigned, cross-user and mixed calibration checkpoints cannot pass."""
import pytest
from fastapi import HTTPException
from app.multimodal.calibration_attestation import sign_checkpoint, verify_calibration_checkpoints


def tokens(user_id=7, resume_attempt_id=None):
    affine = [[1, 0, 0], [0, 1, 0]]
    stages = {
        "gaze": ({"passed": True, "profile": {"affine_matrix": affine, "gaze_source": "mediapipe_five_point_v1", "calibration_target_count": 5}}, {"gaze_source": "mediapipe_five_point_v1", "geometry": {"viewport_width": 1000, "viewport_height": 800}}),
        "camera": ({"passed": True, "camera_reference_center": [.5, .1], "camera_eye_reference": {"center": [0, 0], "radius": .01}, "neutral_head": {"neutral_head_yaw": 0, "neutral_head_pitch": 0, "neutral_head_roll": 0}}, {"gaze_source": "mediapipe_five_point_v1", "affine_matrix": affine, "geometry": {"viewport_width": 1000, "viewport_height": 800}, "geometry_stable": True}),
    }
    return {stage: sign_checkpoint(user_id, 42, stage, {**result, "capture_id": f"capture-{stage}"}, metadata, resume_attempt_id) for stage, (result, metadata) in stages.items()}


def test_verified_results_are_built_from_server_attestations():
    assert set(tokens()) == {"gaze", "camera"}
    result = verify_calibration_checkpoints(7, 42, tokens())
    assert set(result["personal_baseline"]) == {"neutral_head_yaw", "neutral_head_pitch", "neutral_head_roll", "neutral_gaze_yaw", "neutral_gaze_pitch"}
    assert result["personal_baseline"]["neutral_head_yaw"] == 0
    assert result["profile"]["capture_geometry"]["viewport_width"] == 1000
    assert result["capture_ids"] == {"gaze": "capture-gaze", "camera": "capture-camera"}


@pytest.mark.parametrize("invalid", [{}, {"gaze": "forged"}, tokens(8)])
def test_missing_forged_or_other_user_checkpoints_are_rejected(invalid):
    with pytest.raises(HTTPException) as failure:
        verify_calibration_checkpoints(7, 42, invalid)
    assert failure.value.status_code == 422


def test_checkpoints_cannot_be_reused_for_another_interview():
    with pytest.raises(HTTPException) as failure:
        verify_calibration_checkpoints(7, 43, tokens())
    assert failure.value.status_code == 422


def test_recalibration_is_bound_to_one_authorized_resume_attempt():
    assert verify_calibration_checkpoints(7, 42, tokens(resume_attempt_id="attempt-one"), "attempt-one")["status"] == "passed"
    for signed, attempt in ((tokens(), "attempt-one"), (tokens(resume_attempt_id="attempt-one"), None),
                            (tokens(resume_attempt_id="attempt-one"), "attempt-two")):
        with pytest.raises(HTTPException) as failure:
            verify_calibration_checkpoints(7, 42, signed, attempt)
        assert failure.value.status_code == 422


def test_expired_checkpoint_requests_recalibration(monkeypatch):
    from jose.exceptions import ExpiredSignatureError

    signed = tokens()

    def decode_expired(*args, **kwargs):
        raise ExpiredSignatureError("Expired")

    monkeypatch.setattr("app.multimodal.calibration_attestation.jwt.decode", decode_expired)
    with pytest.raises(HTTPException) as failure:
        verify_calibration_checkpoints(7, 42, signed)
    assert failure.value.status_code == 410


def test_camera_checkpoint_must_match_gaze_geometry():
    from jose import jwt
    from app.core.config import settings
    signed = tokens()
    camera = jwt.decode(signed['camera'], settings.secret_key, algorithms=['HS256'], audience='calibration-checkpoint')
    camera['metadata']['geometry']['viewport_width'] = 800
    signed['camera'] = sign_checkpoint(7, 42, 'camera', camera['result'], camera['metadata'])
    with pytest.raises(HTTPException) as failure:
        verify_calibration_checkpoints(7, 42, signed)
    assert failure.value.status_code == 422


def test_iris_checkpoints_require_matching_source_and_merge_enrolled_framing():
    from jose import jwt
    from app.core.config import settings
    signed = tokens()
    gaze, camera = [jwt.decode(signed[stage], settings.secret_key, algorithms=['HS256'],
                               audience='calibration-checkpoint') for stage in ('gaze', 'camera')]
    bounds = [[0] * 5, [.1] * 5]
    gaze['result']['profile'].update(gaze_source='mediapipe_iris_v1', iris_geometry_bounds=bounds)
    signed['gaze'] = sign_checkpoint(7, 42, 'gaze', gaze['result'], gaze['metadata'])
    with pytest.raises(HTTPException) as failure:
        verify_calibration_checkpoints(7, 42, signed)
    assert failure.value.status_code == 422
    camera['metadata'].update(gaze_source='mediapipe_iris_v1', iris_geometry_bounds=bounds)
    camera['result']['iris_geometry_bounds'] = [[-.1] * 5, [.2] * 5]
    signed['camera'] = sign_checkpoint(7, 42, 'camera', camera['result'], camera['metadata'])
    with pytest.raises(HTTPException):
        verify_calibration_checkpoints(7, 42, signed)
