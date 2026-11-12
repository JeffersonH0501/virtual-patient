"""The official API exposes one recording transport and retains shared boundaries."""
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.models.medical_interview import MedicalInterviewCreate
from app.routers import interview_recordings, recording_segments, recording_turns


def test_creation_defaults_to_per_turn_without_a_legacy_flag():
    request = MedicalInterviewCreate(clinical_case_id=1)
    assert request.interview_metadata['recording_transport'] == 'per_turn_v1'


@pytest.mark.parametrize('transport', ['reusable_blocks_v1', 'indexed_chunks_v1', 'unknown', None])
def test_creation_rejects_explicit_noncanonical_transport(transport):
    with pytest.raises(ValidationError):
        MedicalInterviewCreate(clinical_case_id=1, interview_metadata={'recording_transport': transport})


def test_only_current_recording_routes_remain():
    app = FastAPI()
    app.include_router(interview_recordings.router)
    app.include_router(recording_segments.router)
    app.include_router(recording_turns.router)
    paths = app.openapi()['paths']
    prefix = '/medical-interviews/{interview_id}'
    assert prefix + '/recording/segments' in paths
    assert prefix + '/recording/resume' in paths
    assert prefix + '/recap' in paths
    assert prefix + '/calibration/captures/{capture_id}/video' in paths
    # The per-turn transport is the current contract.
    assert prefix + '/recording/turns/{turn_id}/video' in paths
    assert prefix + '/recording/turns/finalize' in paths
    assert prefix + '/recording/turns' in paths
    # The former block and single-asset routes stay retired.
    for suffix in ['/capture/sync', '/capture/state', '/recording/start', '/recording/finalize',
                   '/recording/unavailable', '/recording/segments/finalize',
                   '/recording/segments/{segment_id}/seal', '/recording/segments/{segment_id}/media',
                   '/recording/segments/{segment_id}/chunks', '/recording/blocks/{block_id}',
                   '/recording/assets/{asset_kind}']:
        assert prefix + suffix not in paths
