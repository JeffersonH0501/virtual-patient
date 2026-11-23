"""Segment boundaries survive reload without admitting writes from an old capture."""

from datetime import datetime, timedelta, timezone
import json
import subprocess
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.medical_interview import (
    InterviewMessageDB, InterviewRecordingDB, InterviewRecordingSegmentDB,
    InterviewStatus, InterviewTurnDB, MedicalInterviewDB,
)
from app.routers import recording_segments as segments
from app.routers import interview_hypotheses
from app.routers.tests.test_lifecycle_integrity import lifecycle_api, exchange_agent


@pytest.fixture
def capture(lifecycle_api):
    state = lifecycle_api
    state.client.app.include_router(segments.router)
    state.client.app.include_router(interview_hypotheses.router)
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.interview_metadata = {**interview.interview_metadata, 'recording_transport': 'per_turn_v1'}
        db.commit()
    assert state.client.post(f"/medical-interviews/{state.id}/start").status_code == 200
    state.root = f"/medical-interviews/{state.id}/recording"
    state.geometry = {"viewport_width": 1000, "viewport_height": 700}
    state.segment_id = str(uuid4())
    state.client.headers["X-Capture-Segment"] = state.segment_id
    response = state.client.post(state.root + "/segments", json={
        "request_id": state.segment_id, "capture_config": {"geometry": state.geometry},
    })
    assert response.status_code == 200, response.text
    state.start_payload = {"request_id": state.segment_id, "capture_config": {"geometry": state.geometry}}
    state.greeting_id = state.client.get(f"/medical-interviews/{state.id}/messages").json()["messages"][0]["id"]
    return state


def test_attempt_start_is_idempotent_and_rejects_changed_request_content(capture):
    state = capture
    response = state.client.post(state.root + '/segments', json=state.start_payload)
    assert response.status_code == 200
    assert response.json()['segment_id'] == state.segment_id
    changed = {**state.start_payload, 'capture_config': {'geometry': {'viewport_width': 900}}}
    assert state.client.post(state.root + '/segments', json=changed).status_code == 409


def test_without_gaze_authorization_allows_start_and_retains_geometry_checks(lifecycle_api):
    from app.multimodal.calibration import read_calibration_profile
    state = lifecycle_api
    state.client.app.include_router(segments.router)
    geometry = {'viewport_width': 1000, 'viewport_height': 700}
    calibration = {'status': 'without_gaze', 'version': 'multimodal_without_gaze_v1',
                   'failed_capture_ids': ['first', 'second'], 'profile': {'capture_geometry': geometry}}
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.interview_metadata = {'recording_transport': 'per_turn_v1', 'calibration': calibration}
        db.commit()
    assert state.client.post(f'/medical-interviews/{state.id}/start').status_code == 200
    endpoint = f'/medical-interviews/{state.id}/recording/segments'
    payload = {'request_id': str(uuid4()), 'capture_config': {'geometry': {'viewport_width': 900}}}
    assert state.client.post(endpoint, json=payload).status_code == 409
    payload['capture_config']['geometry'] = geometry
    response = state.client.post(endpoint, json=payload)
    assert response.status_code == 200, response.text
    with Session(state.engine) as db:
        segment = db.query(InterviewRecordingSegmentDB).one()
        assert segment.calibration == calibration
        assert read_calibration_profile(db.get(MedicalInterviewDB, state.id), segment=segment) is None


def test_resume_without_gaze_requires_its_own_failures_and_does_not_reuse_old_profile(capture, monkeypatch):
    from unittest.mock import AsyncMock
    from app.routers import calibration
    from app.routers.tests.test_calibration_reference import upload
    from app.multimodal.tests.test_calibration import _valid_metadata_json
    from app.multimodal.calibration import read_calibration_profile
    state = capture
    state.client.app.include_router(calibration.router)
    monkeypatch.setattr('app.media.calibration.get_media_storage', lambda: state.storage)
    monkeypatch.setattr(calibration, '_run_timed_worker', AsyncMock(return_value=(
        {'passed': False, 'failed_stage': 'gaze', 'gaze': {'passed': False, 'failure_reason': 'median_error'}}, .01)))
    key = str(uuid4())
    assert state.client.post(state.root + '/resume', json={'request_id': key}).status_code == 200
    geometry = json.loads(_valid_metadata_json())['geometry']
    endpoint = f'/calibration/without-gaze/{state.id}'
    payload = {'geometry': geometry, 'resume_attempt_id': key}
    assert state.client.post(endpoint, json=payload).status_code == 409
    for index in range(2):
        response = upload(state.client, state.id, content=f'synthetic resume {index}'.encode(),
                          stage='unified', resume_attempt_id=key)
        assert response.status_code == 200, response.text
        assert response.json()['can_continue_without_gaze'] is (index == 1)
    assert state.client.post(endpoint, json={**payload, 'resume_attempt_id': str(uuid4())}).status_code == 409
    assert state.client.post(endpoint, json=payload).status_code == 200
    response = state.client.post(state.root + '/segments', json={
        'request_id': str(uuid4()), 'resume_attempt_id': key, 'capture_config': {'geometry': geometry}})
    assert response.status_code == 200, response.text
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        assert interview.interview_metadata['calibration']['status'] == 'passed'
        saved = db.query(InterviewRecordingSegmentDB).order_by(InterviewRecordingSegmentDB.sequence).all()
        assert saved[0].calibration['status'] == 'passed'
        assert saved[1].calibration['status'] == 'without_gaze'
        assert read_calibration_profile(interview, segment=saved[1]) is None


