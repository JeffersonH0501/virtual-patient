"""The official API exposes one recording transport and retains shared boundaries."""
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.models.medical_interview import MedicalInterviewCreate
from app.routers import interview_recordings, recording_segments


def test_creation_defaults_to_blocks_without_a_legacy_flag():
    request = MedicalInterviewCreate(clinical_case_id=1)
    assert request.interview_metadata['recording_transport'] == 'reusable_blocks_v1'


@pytest.mark.parametrize('transport', ['indexed_chunks_v1', 'unknown', None])
def test_creation_rejects_explicit_noncanonical_transport(transport):
    with pytest.raises(ValidationError):
        MedicalInterviewCreate(clinical_case_id=1, interview_metadata={'recording_transport': transport})


def test_only_current_recording_routes_remain():
    app = FastAPI()
    app.include_router(interview_recordings.router)
    app.include_router(recording_segments.router)
    paths = app.openapi()['paths']
    prefix = '/medical-interviews/{interview_id}'
    assert prefix + '/recording/segments' in paths
    assert prefix + '/recording/resume' in paths
    assert prefix + '/recap' in paths
    assert prefix + '/calibration/captures/{capture_id}/video' in paths
    for suffix in ['/capture/sync', '/capture/state', '/recording/start', '/recording/finalize',
                   '/recording/unavailable', '/recording/segments/finalize',
                   '/recording/segments/{segment_id}/seal', '/recording/segments/{segment_id}/media',
                   '/recording/segments/{segment_id}/chunks', '/recording/turns/{message_id}',
                   '/recording/turns/{turn_id}/video', '/recording/assets/{asset_kind}']:
        assert prefix + suffix not in paths