def _segment_count(state):
    with Session(state.engine) as db:
        return db.query(InterviewRecordingSegmentDB).count()


def test_repeated_start_replays_confirm_the_active_segment_without_creating_another(capture):
    """A client that lost its connection replays the start request to confirm it may keep writing."""
    state = capture
    for _ in range(5):
        response = state.client.post(state.root + '/segments', json=state.start_payload)
        assert response.status_code == 200, response.text
        assert response.json()['segment_id'] == state.segment_id
    assert _segment_count(state) == 1


def test_start_replay_reports_a_replaced_writer_as_stale_capture(capture):
    state = capture
    assert state.client.post(state.root + '/resume', json={'request_id': str(uuid4())}).status_code == 200
    replay = state.client.post(state.root + '/segments', json=state.start_payload)
    assert replay.status_code == 409
    assert replay.json()['detail'] == {'code': 'stale_capture'}
    assert _segment_count(state) == 1


def test_start_replay_reports_an_ended_interview_or_recording_as_capture_closed(capture):
    state = capture
    with Session(state.engine) as db:
        recording = db.query(InterviewRecordingDB).one()
        recording.status = 'ready'
        db.commit()
    closed_recording = state.client.post(state.root + '/segments', json=state.start_payload)
    assert (closed_recording.status_code, closed_recording.json()['detail']) == (409, {'code': 'capture_closed'})
    with Session(state.engine) as db:
        db.query(InterviewRecordingDB).one().status = 'recording'
        db.get(MedicalInterviewDB, state.id).status = InterviewStatus.COMPLETED
        db.commit()
    closed_interview = state.client.post(state.root + '/segments', json=state.start_payload)
    assert (closed_interview.status_code, closed_interview.json()['detail']) == (409, {'code': 'capture_closed'})
    assert _segment_count(state) == 1


def test_resume_keeps_request_identity_and_fences_previous_writer(capture, exchange_agent):
    state = capture
    key = str(uuid4())
    first = state.client.post(state.root + '/resume', json={'request_id': key})
    assert first.status_code == 200, first.text
    assert state.client.post(state.root + '/resume', json={'request_id': key}).json() == first.json()
    assert first.json()['offset_ms'] == 0
    assert first.json()['pending_patient_message_id'] == state.greeting_id
    assert state.client.post(f'/medical-interviews/{state.id}/messages', json={
        'content': 'Stale tab', 'segment_id': state.segment_id,
    }).status_code == 409
    assert state.client.post(f'/medical-interviews/{state.id}/hypotheses', json=[
        {'hypothesis_text': 'Stale hypothesis', 'hypothesis_order': 1},
    ]).status_code == 409
    assert state.client.post(f'/medical-interviews/{state.id}/abandon').status_code == 409
    assert state.client.post(f'/medical-interviews/{state.id}/abandon', headers={'X-Resume-Attempt': key}).status_code == 200
    exchange_agent[0].assert_not_awaited()


def test_new_attempt_requires_verified_resume_calibration(capture):
    state = capture
    key = str(uuid4())
    assert state.client.post(state.root + '/resume', json={'request_id': key}).status_code == 200
    payload = {'request_id': str(uuid4()), 'resume_attempt_id': key,
               'capture_config': {'geometry': state.geometry}}
    assert state.client.post(state.root + '/segments', json=payload).status_code == 409
    with Session(state.engine) as db:
        recording = db.query(InterviewRecordingDB).one()
        config = dict(recording.capture_config)
        config['resume_attempt'] = {**config['resume_attempt'], 'calibration': {'status': 'passed', 'profile': {'synthetic': 'new'}}}
        recording.capture_config = config
        db.commit()
    response = state.client.post(state.root + '/segments', json=payload)
    assert response.status_code == 200, response.text
    assert state.client.post(state.root + '/segments', json=payload).json() == response.json()
    with Session(state.engine) as db:
        attempts = db.query(InterviewRecordingSegmentDB).order_by(InterviewRecordingSegmentDB.sequence).all()
        assert [item.sequence for item in attempts] == [0, 1]
        assert attempts[1].calibration['profile'] == {'synthetic': 'new'}
        assert attempts[0].sealed_at is not None


@pytest.mark.parametrize('transport', [None, 'unknown', 'indexed_chunks_v1'])
def test_existing_noncanonical_interview_cannot_open_or_resume_capture(capture, transport):
    state = capture
    with Session(state.engine) as db:
        interview = db.get(MedicalInterviewDB, state.id)
        interview.interview_metadata = {**interview.interview_metadata, 'recording_transport': transport}
        db.commit()
    assert state.client.post(state.root + '/segments', json=state.start_payload).status_code == 409
    assert state.client.post(state.root + '/resume', json={'request_id': str(uuid4())}).status_code == 409


